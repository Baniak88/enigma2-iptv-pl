import ast
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from Plugins.Extensions.IPTVPL import media
TREE=ast.parse((ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())

class Screen(dict):
    def __init__(self,session):
        super().__init__();self.session=session;self.onClose=[];self.onFirstExecBegin=[];self.onLayoutFinish=[]
    def close(self,*args):
        self.result=args
        for fn in self.onClose:fn()
class Label:
    def __init__(self,text=''):self.text=text;self.visible=True;self.instance=MagicMock()
    def setText(self,text):self.text=text
    def show(self):self.visible=True
    def hide(self):self.visible=False
class Deferred:
    def __init__(self,result):self.result=result
    def addCallbacks(self,good,bad):return good(self.result)

MOVIES=[{'name':'PL| Film %d'%i,'url':'https://example.com/movie/u/p/%d.mp4'%i,'group':'Akcja' if i%2==0 else 'Dramat'} for i in range(20)]
EPISODES=[{'name':'PL| Serial S%02dE%02d - Odcinek %d'%(season,episode,episode),'url':'https://example.com/series/u/p/%d.mp4'%(season*100+episode),'group':'Seriale'} for season in (1,2) for episode in (1,2,10)]

class LibraryTests(unittest.TestCase):
    def build(self,kind):
        names=('library_skin','IPTVLibrary','PlaybackContext','find_channel_position','channel_key','channel_category')
        nodes=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        ns={'Screen':Screen,'Label':Label,'Pixmap':Label,'fit_skin':lambda skin,**kw:skin,
            'ePicLoad':MagicMock(),'ActionMap':lambda ctx,actions,prio:actions,
            'settings':NS(slowinternet=NS(value=False)),'IPTVKeyboard':object,'IPTVNavigator':object,'IPTVPlayer':object,
            'playback_reference':lambda channel:channel,'MessageBox':NS(TYPE_INFO=1),
            'vod_groups':media.vod_groups,'vod_page':media.vod_page,'series_seasons':media.series_seasons,
            'movie_sequence':media.movie_sequence,'media_metadata':media.media_metadata,'media_kind':media.media_kind,
            'cached_artwork':MagicMock(),'playlist_error_message':lambda error:'Błąd'}
        ns['deferToThread']=lambda fn,*args,**kw:Deferred(fn(*args,**kw))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<library>','exec'),ns)
        view=ns['IPTVLibrary'](MagicMock(),MOVIES+EPISODES,kind)
        view.picload=None
        view.start()
        return view,ns

    def test_movies_grid_categories_paging_and_playback(self):
        view,ns=self.build('movies')
        self.assertEqual(view.total,20);self.assertEqual(len(view.items),8)
        self.assertEqual(view['name0'].text,'Film 0')
        view.choose();self.assertEqual(view.focus,'grid')
        view.page(1);self.assertEqual(view.index,8);self.assertEqual(view['name0'].text,'Film 8')
        view.choose()
        call=view.session.openWithCallback.call_args
        self.assertIs(call.args[1],ns['IPTVPlayer'])
        self.assertTrue(call.args[2]['url'].endswith('/8.mp4'))
        self.assertEqual(len(call.args[3].rows[0][1]),20)
        view.player_closed(MOVIES[8]);self.assertFalse(view.player_open)

    def test_category_choice_filters_grid_once_and_resets_paging(self):
        view,ns=self.build('movies')
        view.choose();view.page(1);self.assertEqual(view.index,8)
        view.move('left');self.assertEqual(view.focus,'groups')
        view.genre_index=1
        original=ns['deferToThread'];ns['deferToThread']=MagicMock(side_effect=original)
        view.move('right')
        self.assertEqual(view.group,'Akcja');self.assertEqual(view.index,0)
        self.assertEqual(view.total,10)
        self.assertTrue(all(c['group']=='Akcja' for c in view.items))
        self.assertEqual(ns['deferToThread'].call_count,1)

    def test_series_are_titles_then_seasons_then_real_episodes(self):
        view,ns=self.build('series')
        self.assertEqual(view.total,1);self.assertEqual(view.items[0]['episode_count'],6)
        self.assertEqual(view['name0'].text,'Serial')
        view.choose();view.choose()
        call=view.session.openWithCallback.call_args
        self.assertIs(call.args[1],ns['IPTVNavigator'])
        context=call.args[2]
        self.assertEqual([title for title,_ in context.rows],['Sezon 1','Sezon 2'])
        self.assertEqual([media.media_metadata(c)['episode'] for c in context.rows[0][1]],[1,2,10])
        view.episode_chosen((1,2))
        call=view.session.openWithCallback.call_args
        self.assertIs(call.args[1],ns['IPTVPlayer'])
        self.assertTrue(call.args[2]['url'].endswith('/210.mp4'))
        view.player_closed(call.args[2])
        self.assertIs(view.session.openWithCallback.call_args.args[1],ns['IPTVNavigator'])

    def test_search_cancel_stale_results_and_missing_data(self):
        view,_=self.build('movies')
        view.searched('Film 19');self.assertEqual(view.total,1);self.assertEqual(view['name0'].text,'Film 19')
        view.searched(None);self.assertEqual(view.total,1)
        view.searched('nie-ma');self.assertEqual(view.total,0)
        self.assertIn('Brak tytułów',view['detail'].text)
        view.close();old=view.items
        view.page_ready((20,MOVIES[:8]),view.request-1)
        self.assertEqual(view.items,old)

    def test_art_decode_failure_and_layout_bounds(self):
        view,_=self.build('movies')
        view.art_busy=True;view.decoding=(0,view.art_generation,'https://example.com/cover')
        view.picload=MagicMock();view.picload.getData.side_effect=RuntimeError('bad image')
        view.art_decoded();self.assertFalse(view.art_busy)
        root=ET.fromstring(view.skin)
        for node in root:
            x,y=map(int,node.get('position').split(','));w,h=map(int,node.get('size').split(','))
            self.assertLessEqual(x+w,1280);self.assertLessEqual(y+h,720)

if __name__=='__main__':unittest.main()
