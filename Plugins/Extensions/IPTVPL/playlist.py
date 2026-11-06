"""M3U input, independent of Enigma2."""
import re
import threading
import time
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
                logo = attrs.get('tvg-logo', '').strip()
                if logo:
                    logo = urljoin(base, logo) if base else logo
                    if urlsplit(logo).scheme.lower() in ('http', 'https'):
                        channels[-1]['logo'] = logo
            pending = None
            group = ''
    return channels


def load_playlist(source, timeout=20, progress=None):
    source = source.strip()
    if source.lower().startswith(('http://', 'https://')):
        request = Request(source, headers={'User-Agent': 'Enigma2-IPTVPL/1.0'})
        with urlopen(request, timeout=timeout) as response:
            if progress is None:
                data = response.read(MAX_BYTES + 1)
            else:
                chunks = []
                received = 0
                header = response.headers.get('Content-Length') if hasattr(response, 'headers') else None
                try:
                    total = int(header) if header else None
                except (TypeError, ValueError):
                    total = None
                if progress:
                    progress(0, total)
                while received <= MAX_BYTES:
                    chunk = response.read(min(65536, MAX_BYTES + 1 - received))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total)
                data = b''.join(chunks)
            base = response.geturl()
    else:
        if not source.startswith('/'):
            raise ValueError('Podaj pełną ścieżkę pliku albo adres HTTP/HTTPS.')
        with open(source, 'rb') as handle:
            data = handle.read(MAX_BYTES + 1)
        base = ''
    if len(data) > MAX_BYTES:
        raise ValueError('Lista przekracza limit 8 MiB.')
    text = data.decode('utf-8-sig', errors='replace')
    if text.lstrip().lower().startswith(('<!doctype html', '<html')):
        raise ValueError('html_response')
    channels = parse_m3u(text, base)
    if not channels:
        raise ValueError('Lista nie zawiera obsługiwanych adresów kanałów.')
    return channels


def load_artwork(url):
    """Fetch a single small artwork file in a worker; the caller owns its lifetime."""
    import os
    import tempfile
    if urlsplit(url).scheme.lower() not in ('http', 'https'):
        raise ValueError('Unsupported artwork URL')
    request = Request(url, headers={'User-Agent': 'Enigma2-IPTVPL/1.0'})
    with urlopen(request, timeout=5) as response:
        data = response.read(512 * 1024 + 1)
    if len(data) > 512 * 1024 or not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
        raise ValueError('Unsupported or oversized artwork')
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='iptvpl-art-', suffix='.img', delete=False) as handle:
            path = handle.name
            handle.write(data)
        return path
    except Exception:
        if path:
            os.unlink(path)
        raise




_preview_lock = threading.Lock()
_preview = None


def remember_playlist(source, channels):
    global _preview
    with _preview_lock:
        _preview = (source, time.monotonic(), channels)


def take_playlist_preview(source):
    global _preview
    with _preview_lock:
        cached = _preview
        _preview = None
    if cached and cached[0] == source and time.monotonic() - cached[1] < 120:
        return cached[2]
    return None


def playlist_error_message(error):
    """User-facing errors must not contain URLs, passwords or provider responses."""
    import socket
    import ssl
    from urllib.error import HTTPError, URLError
    if isinstance(error, HTTPError):
        if error.code in (401, 403):
            return 'Serwer odrzucił dostęp (HTTP %d). Sprawdź dane konta i ważność listy.' % error.code
        if error.code == 404:
            return 'Nie znaleziono playlisty (HTTP 404). Sprawdź cały adres URL.'
        if error.code == 429:
            return 'Za dużo żądań (HTTP 429). Poczekaj chwilę i ponów próbę.'
        return 'Błąd serwera playlisty (HTTP %d). Spróbuj później.' % error.code
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return 'Przekroczono czas oczekiwania. Sprawdź internet lub włącz tryb Wolny internet.'
    if isinstance(reason, socket.gaierror):
        return 'Nie można odnaleźć serwera. Sprawdź adres i połączenie internetowe.'
    if isinstance(reason, ssl.SSLError):
        return 'Błąd certyfikatu HTTPS. Sprawdź datę dekodera i adres dostawcy.'
    if isinstance(error, ValueError):
        if str(error) == 'html_response':
            return 'Serwer zwrócił stronę WWW zamiast M3U. Sprawdź adres i dane konta.'
        if '8 MiB' in str(error):
            return 'Playlista przekracza limit 8 MiB. Użyj mniejszej listy od dostawcy.'
        return 'Odebrany plik nie zawiera obsługiwanych kanałów M3U.'
    if isinstance(error, FileNotFoundError):
        return 'Nie znaleziono pliku playlisty na dekoderze.'
    return 'Nie udało się połączyć z serwerem playlisty. Sprawdź sieć i adres.'
