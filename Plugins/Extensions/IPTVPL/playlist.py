"""M3U input, independent of Enigma2."""
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 8 * 1024 * 1024


def stream_url(value):
    parsed = urlsplit(value)
    return parsed.scheme.lower() in ('http', 'https', 'rtsp', 'rtmp', 'udp', 'rtp') and bool(parsed.netloc)


def parse_m3u(text, base=''):
    channels = []
    pending = None
    group = ''
    for raw in text.lstrip('\ufeff').splitlines():
        line = raw.strip()
        if line.startswith('#EXTINF:'):
            # A comma inside a quoted attribute is not the title separator.
            parts = re.split(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', line, maxsplit=1)
            attrs = dict(re.findall(r'([\w-]+)="([^\"]*)"', parts[0]))
            pending = (parts[1].strip() if len(parts) > 1 else attrs.get('tvg-name', ''), attrs)
            group = attrs.get('group-title', '')
        elif line.startswith('#EXTGRP:'):
            group = line.partition(':')[2].strip()
        elif line and not line.startswith('#'):
            url = urljoin(base, line) if base else line
            if stream_url(url):
                name, attrs = pending or ('', {})
                channels.append({'name': name or attrs.get('tvg-name') or 'Kanał %d' % (len(channels) + 1),
                                 'url': url, 'group': group or 'Pozostałe'})
            pending = None
            group = ''
    return channels


def load_playlist(source, timeout=20):
    source = source.strip()
    if source.lower().startswith(('http://', 'https://')):
        request = Request(source, headers={'User-Agent': 'Enigma2-IPTVPL/1.0'})
        with urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
            base = response.geturl()
    else:
        if not source.startswith('/'):
            raise ValueError('Podaj pełną ścieżkę pliku albo adres HTTP/HTTPS.')
        with open(source, 'rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        base = ''
    if len(data) > MAX_BYTES:
        raise ValueError('Lista przekracza limit 8 MiB.')
    channels = parse_m3u(data.decode('utf-8-sig', errors='replace'), base)
    if not channels:
        raise ValueError('Lista nie zawiera obsługiwanych adresów kanałów.')
    return channels
