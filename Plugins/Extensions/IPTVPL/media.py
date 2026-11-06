"""Media semantics shared by M3U import and the TV/VOD interface."""
import re
from urllib.parse import urlsplit

EPISODE = re.compile(r'(?i)(?:\bS(?P<s>\d{1,3})\s*E(?P<e>\d{1,4})\b|\b(?P<sx>\d{1,3})x(?P<ex>\d{1,4})\b|\b(?:sezon|season)\s*(?P<ss>\d{1,3})\s*[-:. ]*(?:odcinek|episode)\s*(?P<ee>\d{1,4})\b)')
VIDEO_FILE = re.compile(r'\.(mp4|mkv|avi|mov|webm|m4v|wmv|flv|mpg|mpeg)$',re.I)
LIVE_FILE = re.compile(r'\.(ts|m3u8?)$',re.I)
SERIES_GROUP = re.compile(r'\b(series|seriale|serial|sezony|seasons)\b',re.I)
MOVIE_GROUP = re.compile(r'\b(vod|movies?|filmy|films|filmes|peliculas)\b',re.I)
PREFIX = re.compile(r'^(?:PL|POL|EN|UK|US|DE|FR|ES|IT|PT|RU|AR|TR|NL|CZ)(?:\s*-?\s*VIP)?\s*(?:\||:| - )\s*',re.I)


def clean_title(value):
    return PREFIX.sub('',value or '').strip()


def media_kind(channel):
    """As in Android Channel.infer: address before group; film TV remains live."""
    try:
        path=urlsplit(channel['url']).path.casefold()
    except ValueError:
        return 'live'
    group=channel.get('group','')
    types={'live':'live','movie':'movies','movies':'movies','vod':'movies','series':'series'}
    parts=path.strip('/').split('/')
    handler=parts[-4] if len(parts)>=4 and parts[-4] in types else next((part for part in parts if part in types),None)
    if handler:return types[handler]
    if LIVE_FILE.search(path):return 'live'
    if VIDEO_FILE.search(path):
        return 'series' if EPISODE.search(channel.get('name','')) or SERIES_GROUP.search(group) else 'movies'
    if EPISODE.search(channel.get('name','')) and SERIES_GROUP.search(group):
        return 'series'
    return 'movies' if MOVIE_GROUP.search(group) else 'live'


def is_separator(channel):
    name=channel.get('name','').strip()
    if re.match(r'^[#*=─▬•]{3,}.*[#*=─▬•]{3,}$',name):
        return True
    # Provider announcement/numbered series slots are not on-demand episodes.
    if SERIES_GROUP.search(channel.get('group','')) and media_kind(channel)=='live':
        def normalize(value):
            return re.sub(r'\b(?:series|serie|seriale)\b','series',clean_title(value).casefold())
        group=normalize(channel['group']); title=normalize(name)
        if title.startswith(group) and re.fullmatch(r'\s*(?:info|informacje|\d{1,2})',title[len(group):]):
            return True
    return False


def media_metadata(channel):
    kind=media_kind(channel)
    title=clean_title(channel['name'])
    series=''; season=0; episode=0
    if kind=='series':
        match=EPISODE.search(title)
        if match:
            series=title[:match.start()].strip(' -|:·._') or title
            season=int(match.group('s') or match.group('sx') or match.group('ss'))
            episode=int(match.group('e') or match.group('ex') or match.group('ee'))
            title=title[match.end():].strip(' -|:·._') or 'Odcinek %d'%episode
        else:
            series=title
            season=1
    return {'kind':kind,'display_title':title,'series_title':series,'season':season,'episode':episode}


def vod_groups(channels,kind,query=''):
    if getattr(channels,'is_disk_catalogue',False):
        return channels.vod_groups(kind,query)
    items=memory_vod_items(channels,kind,None,query)
    counts={}
    for item in items:
        counts[item['group']]=counts.get(item['group'],0)+1
    return [('Wszystkie',None,len(items))]+[(name,name,count) for name,count in counts.items()]


def memory_vod_items(channels,kind,group=None,query=''):
    result=[]; shows={}
    for channel in channels:
        if is_separator(channel) or media_kind(channel)!=kind or (group is not None and channel['group']!=group):
            continue
        meta=media_metadata(channel)
        if kind=='series':
            key=(channel['group'],meta['series_title'])
            if query and query.casefold() not in (meta['series_title']+'\n'+channel['group']).casefold():
                continue
            if key in shows:
                shows[key]['episode_count']+=1
                continue
            item=dict(channel,kind='series',display_title=meta['series_title'],series_title=meta['series_title'],episode_count=1)
            shows[key]=item; result.append(item)
        elif not query or query.casefold() in (channel['name']+'\n'+channel['group']).casefold():
            result.append(dict(channel,**meta))
    return result


def vod_page(channels,kind,group=None,query='',offset=0,limit=8):
    if getattr(channels,'is_disk_catalogue',False):
        return channels.vod_page(kind,group,query,offset,limit)
    items=memory_vod_items(channels,kind,group,query)
    return len(items),items[offset:offset+limit]


def series_seasons(channels,item):
    if getattr(channels,'is_disk_catalogue',False):
        return channels.series_seasons(item['group'],item['series_title'])
    groups={}
    for channel in channels:
        meta=media_metadata(channel)
        if meta['kind']=='series' and channel['group']==item['group'] and meta['series_title']==item['series_title']:
            groups.setdefault(meta['season'],[]).append((meta['episode'],channel))
    return [('Sezon %d'%number,[channel for _,channel in sorted(episodes,key=lambda value:value[0])]) for number,episodes in sorted(groups.items())]


def movie_sequence(channels,group=None,query=''):
    if getattr(channels,'is_disk_catalogue',False):
        return channels.movie_sequence(group,query)
    return [dict(item) for item in memory_vod_items(channels,'movies',group,query)]


def cached_artwork(url,cache_only=False):
    """Small on-disk image cache; URLs, including account tokens, are not file names."""
    import hashlib
    import os
    import shutil
    import tempfile
    import time
    from .catalogue import cache_directory, cache_roots
    from .playlist import load_artwork
    digest=hashlib.sha256(url.encode('utf-8')).hexdigest()+'.img'
    for root in cache_roots():
        cached=os.path.join(root,'artwork',digest)
        if os.path.isfile(cached) and time.time()-os.path.getmtime(cached)<7*86400:
            os.utime(cached,None)
            return cached
    if cache_only:return None
    directory=os.path.join(cache_directory(),'artwork')
    os.makedirs(directory,mode=0o700,exist_ok=True)
    target=os.path.join(directory,digest)
    if os.path.isfile(target) and time.time()-os.path.getmtime(target)<7*86400:
        os.utime(target,None)
        return target
    source=load_artwork(url)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=directory,prefix='cover-',suffix='.tmp',delete=False) as handle:
            temporary=handle.name
            with open(source,'rb') as input_file:
                shutil.copyfileobj(input_file,handle,65536)
        os.replace(temporary,target)
    finally:
        try: os.unlink(source)
        except OSError: pass
        if temporary and os.path.exists(temporary): os.unlink(temporary)
    files=sorted((os.path.getmtime(os.path.join(directory,name)),os.path.join(directory,name)) for name in os.listdir(directory) if name.endswith('.img'))
    for _,old in files[:-128]:
        try: os.unlink(old)
        except OSError: pass
    return target
