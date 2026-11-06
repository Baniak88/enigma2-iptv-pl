"""Local playlist imports. No Enigma2 objects are touched by the HTTP worker."""
import hmac
import json
import os
import re
import secrets
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue
from urllib.parse import unquote, urlsplit

from .playlist import MAX_BYTES, parse_m3u, load_playlist, remember_playlist, playlist_error_message, count_playlist_file

PLAYLIST_DIR = '/etc/enigma2/iptvpl/playlists'

PAGE = '''<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPTV PL — dodaj playlistę</title><style>
body{background:#101010;color:#fff;font:18px system-ui;margin:0;padding:24px}main{max-width:540px;margin:20px auto}h1{font-size:30px}h2{font-size:23px;margin-top:32px}b{color:#ef3340}label{display:block;margin-top:20px}input,textarea,button{box-sizing:border-box;width:100%;padding:16px;margin-top:10px;border-radius:10px;border:1px solid #555;font:inherit;background:#262626;color:#fff}textarea{resize:vertical;overflow-wrap:anywhere}button{background:#e50914;border:0;font-weight:700}p{color:#bbb;line-height:1.5}#result{white-space:pre-wrap;position:sticky;top:8px;background:#262626;border-left:4px solid #e50914;padding:16px;z-index:2}#result:empty{display:none}button:disabled{opacity:.5}hr{border:0;border-top:1px solid #383838;margin-top:32px}</style>
<main><b>IPTV PL</b><h1>Dodaj playlistę</h1><p>Telefon i dekoder muszą być w tej samej sieci. Wpisz kod z telewizora i wybierz jedną z opcji.</p>
<label>Kod z telewizora<input id="code" inputmode="numeric" autocomplete="off" pattern="[0-9]{6}" maxlength="6" required></label>
<p id="result" role="status" aria-live="polite"></p><h2>Wklej cały adres URL M3U</h2>
<form id="url-form"><label>Pełny adres playlisty<textarea id="playlist-url" rows="4" maxlength="16384" autocapitalize="off" autocomplete="off" autocorrect="off" spellcheck="false" placeholder="https://dostawca.pl/get.php?username=...&amp;password=...&amp;type=m3u_plus" required></textarea></label>
<p>Przytrzymaj pole i wybierz „Wklej”. Zachowaj cały adres, razem z parametrami po znaku ?. Nie musi kończyć się na .m3u.</p><button id="send-url">Wyślij adres do dekodera</button></form>
<hr><h2>Lub prześlij plik</h2><form id="file-form"><label>Plik M3U lub M3U8<input id="file" type="file" accept=".m3u,.m3u8" required></label>
<p>Maksymalnie 64 MiB.</p><button id="send-file">Wyślij plik playlisty</button></form>
<p>Na koniec zatwierdź wybrane źródło zielonym przyciskiem pilota.</p></main>
<script>
function showStatus(text,state){const result=document.getElementById('result');result.textContent=text;result.style.borderColor=state==='ready'?'#35b66a':state==='error'?'#ff5964':'#e50914';}
async function waitForDownload(code){for(;;){await new Promise(resolve=>setTimeout(resolve,700));const response=await fetch('/status',{headers:{'X-IPTVPL-Code':code},cache:'no-store'});const data=await response.json();if(!response.ok)throw new Error();showStatus(data.message,data.state);if(data.state==='ready'||data.state==='error')return;}}
async function send(path,body,headers){const code=document.getElementById('code');if(!code.reportValidity())return;const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);showStatus('Wysyłanie do dekodera…','downloading');document.getElementById('result').scrollIntoView({behavior:'smooth',block:'start'});try{const response=await fetch(path,{method:'POST',headers:{...headers,'X-IPTVPL-Code':code.value},body});const data=await response.json();showStatus(data.message,response.ok?data.state:'error');if(response.status===202)await waitForDownload(code.value);}catch(error){showStatus('Brak połączenia. Sprawdź ekran importu na dekoderze.','error');}finally{buttons.forEach(b=>b.disabled=false);}}
document.getElementById('url-form').addEventListener('submit',function(e){e.preventDefault();const url=document.getElementById('playlist-url').value;send('/url',JSON.stringify({url}),{'Content-Type':'application/json'});});
document.getElementById('file-form').addEventListener('submit',function(e){e.preventDefault();const file=document.getElementById('file').files[0];if(!file)return;if(file.size>67108864){document.getElementById('result').textContent='Plik przekracza limit 64 MiB.';return;}send('/upload',file,{'Content-Type':'application/octet-stream','X-Upload-Name':encodeURIComponent(file.name)});});
</script></html>
'''



