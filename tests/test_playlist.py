import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('playlist', Path(__file__).resolve().parents[1] / 'Plugins/Extensions/IPTVPL/playlist.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PlaylistTests(unittest.TestCase):
    def test_metadata_bom_and_quoted_comma(self):
        result = p.parse_m3u('\ufeff#EXTM3U\n#EXTINF:-1 tvg-name="A,B" group-title="Polskie",TV Polska\nhttps://example.com/live\n')
        self.assertEqual(result, [{'name': 'TV Polska', 'group': 'Polskie', 'url': 'https://example.com/live'}])

    def test_relative_url_and_extgrp(self):
        result = p.parse_m3u('#EXTINF:-1,TV\n#EXTGRP:Sport\n../live.m3u8', 'https://example.com/list/index.m3u')
        self.assertEqual(result[0]['url'], 'https://example.com/live.m3u8')
        self.assertEqual(result[0]['group'], 'Sport')

    def test_invalid_protocol_and_metadata_reset(self):
        result = p.parse_m3u('#EXTINF:-1,Bad\nfile:///etc/passwd\nhttps://example.com/a')
        self.assertEqual(result[0]['name'], 'Kanał 1')

    def test_local_file(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b'#EXTM3U\nhttps://example.com/live\n')
            f.flush()
            self.assertEqual(len(p.load_playlist(f.name)), 1)

    def test_empty_and_oversized(self):
        with tempfile.NamedTemporaryFile() as f:
            with self.assertRaises(ValueError):
                p.load_playlist(f.name)
            f.write(b'x' * 50)
            f.flush()
            with patch.object(p, 'MAX_BYTES', 20), self.assertRaises(ValueError):
                p.load_playlist(f.name)

    def test_remote_redirect_base_and_timeout(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'#EXTINF:-1,TV\nstream.m3u8'
        response.geturl.return_value = 'https://example.com/new/list.m3u'
        with patch.object(p, 'urlopen', return_value=response) as opener:
            self.assertEqual(p.load_playlist('https://example.com/list')[0]['url'], 'https://example.com/new/stream.m3u8')
            self.assertEqual(opener.call_args.kwargs['timeout'], 20)


if __name__ == '__main__':
    unittest.main()
