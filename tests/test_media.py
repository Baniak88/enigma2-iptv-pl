import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Plugins.Extensions.IPTVPL import media, catalogue, playlist

def item(name,url,group,logo=''):
    value={'name':name,'url':'https://example.com'+url,'group':group}
    if logo:value['logo']=logo
    return value

FIXTURE=[item('PL| CANAL+ PREMIUM FHD','/live/u/p/1.ts','PL| FILMOWE'),
         item('France Info','/live/u/p/2.m3u8','Informacyjne'),
         item('##### PL FILMOWE #####','/live/u/p/3.ts','PL| FILMOWE'),
         item('UK| APPLE TV+ SERIES info','/live/u/p/4.ts','UK| APPLE TV+ SERIES'),
         item('UK| APPLE TV+ SERIES 1','/live/u/p/5.ts','UK| APPLE TV+ SERIES'),
         item('PL| Film A (2026)','/movie/u/p/6.mp4','PL| Akcja','https://example.com/film.jpg'),
         item('Film B','/other/7.mkv','Dramat'),
         item('PL| Detektyw S01E10 - Finał','/series/u/p/8.mp4','PL| Seriale','https://example.com/show.jpg'),
         item('PL| Detektyw S01E02 - Trop','/series/u/p/9.mp4','PL| Seriale'),
         item('PL| Detektyw S02E01 - Powrót','/series/u/p/10.ts','PL| Seriale')]

class MediaTests(unittest.TestCase):
    def test_address_wins_over_live_film_group_and_placeholder_sections(self):
        self.assertEqual(media.media_kind(FIXTURE[0]),'live')
        self.assertEqual(media.media_kind(item('Film TV','/live/series/password/1.ts','Filmy')),'live')
        self.assertEqual(media.media_kind(item('Film TV','/live/u%2Fseries%2F/p/1.ts','Filmy')),'live')
        self.assertFalse(media.is_separator(FIXTURE[1]))
        for entry in FIXTURE[2:5]:self.assertTrue(media.is_separator(entry))
        self.assertEqual(media.media_kind(FIXTURE[5]),'movies')
        self.assertEqual(media.media_kind(FIXTURE[6]),'movies')
        self.assertEqual(media.media_kind(FIXTURE[-1]),'series')
        named=media.media_metadata(FIXTURE[7])
        self.assertEqual((named['series_title'],named['season'],named['episode'],named['display_title']),('Detektyw',1,10,'Finał'))

    def test_parser_filters_separators_without_losing_following_metadata(self):
        text='#EXTM3U\n'+''.join('#EXTINF:-1 group-title="%s",%s\n%s\n'%(c['group'],c['name'],c['url']) for c in FIXTURE)
        result=playlist.parse_m3u(text)
        self.assertEqual(len(result),7)
        self.assertFalse(any(c['name'].startswith('#####') for c in result))
        self.assertTrue(any(c['name']=='France Info' for c in result))
        self.assertEqual(result[-1]['group'],'PL| Seriale')

    def check_library(self,channels):
        count,movies=media.vod_page(channels,'movies')
        self.assertEqual(count,2)
        self.assertEqual(movies[0]['display_title'],'Film A (2026)')
        count,shows=media.vod_page(channels,'series')
        self.assertEqual(count,1);self.assertEqual(shows[0]['display_title'],'Detektyw')
        self.assertEqual(shows[0]['episode_count'],3)
        seasons=media.series_seasons(channels,shows[0])
        self.assertEqual([name for name,_ in seasons],['Sezon 1','Sezon 2'])
        self.assertEqual([media.media_metadata(c)['episode'] for c in seasons[0][1]],[2,10])
        self.assertEqual(media.vod_page(channels,'series',query='DETEKTYW')[0],1)
        self.assertEqual(media.vod_groups(channels,'series')[0][2],1)
        self.assertEqual(len(media.movie_sequence(channels)),2)

    def test_small_playlist_series_and_movie_library(self):
        self.check_library(FIXTURE)

    def test_disk_library_matches_small_and_orders_episodes_numerically(self):
        with tempfile.TemporaryDirectory() as d,patch.object(catalogue,'cache_directory',return_value=d):
            builder=catalogue.CatalogueBuilder(force_disk=True)
            for entry in FIXTURE:builder.append(entry)
            result=builder.finish()
            try:
                self.assertEqual(len(result),7)
                self.check_library(result)
                show=media.vod_page(result,'series')[1][0]
                seasons=media.series_seasons(result,show)
                self.assertEqual(seasons[0][1].position_of(FIXTURE[7]),1)
                mixed=result.build_rows('live')
                self.assertEqual(sum(len(rows) for _,rows in mixed),2)
            finally:result.close()

    def test_v2_cache_is_reclassified_locally_without_network(self):
        with tempfile.TemporaryDirectory() as d,patch.object(catalogue,'cache_directory',return_value=d),patch.object(catalogue,'cache_roots',return_value=[d]):
            path=Path(d)/'catalogue-old.sqlite'
            connection=sqlite3.connect(path)
            connection.execute('CREATE TABLE channels (id INTEGER PRIMARY KEY,name TEXT,url TEXT,group_name TEXT,logo TEXT,category TEXT,search TEXT,favourite TEXT)')
            for c in FIXTURE:
                connection.execute('INSERT INTO channels (name,url,group_name,logo,category,search,favourite) VALUES (?,?,?,?,?,?,?)',(c['name'],c['url'],c['group'],c.get('logo',''),'movies',c['name'].casefold(),hashlib.sha256(c['url'].encode()).hexdigest()))
            connection.execute('CREATE TABLE group_summary AS SELECT group_name,category,COUNT(*) AS amount,MIN(id) AS first_id FROM channels GROUP BY group_name')
            connection.commit();connection.close()
            source='https://example.com/get.php?username=test&password=private'
            record=Path(d)/catalogue.cache_name(source)
            saved=time.time()-300
            record.write_text(json.dumps({'schema':2,'file':path.name,'count':len(FIXTURE),'saved':saved,'fingerprint':None}))
            with patch.object(playlist,'urlopen',side_effect=AssertionError('unexpected download')):
                result=playlist.load_playlist(source)
            try:
                self.assertTrue(result.from_cache);self.assertEqual(len(result),7)
                self.check_library(result)
                meta=json.loads(record.read_text())
                self.assertEqual(meta['schema'],3);self.assertEqual(meta['saved'],saved)
                self.assertFalse(path.exists())
            finally:result.close()

if __name__=='__main__':unittest.main()
