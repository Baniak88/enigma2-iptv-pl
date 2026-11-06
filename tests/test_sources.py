import ast
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock
from urllib.parse import quote
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Plugins.Extensions.IPTVPL.sources import PlaylistUpload, import_playlist, import_local_playlist, saved_playlists

DATA=b'#EXTM3U\n#EXTINF:-1 group-title="Polskie",TV\nhttps://example.com/live\n'

class SourceTests(unittest.TestCase):
    def test_managed_import_sanitizes_name_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            p,count=import_playlist(DATA,'../../Moja lista.m3u',d)
            self.assertEqual(count,1); self.assertEqual(Path(p).parent,Path(d))
            self.assertEqual(Path(p).read_bytes(),DATA)
            self.assertEqual(os.stat(p).st_mode & 0o777,0o600)
            second,_=import_playlist(DATA,'../../Moja lista.m3u',d)
            self.assertNotEqual(p,second); self.assertEqual(len(saved_playlists(d)),2)

    def test_invalid_empty_oversized_extension(self):
        with tempfile.TemporaryDirectory() as d:
            for content,name in [(b'','a.m3u'),(b'<html>error</html>','a.m3u'),(DATA,'a.txt'),(b'x'*(8*1024*1024+1),'a.m3u')]:
                with self.assertRaises(ValueError): import_playlist(content,name,d)
            self.assertEqual(saved_playlists(d),[])

    def test_local_import_copies_usb_file(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/'usb.m3u8'; original.write_bytes(DATA)
            p,_=import_local_playlist(str(original),str(Path(d)/'saved'))
            original.unlink()
            self.assertEqual(Path(p).read_bytes(),DATA)

    def receiver(self,d):
        r=PlaylistUpload('127.0.0.1',0,d); r.start()
        def cleanup():
            r.stop(); r.thread.join(2)
        self.addCleanup(cleanup)
        return r

    def request(self,r,method,path='/',data=None,code=None,name='Lista.m3u'):
        connection=http.client.HTTPConnection('127.0.0.1',r.port,timeout=3)
        headers={'X-IPTVPL-Code':code or r.code,'X-Upload-Name':quote(name)}
        connection.request(method,path,body=data,headers=headers)
        response=connection.getresponse(); status=response.status; body=response.read()
        connection.close(); return status,body

    def test_real_http_page_pin_upload_and_event(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.receiver(d)
            status,page=self.request(r,'GET')
            self.assertEqual(status,200); self.assertIn(b'type="file"',page)
            self.assertNotIn(r.code.encode(),page)
            status,_=self.request(r,'POST','/upload',DATA,code='wrong')
            self.assertEqual(status,403); self.assertEqual(saved_playlists(d),[])
            status,reply=self.request(r,'POST','/upload',DATA)
            self.assertEqual(status,200)
            p,count=r.events.get(timeout=1)
            self.assertEqual(count,1); self.assertEqual(Path(p).read_bytes(),DATA)
            self.assertIn('zielony',json.loads(reply)['message'])
            r.stop(); r.thread.join(2)
            self.assertFalse(r.thread.is_alive())

    def test_wrong_pin_rate_limit_and_malformed_playlist(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.receiver(d)
            self.assertEqual(self.request(r,'POST','/upload',b'bad')[0],400)
            for _ in range(10): self.assertEqual(self.request(r,'POST','/upload',DATA,code='wrong')[0],403)
            self.assertEqual(self.request(r,'POST','/upload',DATA)[0],429)
            self.assertEqual(saved_playlists(d),[])

    def test_new_screens_xml_and_poll_on_gui(self):
        tree=ast.parse((ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())
        for cls in tree.body:
            if isinstance(cls,ast.ClassDef) and cls.name.startswith('IPTVPlaylist'):
                for stmt in cls.body:
                    if isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='skin' for t in stmt.targets):
                        ET.fromstring(ast.literal_eval(stmt.value))
        self.assertNotIn('settings.source',Path(ROOT/'Plugins/Extensions/IPTVPL/sources.py').read_text())

if __name__=='__main__': unittest.main()
