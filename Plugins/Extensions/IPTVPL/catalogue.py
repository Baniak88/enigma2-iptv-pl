"""Disk-backed M3U catalogue. Only small pages are retained by the TV UI."""
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
import json

MAX_IN_MEMORY = 5000
MEMORY_BUDGET = 4 * 1024 * 1024


def classify(channel):
    group = channel.get('group', '').casefold()
    if any(word in group for word in ('serial', 'series', 'sezon', 'season')):
        return 'series'
    if any(word in group for word in ('film', 'movie', 'vod', 'kino')):
        return 'movies'
    return 'live'


CACHE_SECONDS = 24 * 60 * 60
CACHE_SCHEMA = 2
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


def load_cached_catalogue(source):
    # Prefer the newest valid snapshot, even after a USB drive is reconnected.
    candidates = []
    with _cache_lock:
        for directory in cache_roots():
            record = os.path.join(directory, cache_name(source))
            try:
                meta, path = read_cache_record(record)
                if meta.get('schema') != CACHE_SCHEMA or meta.get('fingerprint') != source_fingerprint(source):
                    continue
                age = time.time() - meta['saved']
                if not source.startswith('/') and not 0 <= age < CACHE_SECONDS:
                    continue
                count = meta['count']
                if not isinstance(count, int) or count <= 0:
                    continue
                candidates.append((meta['saved'],record,path,count))
            except Exception:
                continue
        for _,record,path,count in sorted(candidates,reverse=True):
            try:
                from contextlib import closing
                with closing(sqlite_module().connect('file:' + path + '?mode=ro', uri=True)) as connection:
                    if connection.execute('SELECT MAX(id) FROM channels').fetchone()[0] != count:
                        continue
                    if connection.execute('SELECT 1 FROM group_summary LIMIT 1').fetchone() is None:
                        continue
                result = ChannelCatalogue(path, count)
                result.cache_record = record
                result.from_cache = True
                return result
            except Exception:
                continue
    return None


def save_cached_catalogue(source, result, fingerprint):
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
                    'saved': time.time(), 'count': len(result), 'fingerprint': fingerprint}
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
    def __init__(self):
        self.small = []
        self.memory = 0
        self.connection = None
        self.path = None
        self.count = 0
        self.batch = []
        self.batch_bytes = 0

    def append(self, channel):
        self.count += 1
        if self.connection is None:
            self.memory += 256 + sum(len(value) * 4 for value in channel.values())
        if self.connection is None and (self.count > MAX_IN_MEMORY or self.memory > MEMORY_BUDGET):
            directory = cache_directory()
            handle = tempfile.NamedTemporaryFile(prefix='catalogue-', suffix='.sqlite', dir=directory, delete=False)
            self.path = handle.name
            handle.close()
            self.connection = sqlite_module().connect(self.path)
            self.connection.execute('PRAGMA journal_mode=OFF')
            self.connection.execute('PRAGMA synchronous=OFF')
            self.connection.execute('PRAGMA cache_size=-2048')
            self.connection.execute('CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT, url TEXT, group_name TEXT, logo TEXT, category TEXT, search TEXT, favourite TEXT)')
            for item in self.small:
                self.queue(item)
            self.small = []
        if self.connection is None:
            self.small.append(channel)
        else:
            self.queue(channel)

    def queue(self, channel):
        name, url, group = channel['name'], channel['url'], channel['group']
        self.batch.append((name, url, group, channel.get('logo', ''), classify(channel),
                           (name + '\n' + group).casefold(), hashlib.sha256(url.encode('utf-8')).hexdigest()))
        self.batch_bytes += 256 + sum(len(v) * 4 for v in self.batch[-1])
        if len(self.batch) >= 1024 or self.batch_bytes >= 2 * 1024 * 1024:
            self.flush()

    def flush(self):
        if not self.batch:
            return
        if shutil.disk_usage(os.path.dirname(self.path)).free < 32 * 1024 * 1024:
            raise ValueError('Brak miejsca na katalog playlisty. Zwolnij pamięć dekodera lub podłącz dysk USB.')
        self.connection.executemany('INSERT INTO channels (name,url,group_name,logo,category,search,favourite) VALUES (?,?,?,?,?,?,?)',self.batch)
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
        self.connection.execute('CREATE TABLE group_summary AS SELECT group_name,category,COUNT(*) AS amount,MIN(id) AS first_id FROM channels GROUP BY group_name')
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
    def __init__(self, catalogue, where, params, count):
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
        page = self.catalogue.read_page(self.where, self.params, start)
        return page[index - start]

    def position_of(self, channel):
        key = hashlib.sha256(channel['url'].encode('utf-8')).hexdigest()
        with self.catalogue.connect() as connection:
            found = connection.execute('SELECT id FROM channels WHERE '+self.where+' AND favourite=? ORDER BY id LIMIT 1',self.params+(key,)).fetchone()
            if found is None:
                return None
            return connection.execute('SELECT COUNT(*) FROM channels WHERE '+self.where+' AND id<?',self.params+(found[0],)).fetchone()[0]

    def __iter__(self):
        for index in range(self.count):
            yield self[index]


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

    def read_page(self, where, params, start):
        key = (where, tuple(params), start)
        if key in self.pages:
            self.pages.move_to_end(key)
            return self.pages[key]
        with self.connect() as connection:
            rows = connection.execute('SELECT name,url,group_name,logo FROM channels WHERE ' + where + ' ORDER BY id LIMIT 16 OFFSET ?', tuple(params) + (start,)).fetchall()
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
                rows = []
                for key, title in [('live','Telewizja na żywo'),('movies','Filmy'),('series','Seriale')]:
                    if counts.get(key):
                        rows.append((title, ChannelPage(self, 'category=?', [key], counts[key])))
                return rows
            if not query and category != 'favourites':
                if category in ('live','movies','series'):
                    groups = connection.execute('SELECT group_name,amount,first_id FROM group_summary WHERE category=? ORDER BY first_id',(category,)).fetchall()
                else:
                    groups = connection.execute('SELECT group_name,amount,first_id FROM group_summary ORDER BY first_id').fetchall()
            else:
                groups = connection.execute('SELECT group_name,COUNT(*),MIN(id) FROM channels WHERE '+where+' GROUP BY group_name ORDER BY MIN(id)', params).fetchall()
        return [(group,ChannelPage(self,where+' AND group_name=?',params+[group],count)) for group,count,_ in groups]

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


