"""Disk-backed M3U catalogue. Only small pages are retained by the TV UI."""
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
import json
from .media import media_kind, media_metadata, is_separator

MAX_IN_MEMORY = 5000
MEMORY_BUDGET = 4 * 1024 * 1024


def classify(channel):
    return media_kind(channel)


CACHE_SECONDS = 24 * 60 * 60
CACHE_SCHEMA = 3
_cache_lock = threading.RLock()
_open_paths = {}


def cache_roots():
    roots = []
    for path in ('/media/hdd', '/media/usb'):
        if os.path.ismount(os.path.realpath(path)):
            roots.append(os.path.join(path, '.iptvpl-cache'))
    return roots + ['/etc/enigma2/iptvpl/catalogue-cache']


def source_fingerprint(source):
    if source.startswith('/'):
        stat = os.stat(source)
        return [stat.st_size, stat.st_mtime_ns]
    return None


def cache_name(source):
    return 'source-' + hashlib.sha256(source.encode('utf-8')).hexdigest() + '.json'


def read_cache_record(record):
    with open(record, 'r', encoding='utf-8') as handle:
        value = json.load(handle)
    filename = value.get('file', '')
    if not re.fullmatch(r'catalogue-[a-zA-Z0-9_-]+\.sqlite', filename):
        raise ValueError('Invalid cache file')
    return value, os.path.join(os.path.dirname(record), filename)


def remove_unused(path):
    if not _open_paths.get(path):
        try:
            os.unlink(path)
        except OSError:
            pass


def load_cached_catalogue(source,progress=None):
    # Prefer the newest valid snapshot, even after a USB drive is reconnected.
    candidates = []
    with _cache_lock:
        for directory in cache_roots():
            record = os.path.join(directory, cache_name(source))
            try:
                meta, path = read_cache_record(record)
                if meta.get('schema') not in (2,CACHE_SCHEMA) or meta.get('fingerprint') != source_fingerprint(source):
                    continue
                age = time.time() - meta['saved']
                if not source.startswith('/') and not 0 <= age < CACHE_SECONDS:
                    continue
                count = meta['count']
                if not isinstance(count, int) or count <= 0:
                    continue
                candidates.append((meta['saved'],record,path,count,meta))
            except Exception:
                continue
        for _,record,path,count,meta in sorted(candidates,reverse=True):
            try:
                from contextlib import closing
                with closing(sqlite_module().connect('file:' + path + '?mode=ro', uri=True)) as connection:
                    if connection.execute('SELECT MAX(id) FROM channels').fetchone()[0] != count:
                        continue
                    if connection.execute('SELECT 1 FROM group_summary LIMIT 1').fetchone() is None:
                        continue
                    if meta['schema']==CACHE_SCHEMA:
                        connection.execute('SELECT 1 FROM series_summary LIMIT 1').fetchall()
                if meta['schema']==2:
                    result=upgrade_catalogue(path,progress)
                    save_cached_catalogue(source,result,meta['fingerprint'],meta['saved'])
                    result.from_cache=True
                    return result
                result = ChannelCatalogue(path, count)
                result.cache_record = record
                result.from_cache = True
                return result
            except Exception as error:
                if str(error).startswith('Brak miejsca') or getattr(error,'sqlite_errorcode',None)==13:
                    raise
                continue
    return None


def save_cached_catalogue(source, result, fingerprint, saved_at=None):
    if not getattr(result, 'is_disk_catalogue', False):
        with _cache_lock:
            for directory in cache_roots():
                record = os.path.join(directory, cache_name(source))
                try:
                    _, previous = read_cache_record(record)
                    os.unlink(record)
                    remove_unused(previous)
                except OSError:
                    pass
                except ValueError:
                    pass
        return
    record = os.path.join(os.path.dirname(result.path), cache_name(source))
    temp = None
    with _cache_lock:
        try:
            try:
                _, previous = read_cache_record(record)
            except Exception:
                previous = None
            meta = {'schema': CACHE_SCHEMA, 'file': os.path.basename(result.path),
                    'saved': time.time() if saved_at is None else saved_at, 'count': len(result), 'fingerprint': fingerprint}
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='source-', suffix='.tmp', dir=os.path.dirname(record), delete=False) as handle:
                temp = handle.name
                json.dump(meta, handle)
            os.replace(temp, record)
            result.cache_record = record
            if previous and previous != result.path:
                remove_unused(previous)
        except OSError:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass
            # Successful playback must not depend on writing the cache pointer.


def cache_directory():
    roots = cache_roots()
    for path in roots:
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
            if shutil.disk_usage(path).free > 128 * 1024 * 1024:
                return path
        except OSError:
            pass
    raise ValueError('Brak miejsca na katalog playlisty. Podłącz dysk USB lub zwolnij pamięć dekodera.')


