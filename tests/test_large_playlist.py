import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import playlist, sources

class LargeTests(unittest.TestCase):
    def test_real_9_mib_playlist_download_and_usb_import_read_in_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            original=Path(directory)/'large.m3u'
            with original.open('wb') as f:
                f.write(b'#EXTM3U\n')
                for _ in range(10000): f.write(b'# '+b'x'*990+b'\n')
                f.write('#EXTINF:-1,Kanał Polska\nhttps://example.com/live'.encode('utf-8'))
            size=original.stat().st_size
            self.assertGreater(size,8*1024*1024)
            amounts=[]
            with original.open('rb') as handle:
                class Response:
                    headers={'Content-Length':str(size)}
                    def geturl(self): return 'https://example.com/list.m3u'
                    def read(self,amount):
                        self_check=0 < amount <= 65536
                        if not self_check: raise AssertionError('unbounded read')
                        amounts.append(amount)
                        return handle.read(amount)
                    def __enter__(self): return self
                    def __exit__(self,*args): pass
                progress=[]
                with patch.object(playlist,'urlopen',return_value=Response()):
                    result=playlist.load_playlist('https://example.com/list.m3u',progress=lambda n,total:progress.append(n))
            self.assertEqual(result[0]['name'],'Kanał Polska')
            self.assertEqual(len(result),1); self.assertEqual(progress[-1],size)
            self.assertGreater(len(amounts),100)
            path,count=sources.import_local_playlist(str(original),str(Path(directory)/'saved'))
            self.assertEqual(count,1); self.assertEqual(os.path.getsize(path),size)

    def test_size_line_and_channel_limits_are_explicit_without_truncation(self):
        import io
        with patch.object(playlist,'MAX_BYTES',20), self.assertRaises(playlist.PlaylistLimitError):
            list(playlist.playlist_lines(io.BytesIO(b'x'*21)))
        with patch.object(playlist,'MAX_LINE_BYTES',20), self.assertRaises(playlist.PlaylistLimitError):
            list(playlist.playlist_lines(io.BytesIO(b'x'*21)))
        with patch.object(playlist,'MAX_CHANNELS',2), self.assertRaises(playlist.PlaylistLimitError):
            playlist.parse_m3u('https://example.com/1\nhttps://example.com/2\nhttps://example.com/3')
        with tempfile.TemporaryDirectory() as d:
            with patch.object(sources,'MAX_BYTES',20), self.assertRaises(ValueError):
                sources.import_playlist_stream(io.BytesIO(b'x'*21),'test.m3u',directory=d)
            self.assertEqual(os.listdir(d),[])

    def test_mobile_limit_matches_backend(self):
        self.assertEqual(playlist.MAX_BYTES,64*1024*1024)
        self.assertEqual(sources.MAX_BYTES,playlist.MAX_BYTES)
        self.assertIn('67108864',sources.PAGE)
        self.assertNotIn('8 MiB',sources.PAGE)
        self.assertIn('64 MiB',playlist.playlist_error_message(playlist.PlaylistLimitError('Lista przekracza limit 64 MiB.')))

if __name__=='__main__': unittest.main()
