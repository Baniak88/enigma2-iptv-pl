"""M3U input, independent of Enigma2."""
import re
import threading
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 512 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_CHANNELS = 2000000


class PlaylistLimitError(ValueError):
    pass


def stream_url(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in ('http', 'https', 'rtsp', 'rtmp', 'udp', 'rtp') and bool(parsed.netloc)
    except ValueError:
        return False


def iter_m3u(lines, base=''):
    pending = None
    group = ''
    count = 0
    first = True
    for raw in lines:
        line = raw.strip().lstrip('\ufeff')
        if first and line:
            first = False
            if line.lower().startswith(('<!doctype html', '<html')):
                raise ValueError('html_response')
        if line.startswith('#EXTINF:'):
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
                count += 1
                if count > MAX_CHANNELS:
                    raise PlaylistLimitError('Lista przekracza limit 2000000 pozycji. Podziel ją u dostawcy.')
                channel = {'name': name or attrs.get('tvg-name') or 'Kanał %d' % count,
                           'url': url, 'group': group or 'Pozostałe'}
                logo = attrs.get('tvg-logo', '').strip()
                if logo:
                    logo = urljoin(base, logo) if base else logo
                    try:
                        if urlsplit(logo).scheme.lower() in ('http', 'https'):
                            channel['logo'] = logo
                    except ValueError:
                        pass
                yield channel
            pending = None
            group = ''


def parse_m3u(text, base=''):
    import io
    return list(iter_m3u(io.StringIO(text), base))


def playlist_lines(handle, progress=None, total=None):
    """Decode bounded chunks; never retain the complete downloaded playlist."""
    received = 0
    pending = b''
    if total is not None and total > MAX_BYTES:
        raise PlaylistLimitError('Lista przekracza limit 512 MiB.')
    if progress:
        progress(0, total)
    while True:
        chunk = handle.read(min(65536, MAX_BYTES + 1 - received))
        if not chunk:
            break
        received += len(chunk)
        if received > MAX_BYTES:
            raise PlaylistLimitError('Lista przekracza limit 512 MiB.')
        if progress:
            progress(received, total)
        lines = (pending + chunk).split(b'\n')
        pending = lines.pop()
        for line in lines:
            if len(line) > MAX_LINE_BYTES:
                raise PlaylistLimitError('Nieprawidłowa lista: pojedynczy wiersz przekracza 1 MiB.')
            yield line.decode('utf-8', errors='replace')
        if len(pending) > MAX_LINE_BYTES:
            raise PlaylistLimitError('Nieprawidłowa lista: pojedynczy wiersz przekracza 1 MiB.')
    if pending:
        yield pending.decode('utf-8', errors='replace')


def count_playlist_file(path):
    with open(path, 'rb') as handle:
        count = sum(1 for _ in iter_m3u(playlist_lines(handle)))
    if not count:
        raise ValueError('Lista nie zawiera obsługiwanych adresów kanałów.')
    return count


def load_playlist(source, timeout=20, progress=None):
    from .catalogue import CatalogueBuilder
    builder = CatalogueBuilder()
    source = source.strip()
    try:
        if source.lower().startswith(('http://', 'https://')):
            request = Request(source, headers={'User-Agent': 'Enigma2-IPTVPL/1.0'})
            with urlopen(request, timeout=timeout) as response:
                header = response.headers.get('Content-Length') if hasattr(response, 'headers') else None
                try:
                    total = int(header) if header else None
                except (TypeError, ValueError):
                    total = None
                for channel in iter_m3u(playlist_lines(response, progress, total), response.geturl()):
                    builder.append(channel)
        else:
            if not source.startswith('/'):
                raise ValueError('Podaj pełną ścieżkę pliku albo adres HTTP/HTTPS.')
            with open(source, 'rb') as handle:
                for channel in iter_m3u(playlist_lines(handle, progress)):
                    builder.append(channel)
        if not builder.count:
            raise ValueError('Lista nie zawiera obsługiwanych adresów kanałów.')
        if builder.connection is not None and progress:
            progress(-1, builder.count)
        return builder.finish()
    except Exception:
        builder.abort()
        raise


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


def discard_playlist(value):
    if getattr(value, 'is_disk_catalogue', False):
        value.close()


def remember_playlist(source, channels):
    global _preview
    with _preview_lock:
        previous = _preview
        cached = (source, time.monotonic(), channels)
        _preview = cached
    if previous:
        discard_playlist(previous[2])
    def expire():
        global _preview
        with _preview_lock:
            if _preview is not cached:
                return
            _preview = None
        discard_playlist(channels)
    timer = threading.Timer(120, expire)
    timer.daemon = True
    timer.start()


def take_playlist_preview(source):
    global _preview
    with _preview_lock:
        cached = _preview
        _preview = None
    if cached and cached[0] == source and time.monotonic() - cached[1] < 120:
        return cached[2]
    if cached:
        discard_playlist(cached[2])
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
    if isinstance(error, PlaylistLimitError):
        return str(error)
    if getattr(error, 'sqlite_errorcode', None) == 13:
        return 'Brak miejsca na katalog playlisty. Zwolnij pamięć dekodera lub podłącz dysk USB.'
    if isinstance(error, ValueError):
        if str(error).startswith(('Brak miejsca', 'Duża playlista wymaga')):
            return str(error)
        if str(error) == 'html_response':
            return 'Serwer zwrócił stronę WWW zamiast M3U. Sprawdź adres i dane konta.'
        if '512 MiB' in str(error):
            return 'Playlista przekracza limit 512 MiB. Użyj mniejszej listy od dostawcy.'
        return 'Odebrany plik nie zawiera obsługiwanych kanałów M3U.'
    if isinstance(error, FileNotFoundError):
        return 'Nie znaleziono pliku playlisty na dekoderze.'
    return 'Nie udało się połączyć z serwerem playlisty. Sprawdź sieć i adres.'