def sqlite_module():
    try:
        import sqlite3
        return sqlite3
    except ImportError:
        raise ValueError('Duża playlista wymaga pakietu python3-sqlite3. Zainstaluj go poleceniem opkg install python3-sqlite3.')


def as_channel(row):
    channel = {'name': row[0], 'url': row[1], 'group': row[2]}
    if row[3]:
        channel['logo'] = row[3]
    return channel


class CatalogueBuilder:
    def __init__(self,force_disk=False):
        self.force_disk=force_disk
        self.small = []
        self.memory = 0
        self.connection = None
        self.path = None
        self.count = 0
        self.batch = []
        self.batch_bytes = 0

    def append(self, channel):
        if is_separator(channel):
            return
        self.count += 1
        if self.connection is None:
            self.memory += 256 + sum(len(value) * 4 for value in channel.values())
        if self.connection is None and (self.force_disk or self.count > MAX_IN_MEMORY or self.memory > MEMORY_BUDGET):
            directory = cache_directory()
            handle = tempfile.NamedTemporaryFile(prefix='catalogue-', suffix='.sqlite', dir=directory, delete=False)
            self.path = handle.name
            handle.close()
            self.connection = sqlite_module().connect(self.path)
            self.connection.execute('PRAGMA journal_mode=OFF')
            self.connection.execute('PRAGMA synchronous=OFF')
            self.connection.execute('PRAGMA cache_size=-2048')
            self.connection.execute('CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT, url TEXT, group_name TEXT, logo TEXT, category TEXT, search TEXT, favourite TEXT, display_title TEXT, series_title TEXT, season INTEGER, episode INTEGER)')
            for item in self.small:
                self.queue(item)
            self.small = []
        if self.connection is None:
            self.small.append(channel)
        else:
            self.queue(channel)

    def queue(self, channel):
        name, url, group = channel['name'], channel['url'], channel['group']
        meta=media_metadata(channel)
        self.batch.append((name, url, group, channel.get('logo', ''), meta['kind'],
                           (name + '\n' + group).casefold(), hashlib.sha256(url.encode('utf-8')).hexdigest(),
                           meta['display_title'],meta['series_title'],meta['season'],meta['episode']))
        self.batch_bytes += 256 + sum(len(v) * 4 if isinstance(v,str) else 8 for v in self.batch[-1])
        if len(self.batch) >= 1024 or self.batch_bytes >= 2 * 1024 * 1024:
            self.flush()

    def flush(self):
        if not self.batch:
            return
        if shutil.disk_usage(os.path.dirname(self.path)).free < 32 * 1024 * 1024:
            raise ValueError('Brak miejsca na katalog playlisty. Zwolnij pamięć dekodera lub podłącz dysk USB.')
        self.connection.executemany('INSERT INTO channels (name,url,group_name,logo,category,search,favourite,display_title,series_title,season,episode) VALUES (?,?,?,?,?,?,?,?,?,?,?)',self.batch)
        self.batch = []
        self.batch_bytes = 0

    def finish(self):
        if self.connection is None:
            result = self.small
            self.small = []
            return result
        self.flush()
        self.connection.execute('CREATE INDEX category_rows ON channels(category,id)')
        self.connection.execute('CREATE INDEX group_rows ON channels(group_name,id)')
        self.connection.execute('CREATE INDEX favourite_rows ON channels(favourite)')
        self.connection.execute('CREATE INDEX series_rows ON channels(category,group_name,series_title,season,episode)')
        self.connection.execute('CREATE TABLE group_summary AS SELECT group_name,category,COUNT(*) AS amount,MIN(id) AS first_id FROM channels GROUP BY category,group_name')
        self.connection.create_function('casefold',1,lambda value:value.casefold())
        self.connection.execute("CREATE TABLE series_summary AS SELECT group_name,series_title,MIN(id) AS first_id,COUNT(*) AS amount,MIN(NULLIF(logo,'')) AS logo,casefold(series_title||char(10)||group_name) AS search FROM channels WHERE category='series' GROUP BY group_name,series_title")
        self.connection.execute('CREATE INDEX series_groups ON series_summary(group_name,first_id)')
        self.connection.commit()
        self.connection.close()
        self.connection = None
        result = ChannelCatalogue(self.path, self.count)
        self.path = None
        return result

    def abort(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.path:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            self.path = None
        self.small = []
        self.batch = []


class ChannelPage:
    """A sequence view of a SQL result; at most 64 channel dicts are cached."""
    def __init__(self, catalogue, where, params, count, order='id'):
        self.order=order
        self.catalogue, self.where, self.params = catalogue, where, tuple(params)
        self.count = count

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        start = (index // 16) * 16
        page = self.catalogue.read_page(self.where, self.params, start,self.order)
        return page[index - start]

    def position_of(self, channel):
        key = hashlib.sha256(channel['url'].encode('utf-8')).hexdigest()
        with self.catalogue.connect() as connection:
            found = connection.execute('SELECT id FROM channels WHERE '+self.where+' AND favourite=? ORDER BY id LIMIT 1',self.params+(key,)).fetchone()
            if found is None:
                return None
            if self.order=='episode,id':
                number=connection.execute('SELECT episode FROM channels WHERE id=?',found).fetchone()[0]
                return connection.execute('SELECT COUNT(*) FROM channels WHERE '+self.where+' AND (episode<? OR (episode=? AND id<?))',self.params+(number,number,found[0])).fetchone()[0]
            return connection.execute('SELECT COUNT(*) FROM channels WHERE '+self.where+' AND id<?',self.params+(found[0],)).fetchone()[0]

    def __iter__(self):
        for index in range(self.count):
            yield self[index]


class SeriesCards:
    def __init__(self,catalogue,count):
        self.catalogue=catalogue;self.count=count;self.start=-1;self.page=[]
    def __len__(self):return self.count
    def __getitem__(self,index):
        if index<0:index+=self.count
        if not 0<=index<self.count:raise IndexError(index)
        start=(index//16)*16
        if self.start!=start:
            _,self.page=self.catalogue.vod_page('series',offset=start,limit=16)
            self.start=start
        return self.page[index-start]
    def __iter__(self):
        for index in range(self.count):yield self[index]
    def position_of(self,channel):
        title=channel.get('series_title') or media_metadata(channel)['series_title']
        with self.catalogue.connect() as connection:
            row=connection.execute('SELECT first_id FROM series_summary WHERE group_name=? AND series_title=?',(channel['group'],title)).fetchone()
            return connection.execute('SELECT COUNT(*) FROM series_summary WHERE first_id<?',row).fetchone()[0] if row else None


class ChannelCatalogue:
    is_disk_catalogue = True

    def __init__(self, path, count):
        self.path, self.count = path, count
        self.closed = False
        self.cache_record = None
        self.from_cache = False
        with _cache_lock:
            _open_paths[path] = _open_paths.get(path, 0) + 1
        from collections import OrderedDict
        self.pages = OrderedDict()

    def __len__(self):
        return self.count

    def connect(self):
        if self.closed:
            raise ValueError('Katalog playlisty jest zamknięty.')
        # sqlite context managers commit but do not close; closing() is needed for paged UI reads.
        from contextlib import closing
        return closing(sqlite_module().connect('file:' + self.path + '?mode=ro', uri=True))

    def read_page(self, where, params, start, order='id'):
        if order not in ('id','episode,id'):
            raise ValueError('Invalid page order')
        key = (where, tuple(params), start,order)
        if key in self.pages:
            self.pages.move_to_end(key)
            return self.pages[key]
        with self.connect() as connection:
            rows = connection.execute('SELECT name,url,group_name,logo FROM channels WHERE ' + where + ' ORDER BY '+order+' LIMIT 16 OFFSET ?', tuple(params) + (start,)).fetchall()
        page = [as_channel(row) for row in rows]
        self.pages[key] = page
        while len(self.pages) > 4:
            self.pages.popitem(last=False)
        return page

    def build_rows(self, category, query='', favourites=()):
        clauses, params = ['1'], []
        if category in ('live', 'movies', 'series'):
            clauses.append('category=?'); params.append(category)
        if query:
            clauses.append('instr(search,?)>0'); params.append(query.casefold())
        if category == 'favourites':
            keys = sorted(key for key in favourites if re.fullmatch('[0-9a-f]{64}', key))
            clauses.append('favourite IN (' + ','.join("'" + key + "'" for key in keys) + ')' if keys else '0')
        where = ' AND '.join(clauses)
        with self.connect() as connection:
            if category == 'start' and not query:
                counts = dict(connection.execute('SELECT category,SUM(amount) FROM group_summary GROUP BY category'))
                counts['series']=connection.execute('SELECT COUNT(*) FROM series_summary').fetchone()[0]
                rows = []
                for key, title in [('live','Telewizja na żywo'),('movies','Filmy'),('series','Seriale')]:
                    if counts.get(key):
                        rows.append((title, SeriesCards(self,counts[key]) if key=='series' else ChannelPage(self, 'category=?', [key], counts[key])))
                return rows
            if not query and category != 'favourites':
                if category in ('live','movies','series'):
                    groups = connection.execute('SELECT group_name,amount,first_id FROM group_summary WHERE category=? ORDER BY first_id',(category,)).fetchall()
                else:
                    groups = connection.execute('SELECT group_name,SUM(amount),MIN(first_id) FROM group_summary GROUP BY group_name ORDER BY MIN(first_id)').fetchall()
            else:
                groups = connection.execute('SELECT group_name,COUNT(*),MIN(id) FROM channels WHERE '+where+' GROUP BY group_name ORDER BY MIN(id)', params).fetchall()
        return [(group,ChannelPage(self,where+' AND group_name=?',params+[group],count)) for group,count,_ in groups]

    def vod_groups(self,kind,query=''):
        with self.connect() as connection:
            if kind=='series':
                where='instr(search,?)>0' if query else '1'
                params=(query.casefold(),) if query else ()
                rows=connection.execute('SELECT group_name,COUNT(*),MIN(first_id) FROM series_summary WHERE '+where+' GROUP BY group_name ORDER BY MIN(first_id)',params).fetchall()
            elif not query:
                rows=connection.execute('SELECT group_name,amount,first_id FROM group_summary WHERE category=? ORDER BY first_id',(kind,)).fetchall()
            else:
                rows=connection.execute('SELECT group_name,COUNT(*),MIN(id) FROM channels WHERE category=? AND instr(search,?)>0 GROUP BY group_name ORDER BY MIN(id)',(kind,query.casefold())).fetchall()
        return [('Wszystkie',None,sum(row[1] for row in rows))]+[(group,group,count) for group,count,_ in rows]

    def vod_page(self,kind,group=None,query='',offset=0,limit=8):
        if kind not in ('movies','series'):
            raise ValueError('Invalid VOD kind')
        clauses=[];params=[]
        if group is not None:
            clauses.append('group_name=?');params.append(group)
        if query:
            clauses.append('instr(search,?)>0');params.append(query.casefold())
        extra=' AND '.join(clauses) or '1'
        with self.connect() as connection:
            if kind=='series':
                count=connection.execute('SELECT COUNT(*) FROM series_summary WHERE '+extra,params).fetchone()[0]
                rows=connection.execute('SELECT s.series_title,c.url,s.group_name,COALESCE(s.logo,\'\'),s.amount FROM series_summary s JOIN channels c ON c.id=s.first_id WHERE '+extra.replace('group_name','s.group_name').replace('instr(search','instr(s.search')+' ORDER BY s.first_id LIMIT ? OFFSET ?',params+[min(limit,32),offset]).fetchall()
                return count,[dict(name=title,url=url,group=genre,logo=logo or '',kind='series',series_title=title,display_title=title,episode_count=amount) for title,url,genre,logo,amount in rows]
            where='category=? AND '+extra;values=[kind]+params
            count=connection.execute('SELECT COUNT(*) FROM channels WHERE '+where,values).fetchone()[0]
            rows=connection.execute('SELECT name,url,group_name,logo,display_title FROM channels WHERE '+where+' ORDER BY id LIMIT ? OFFSET ?',values+[min(limit,32),offset]).fetchall()
        return count,[dict(as_channel(row[:4]),kind='movies',display_title=row[4]) for row in rows]

    def series_seasons(self,group,title):
        where="category='series' AND group_name=? AND series_title=?"
        with self.connect() as connection:
            rows=connection.execute('SELECT season,COUNT(*) FROM channels WHERE '+where+' GROUP BY season ORDER BY season',(group,title)).fetchall()
        return [('Sezon %d'%season,ChannelPage(self,where+' AND season=?',(group,title,season),count,order='episode,id')) for season,count in rows]

    def movie_sequence(self,group=None,query=''):
        where="category='movies'";params=[]
        if group is not None: where+=' AND group_name=?';params.append(group)
        if query: where+=' AND instr(search,?)>0';params.append(query.casefold())
        with self.connect() as connection:
            count=connection.execute('SELECT COUNT(*) FROM channels WHERE '+where,params).fetchone()[0]
        return ChannelPage(self,where,params,count)


    def close(self):
        if not self.closed:
            self.closed = True
            self.pages.clear()
            with _cache_lock:
                remaining = _open_paths.get(self.path, 1) - 1
                if remaining > 0:
                    _open_paths[self.path] = remaining
                else:
                    _open_paths.pop(self.path, None)
                keep = False
                if self.cache_record:
                    try:
                        _, current = read_cache_record(self.cache_record)
                        keep = current == self.path
                    except Exception:
                        pass
                if not keep:
                    remove_unused(self.path)

    def __del__(self):
        self.close()





def upgrade_catalogue(path, progress=None):
    from contextlib import closing
    builder=CatalogueBuilder(force_disk=True)
    try:
        with closing(sqlite_module().connect('file:'+path+'?mode=ro',uri=True)) as connection:
            cursor=connection.execute('SELECT name,url,group_name,logo FROM channels ORDER BY id')
            while True:
                rows=cursor.fetchmany(256)
                if not rows: break
                for row in rows: builder.append(as_channel(row))
                if progress: progress(-3,builder.count)
        if not builder.count: raise ValueError('Brak pozycji po sprawdzeniu listy.')
        return builder.finish()
    except Exception:
        builder.abort()
        raise
