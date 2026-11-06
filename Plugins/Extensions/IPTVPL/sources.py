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
from urllib.parse import unquote

from .playlist import MAX_BYTES, parse_m3u

PLAYLIST_DIR = '/etc/enigma2/iptvpl/playlists'

PAGE = '''<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPTV PL — dodaj playlistę</title><style>
body{background:#101010;color:#fff;font:18px system-ui;margin:0;padding:28px}main{max-width:520px;margin:30px auto}h1{font-size:30px}b{color:#ef3340}label{display:block;margin-top:24px}input,button{box-sizing:border-box;width:100%;padding:16px;margin-top:10px;border-radius:10px;border:1px solid #555;font:inherit;background:#262626;color:#fff}button{background:#e50914;border:0;font-weight:700}p{color:#bbb;line-height:1.5}#result{white-space:pre-wrap}button:disabled{opacity:.5}</style>
<main><b>IPTV PL</b><h1>Dodaj playlistę</h1><p>Telefon i dekoder muszą być w tej samej sieci Wi-Fi. Wpisz kod widoczny na telewizorze.</p>
<form id="form"><label>Kod z telewizora<input id="code" inputmode="numeric" autocomplete="off" pattern="[0-9]{6}" maxlength="6" required></label>
<label>Plik M3U lub M3U8<input id="file" type="file" accept=".m3u,.m3u8" required></label>
<p>Maksymalnie 8 MiB. Po przesłaniu zatwierdź playlistę zielonym przyciskiem pilota.</p><button id="send">Wyślij playlistę</button></form><p id="result" role="status" aria-live="polite"></p></main>
<script>
document.getElementById('form').addEventListener('submit',async function(e){e.preventDefault();const f=document.getElementById('file').files[0];const r=document.getElementById('result');const b=document.getElementById('send');if(!f)return;if(f.size>8388608){r.textContent='Plik przekracza limit 8 MiB.';return;}b.disabled=true;r.textContent='Przesyłanie…';try{const reply=await fetch('/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-IPTVPL-Code':document.getElementById('code').value,'X-Upload-Name':encodeURIComponent(f.name)},body:f});const data=await reply.json();r.textContent=data.message;}catch(err){r.textContent='Brak połączenia. Sprawdź, czy ekran importu jest nadal otwarty na dekoderze.';}finally{b.disabled=false;}});
</script></html>'''


def import_playlist(data, name, directory=PLAYLIST_DIR):
    if len(data) > MAX_BYTES:
        raise ValueError('Plik przekracza limit 8 MiB.')
    name = name.replace('\\', '/').rsplit('/', 1)[-1]
    if not name.lower().endswith(('.m3u', '.m3u8')):
        raise ValueError('Wybierz plik z rozszerzeniem .m3u lub .m3u8.')
    channels = parse_m3u(data.decode('utf-8-sig', errors='replace'))
    if not channels:
        raise ValueError('Plik nie zawiera obsługiwanych adresów kanałów M3U.')
    stem = re.sub(r'[^\w.-]', '_', name.rsplit('.', 1)[0])[:64].strip('.') or 'playlista'
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix=stem + '-', suffix='.m3u', dir=directory, delete=False) as handle:
            path = handle.name
            handle.write(data)
        return path, len(channels)
    except Exception:
        if path:
            os.unlink(path)
        raise


def saved_playlists(directory=PLAYLIST_DIR):
    try:
        return [(name, os.path.join(directory, name)) for name in sorted(os.listdir(directory), key=str.casefold)
                if name.lower().endswith(('.m3u', '.m3u8')) and os.path.isfile(os.path.join(directory, name))]
    except OSError:
        return []


class PlaylistUpload:
    """Temporary PIN-protected receiver, started only by the upload screen."""
    def __init__(self, host='0.0.0.0', port=8099, directory=PLAYLIST_DIR):
        self.code = '%06d' % secrets.randbelow(1000000)
        self.events = Queue()
        self.directory = directory
        self.failed_codes = 0
        self.closed = threading.Event()
        self.httpd = None
        self.host, self.port = host, port
        self.lock = threading.Lock()

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
                if self.path != '/':
                    self.message(404, 'Nie znaleziono strony.')
                else:
                    self.reply(200, PAGE, 'text/html; charset=utf-8')

            def do_POST(self):
                if self.path != '/upload' or owner.closed.is_set():
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
                if self.headers.get('Transfer-Encoding'):
                    self.message(400, 'Nieobsługiwany sposób przesyłania pliku.')
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if size <= 0 or size > MAX_BYTES:
                        self.message(413, 'Plik jest pusty lub przekracza limit 8 MiB.')
                        return
                    data = self.rfile.read(size)
                    if len(data) != size:
                        self.message(400, 'Przesyłanie pliku nie zostało zakończone.')
                        return
                    # Serialize close with commit, so a closed screen never accepts a new file.
                    with owner.lock:
                        if owner.closed.is_set():
                            self.message(409, 'Ekran importu jest zamknięty.')
                            return
                        path, count = import_playlist(data, unquote(self.headers.get('X-Upload-Name', '')), owner.directory)
                        if owner.closed.is_set():
                            os.unlink(path)
                            self.message(409, 'Ekran importu jest zamknięty.')
                            return
                        owner.events.put((path, count))
                    self.message(200, 'Przesłano %d pozycji. Naciśnij zielony przycisk na pilocie, aby użyć tej playlisty.' % count)
                except ValueError as error:
                    self.message(400, str(error))
                except (OSError, socket.timeout):
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
        data = handle.read(MAX_BYTES + 1)
    return import_playlist(data, os.path.basename(path), directory)
