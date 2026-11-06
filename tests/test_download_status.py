import http.client
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import sources, playlist

class StatusTests(unittest.TestCase):
    def request(self,r,path,code):
        c=http.client.HTTPConnection('127.0.0.1',r.port,timeout=2)
        c.request('GET',path,headers={'X-IPTVPL-Code':code})
        res=c.getresponse(); status=res.status; body=json.loads(res.read()); c.close()
        return status,body

    def test_download_progress_ready_status_pin_and_cached_result(self):
        gate=threading.Event(); progress_sent=threading.Event()
        url='https://example.com/get.php?password=do-not-display'
        channels=[{'name':'TV','url':'https://example.com/live','group':'TV'}]
        def loader(source,timeout,progress):
            progress(65536,200000); progress_sent.set(); gate.wait(2)
            return channels
        with tempfile.TemporaryDirectory() as d:
            r=sources.PlaylistUpload('127.0.0.1',0,d); r.start()
            try:
                with patch.object(sources,'load_playlist',side_effect=loader):
                    self.assertTrue(r.begin_download(url)); self.assertTrue(progress_sent.wait(1))
                    self.assertFalse(r.begin_download(url))
                    self.assertEqual(self.request(r,'/status','bad')[0],403)
                    status,body=self.request(r,'/status',r.code)
                    self.assertEqual(body['state'],'downloading'); self.assertEqual(body['bytes'],65536)
                    self.assertNotIn('password',json.dumps(body))
                    gate.set(); self.assertEqual(r.events.get(timeout=1),(url,1))
                _,body=self.request(r,'/status',r.code)
                self.assertEqual((body['state'],body['count']),('ready',1))
                self.assertEqual(playlist.take_playlist_preview(url),channels)
                self.assertIsNone(playlist.take_playlist_preview(url))
            finally:
                gate.set(); r.stop(); r.thread.join(2)

    def test_failure_explains_http_code_without_password_and_no_ready_event(self):
        error=HTTPError('https://example.com/?password=secret',403,'Forbidden',None,None)
        r=sources.PlaylistUpload()
        with patch.object(sources,'load_playlist',side_effect=error):
            done=threading.Event()
            original=playlist.playlist_error_message
            def message(e):
                value=original(e); done.set(); return value
            with patch.object(sources,'playlist_error_message',side_effect=message):
                r.begin_download('https://example.com/?password=secret')
                self.assertTrue(done.wait(1))
        state=r.download_status()
        self.assertEqual(state['state'],'error'); self.assertIn('403',state['message'])
        self.assertNotIn('secret',state['message']); self.assertTrue(r.events.empty())
        r.stop()

    def test_streamed_read_reports_bytes_and_rejects_html(self):
        response=MagicMock(); response.__enter__.return_value=response
        data=b'#EXTM3U\nhttps://example.com/live\n'
        response.read.side_effect=io.BytesIO(data).read
        response.headers={'Content-Length':str(len(data))}
        response.geturl.return_value='https://example.com/list'
        progress=MagicMock()
        with patch.object(playlist,'urlopen',return_value=response):
            channels=playlist.load_playlist('https://example.com/list',progress=progress)
        self.assertEqual(len(channels),1)
        progress.assert_any_call(len(data),len(data))
        response.read.side_effect=io.BytesIO(b'<!doctype html><html>Login</html>').read
        with patch.object(playlist,'urlopen',return_value=response), self.assertRaises(ValueError) as error:
            playlist.load_playlist('https://example.com/list')
        self.assertIn('stronę WWW',playlist.playlist_error_message(error.exception))
        self.assertIn('czas',playlist.playlist_error_message(socket.timeout()))

if __name__=='__main__': unittest.main()
