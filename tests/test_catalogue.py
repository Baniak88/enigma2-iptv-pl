import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import catalogue, playlist, sources

class CatalogueTests(unittest.TestCase):
    def test_real_playlist_over_64_mib_disk_catalogue_search_and_bounded_pages(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'provider.m3u'
            with path.open('wb') as f:
                f.write(b'#EXTM3U\n')
                comment=b'#'+b'x'*1022+b'\n'
                for _ in range(66000): f.write(comment)
                for i in range(6000):
                    group=('Sport','Filmy','Seriale')[i%3]
                    f.write(('#EXTINF:-1 group-title="%s",Kanał %d\nhttps://example.com/%s/%d\n'%(group,i,('live','movie','series')[i%3],i)).encode())
            self.assertGreater(path.stat().st_size,64*1024*1024)
            with path.open('rb') as handle:
                class Response:
                    headers={'Content-Length':str(path.stat().st_size)}
                    def geturl(self): return 'https://example.com/provider.m3u'
                    def read(self,amount):
                        if not 0 < amount <= 65536: raise AssertionError('unbounded read')
                        return handle.read(amount)
                    def __enter__(self): return self
                    def __exit__(self,*args): pass
                with patch.object(catalogue,'cache_directory',return_value=d), patch.object(playlist,'urlopen',return_value=Response()):
                    result=playlist.load_playlist('https://example.com/provider.m3u')
            self.assertTrue(result.is_disk_catalogue); self.assertEqual(len(result),6000)
            try:
                rows=result.build_rows('start')
                self.assertEqual([len(items) for _,items in rows],[2000,2000,2000])
                live=rows[0][1]
                self.assertEqual(live[0]['name'],'Kanał 0')
                self.assertEqual(live[-1]['name'],'Kanał 5997')
                for i in range(0,len(live),32): live[i]
                self.assertLessEqual(len(result.pages),4)
                self.assertLessEqual(sum(len(page) for page in result.pages.values()),64)
                search=result.build_rows('start','KANAŁ 5999')
                self.assertEqual(search[0][1][0]['name'],'Kanał 5999')
                key=hashlib.sha256(b'https://example.com/series/5999').hexdigest()
                fav=result.build_rows('favourites',favourites=[key])
                self.assertEqual(sum(len(items) for _,items in fav),1)
                self.assertEqual(fav[0][1][0]['group'],'Seriale')
            finally:
                cache=result.path; result.close()
            self.assertTrue(Path(cache).exists())  # Completed imports now survive closing.

    def test_failed_build_removes_partial_catalogue(self):
        with tempfile.TemporaryDirectory() as d, patch.object(catalogue,'cache_directory',return_value=d), patch.object(catalogue,'MAX_IN_MEMORY',2):
            builder=catalogue.CatalogueBuilder()
            for i in range(3): builder.append({'name':'TV','url':'https://example.com/%d'%i,'group':'TV'})
            self.assertTrue(list(Path(d).glob('*.sqlite')))
            builder.abort(); self.assertEqual(list(Path(d).glob('*.sqlite')),[])

    def test_low_storage_rejects_upload_and_removes_partial_file(self):
        from types import SimpleNamespace
        data=b'#EXTM3U\nhttps://example.com/live'
        with tempfile.TemporaryDirectory() as d, patch.object(sources.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError,'Brak miejsca'):
                sources.import_playlist(data,'test.m3u',d)
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_expired_or_replaced_preview_releases_disk_catalogue(self):
        with tempfile.TemporaryDirectory() as d, patch.object(catalogue,'cache_directory',return_value=d), patch.object(catalogue,'MAX_IN_MEMORY',0):
            builder=catalogue.CatalogueBuilder(); builder.append({'name':'TV','url':'https://example.com/1','group':'TV'})
            result=builder.finish(); cache=result.path
            playlist.remember_playlist('first',result)
            playlist.remember_playlist('second',[{'name':'TV'}])
            self.assertFalse(Path(cache).exists())
            playlist.take_playlist_preview('second')

if __name__=='__main__': unittest.main()
