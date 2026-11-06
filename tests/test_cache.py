import gzip
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import catalogue, playlist

class Response:
    def __init__(self,data,encoding=None):
        self.buffer=io.BytesIO(data); self.headers={'Content-Length':str(len(data))}
        if encoding: self.headers['Content-Encoding']=encoding
    def read(self,n): return self.buffer.read(n)
    def geturl(self): return 'https://example.com/list.m3u'
    def __enter__(self): return self
    def __exit__(self,*args): pass

def body(n):
    return ('#EXTM3U\n'+''.join('#EXTINF:-1,TV %d\nhttps://example.com/%d\n'%(i,i) for i in range(n))).encode()

class CacheTests(unittest.TestCase):
    def setup_cache(self,d):
        self.enterContext(patch.object(catalogue,'cache_directory',return_value=d))
        self.enterContext(patch.object(catalogue,'cache_roots',return_value=[d]))
        self.enterContext(patch.object(catalogue,'MAX_IN_MEMORY',1))

    def test_reopen_uses_saved_catalogue_without_network_or_rebuilding(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_cache(d); url='https://example.com/get.php?password=private'
            with patch.object(playlist,'urlopen',return_value=Response(body(5))) as network:
                first=playlist.load_playlist(url); path=first.path; first.close()
                self.assertEqual(network.call_count,1)
            self.assertTrue(Path(path).exists())
            with patch.object(playlist,'urlopen',side_effect=AssertionError('network called')),patch.object(catalogue.CatalogueBuilder,'append',side_effect=AssertionError('parser called')):
                second=playlist.load_playlist(url)
            self.assertTrue(second.from_cache); self.assertEqual(len(second),5)
            self.assertEqual(second.build_rows('start')[0][1][4]['name'],'TV 4')
            second.close()
            for record in Path(d).glob('*.json'):
                self.assertNotIn('password',record.read_text())
                self.assertNotIn('private',record.read_text())

    def test_force_refresh_keeps_active_old_database_then_retires_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_cache(d); url='https://example.com/refresh'
            with patch.object(playlist,'urlopen',return_value=Response(body(3))): old=playlist.load_playlist(url)
            old_path=old.path
            with patch.object(playlist,'urlopen',return_value=Response(body(6))) as network:
                fresh=playlist.load_playlist(url,force=True)
            self.assertEqual(network.call_count,1); self.assertEqual(len(fresh),6)
            self.assertTrue(Path(old_path).exists())
            self.assertEqual(old.build_rows('start')[0][1][0]['name'],'TV 0')
            old.close(); self.assertFalse(Path(old_path).exists()); fresh.close()
            cached=playlist.load_playlist(url); self.assertEqual(len(cached),6); cached.close()
            with patch.object(playlist,'urlopen',return_value=Response(body(1))): small=playlist.load_playlist(url,force=True)
            self.assertIsInstance(small,list)
            self.assertIsNone(catalogue.load_cached_catalogue(url))

    def test_cache_expiry_local_change_and_corruption_fall_back(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_cache(d); url='https://example.com/expire'
            with patch.object(playlist,'urlopen',return_value=Response(body(3))): cached=playlist.load_playlist(url)
            path=cached.path; cached.close()
            now=time.time()
            with patch.object(catalogue.time,'time',return_value=now+90000):
                self.assertIsNone(catalogue.load_cached_catalogue(url))
            Path(path).write_bytes(b'not a sqlite database')
            self.assertIsNone(catalogue.load_cached_catalogue(url))
            local=Path(d)/'local.m3u'; local.write_bytes(body(3))
            result=playlist.load_playlist(str(local)); result.close()
            hit=playlist.load_playlist(str(local)); self.assertTrue(hit.from_cache); hit.close()
            local.write_bytes(body(4))
            changed=playlist.load_playlist(str(local)); self.assertFalse(changed.from_cache); self.assertEqual(len(changed),4); changed.close()

    def test_unfiltered_bouquets_use_saved_counts_instead_of_scanning_channels(self):
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as d:
            self.setup_cache(d)
            with patch.object(playlist,'urlopen',return_value=Response(body(5))): result=playlist.load_playlist('https://example.com/counts')
            trace=[]
            def connect():
                connection=sqlite3.connect(result.path)
                connection.set_trace_callback(trace.append)
                return closing(connection)
            with patch.object(result,'connect',side_effect=connect):
                start=result.build_rows('start'); groups=result.build_rows('all')
            self.assertEqual(sum(len(items) for _,items in start),5)
            self.assertEqual(sum(len(items) for _,items in groups),5)
            self.assertTrue(trace)
            self.assertTrue(all('group_summary' in sql for sql in trace))
            result.close()

    def test_gzip_supported_and_decompressed_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_cache(d)
            raw=body(3); compressed=gzip.compress(raw); progress=[]
            with patch.object(playlist,'urlopen',return_value=Response(compressed,'gzip')) as network:
                result=playlist.load_playlist('https://example.com/gzip',progress=lambda n,total:progress.append((n,total)))
            self.assertEqual(len(result),3); result.close()
            self.assertEqual(network.call_args.args[0].get_header('Accept-encoding'),'gzip')
            self.assertIn((len(raw),None),progress)
            with patch.object(playlist,'MAX_BYTES',20),patch.object(playlist,'urlopen',return_value=Response(compressed,'gzip')):
                with self.assertRaises(playlist.PlaylistLimitError): playlist.load_playlist('https://example.com/gzip',force=True)

if __name__=='__main__': unittest.main()