def validate_playlist_url(value):
    if not isinstance(value, str):
        raise ValueError('Wklej pełny adres HTTP lub HTTPS playlisty.')
    value = value.strip()
    if not value or len(value) > 16384 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Adres jest pusty, za długi lub zawiera odstępy. Wklej pełny URL.')
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme.lower() in ('http', 'https') and bool(parsed.hostname)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Wklej pełny adres zaczynający się od http:// lub https://.')
    return value


def import_playlist_stream(handle, name, size=None, directory=PLAYLIST_DIR, progress=None):
    name = name.replace('\\\\', '/').rsplit('/', 1)[-1]
    if not name.lower().endswith(('.m3u', '.m3u8')):
        raise ValueError('Wybierz plik z rozszerzeniem .m3u lub .m3u8.')
    if size is not None and (size <= 0 or size > MAX_BYTES):
        raise ValueError('Plik jest pusty lub przekracza limit 64 MiB.')
    stem = re.sub(r'[^\u005cw.-]', '_', name.rsplit('.', 1)[0])[:64].strip('.') or 'playlista'
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = None
    try:
        received = 0
        with tempfile.NamedTemporaryFile(prefix=stem + '-', suffix='.m3u', dir=directory, delete=False) as output:
            path = output.name
            while size is None or received < size:
                chunk = handle.read(min(65536, (size - received) if size is not None else MAX_BYTES + 1 - received))
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_BYTES:
                    raise ValueError('Plik przekracza limit 64 MiB.')
                output.write(chunk)
                if progress:
                    progress(received, size)
            if size is not None and received != size:
                raise ValueError('Przesyłanie pliku nie zostało zakończone.')
        count = count_playlist_file(path)
        return path, count
    except Exception:
        if path:
            os.unlink(path)
        raise


def import_playlist(data, name, directory=PLAYLIST_DIR):
    import io
    return import_playlist_stream(io.BytesIO(data), name, len(data), directory)


def saved_playlists(directory=PLAYLIST_DIR):
    try:
        return [(name, os.path.join(directory, name)) for name in sorted(os.listdir(directory), key=str.casefold)
                if name.lower().endswith(('.m3u', '.m3u8')) and os.path.isfile(os.path.join(directory, name))]
    except OSError:
        return []


