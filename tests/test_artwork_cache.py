from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import media,catalogue,playlist

class ArtworkTests(unittest.TestCase):
    def test_cover_download_once_and_cache_only_never_uses_network(self):
        with tempfile.TemporaryDirectory() as d,patch.object(catalogue,'cache_directory',return_value=d),patch.object(catalogue,'cache_roots',return_value=[d]):
            url='https://example.com/poster.jpg?token=private'
            with patch.object(playlist,'load_artwork',side_effect=AssertionError('unexpected network')):
                self.assertIsNone(media.cached_artwork(url,cache_only=True))
            incoming=Path(d)/'download.img';incoming.write_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*30)
            with patch.object(playlist,'load_artwork',return_value=str(incoming)) as download:
                path=media.cached_artwork(url)
            self.assertEqual(download.call_count,1);self.assertFalse(incoming.exists());self.assertTrue(Path(path).exists())
            self.assertNotIn('private',path)
            with patch.object(playlist,'load_artwork',side_effect=AssertionError('unexpected network')),patch.object(catalogue,'cache_directory',side_effect=AssertionError('cache lookup must not require new storage')):
                self.assertEqual(media.cached_artwork(url,cache_only=True),path)

if __name__=='__main__':unittest.main()