class PlaylistUpload:
    """Temporary PIN-protected receiver, started only by the upload screen."""
    def __init__(self, host='0.0.0.0', port=8099, directory=PLAYLIST_DIR, timeout=20):
        self.code = '%06d' % secrets.randbelow(1000000)
        self.events = Queue()
        self.directory = directory
        self.failed_codes = 0
        self.closed = threading.Event()
        self.httpd = None
        self.host, self.port = host, port
        self.lock = threading.Lock()
        self.timeout = timeout
        self.job = 0
        self.state = {'state': 'idle', 'message': 'Wklej URL lub prześlij plik.'}

    def download_status(self):
        with self.lock:
            return dict(self.state)

    def begin_download(self, url):
        with self.lock:
            if self.closed.is_set() or self.state['state'] == 'downloading':
                return False
            self.job += 1
            job = self.job
            self.state = {'state': 'downloading', 'message': 'Łączenie z serwerem playlisty…', 'bytes': 0}
        def progress(received, total):
            with self.lock:
                if not self.closed.is_set() and self.job == job:
                    self.state.update({'bytes': received, 'total': total,
                                       'message': 'Pobieranie: %.2f MiB' % (received / 1048576.0)})
        def run():
            try:
                channels = load_playlist(url, timeout=self.timeout, progress=progress)
                with self.lock:
                    if self.closed.is_set() or self.job != job:
                        return
                    remember_playlist(url, channels)
                    self.events.put((url, len(channels)))
                    self.state = {'state': 'ready', 'count': len(channels),
                                  'message': 'Pobrano i sprawdzono %d pozycji. Zielony przycisk pilota: zapisz i otwórz listę.' % len(channels)}
            except Exception as error:
                with self.lock:
                    if not self.closed.is_set() and self.job == job:
                        self.state = {'state': 'error', 'message': playlist_error_message(error)}
        threading.Thread(target=run, name='IPTVPL-download', daemon=True).start()
        return True

    def start(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                pass

            def reply(self, status, data, content_type='application/json; charset=utf-8'):
                body = data.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            def message(self, status, text):
                self.reply(status, json.dumps({'message': text}))

            def do_GET(self):
                if self.path == '/status':
                    code = self.headers.get('X-IPTVPL-Code', '')
                    if not hmac.compare_digest(code.encode('utf-8'), owner.code.encode('utf-8')):
                        self.message(403, 'Nieprawidłowy kod z telewizora.')
                        return
                    self.reply(200, json.dumps(owner.download_status()))
                    return
                if self.path != '/':
                    self.message(404, 'Nie znaleziono strony.')
                else:
                    self.reply(200, PAGE, 'text/html; charset=utf-8')

            def do_POST(self):
                if self.path not in ('/upload', '/url') or owner.closed.is_set():
                    self.message(404, 'Ekran importu jest zamknięty.')
                    return
                if owner.failed_codes >= 10:
                    self.message(429, 'Zbyt wiele błędnych kodów. Zamknij i otwórz ekran importu na dekoderze.')
                    return
                code = self.headers.get('X-IPTVPL-Code', '')
                if not hmac.compare_digest(code.encode('utf-8'), owner.code.encode('utf-8')):
                    owner.failed_codes += 1
                    self.message(403, 'Nieprawidłowy kod z telewizora.')
                    return
                if self.path == '/upload' and owner.download_status()['state'] == 'downloading':
                    self.message(409, 'Trwa pobieranie playlisty. Poczekaj na wynik.')
                    return
                if self.headers.get('Transfer-Encoding'):
                    self.message(400, 'Nieobsługiwany sposób przesyłania pliku.')
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    limit = 32768 if self.path == '/url' else MAX_BYTES
                    if size <= 0 or size > limit:
                        self.message(413, 'Dane adresu są puste lub za długie.' if self.path == '/url' else 'Plik jest pusty lub przekracza limit 64 MiB.')
                        return
                    if self.path == '/url':
                        data = self.rfile.read(size)
                        if len(data) != size:
                            self.message(400, 'Przesyłanie adresu nie zostało zakończone.')
                            return
                    if self.path == '/url':
                        try:
                            payload = json.loads(data.decode('utf-8'))
                            url = validate_playlist_url(payload.get('url') if isinstance(payload, dict) else None)
                        except (UnicodeError, ValueError):
                            self.message(400, 'Nieprawidłowy adres. Wklej pełny URL HTTP/HTTPS bez odstępów.')
                            return
                        if not owner.begin_download(url):
                            self.message(409, 'Trwa pobieranie. Poczekaj na wynik lub zamknij ekran importu.')
                            return
                        self.reply(202, json.dumps(owner.download_status()))
                        return
                    def upload_progress(received, total):
                        if owner.closed.is_set():
                            raise ValueError('Ekran importu jest zamknięty.')
                        with owner.lock:
                            owner.state = {'state': 'downloading', 'bytes': received, 'total': total,
                                           'message': 'Odbieranie pliku: %.2f MiB' % (received / 1048576.0)}
                    path, count = import_playlist_stream(
                        self.rfile, unquote(self.headers.get('X-Upload-Name', '')),
                        size, owner.directory, upload_progress)
                    with owner.lock:
                        if owner.closed.is_set():
                            os.unlink(path)
                            self.message(409, 'Ekran importu jest zamknięty.')
                            return
                        owner.events.put((path, count))
                        owner.state = {'state': 'ready', 'count': count, 'message': 'Plik sprawdzony: %d pozycji. Naciśnij zielony przycisk pilota, aby użyć listy.' % count}
                    self.reply(200, json.dumps(owner.download_status()))
                except ValueError as error:
                    message = playlist_error_message(error) if str(error) == 'html_response' else str(error)
                    with owner.lock:
                        owner.state = {'state': 'error', 'message': message}
                    self.message(400, message)
                except (OSError, socket.timeout):
                    with owner.lock:
                        owner.state = {'state': 'error', 'message': 'Nie udało się odebrać lub zapisać pliku.'}
                    self.message(500, 'Nie udało się odebrać lub zapisać pliku. Spróbuj ponownie.')

        class Server(HTTPServer):
            allow_reuse_address = True
        if self.closed.is_set():
            return
        httpd = Server((self.host, self.port), Handler)
        with self.lock:
            if self.closed.is_set():
                httpd.server_close()
                return
            self.httpd = httpd
            self.port = httpd.server_port
        # handle_request + a short timeout lets stop() be nonblocking for Enigma2.
        httpd.timeout = 0.25
        def run():
            try:
                while not self.closed.is_set():
                    httpd.handle_request()
            finally:
                httpd.server_close()
        self.thread = threading.Thread(target=run, name='IPTVPL-upload', daemon=True)
        self.thread.start()

    def stop(self):
        # Never block the GUI waiting for an incomplete request body.
        self.closed.set()


def import_local_playlist(path, directory=PLAYLIST_DIR):
    with open(path, 'rb') as handle:
        return import_playlist_stream(handle, os.path.basename(path), os.fstat(handle.fileno()).st_size, directory)

