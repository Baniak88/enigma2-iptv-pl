import ast
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TREE=ast.parse((ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())
from Plugins.Extensions.IPTVPL import catalogue
from Plugins.Extensions.IPTVPL.media import media_kind, clean_title

class Screen(dict):
    def __init__(self,session):
        super().__init__(); self.session=session; self.onFirstExecBegin=[]; self.onClose=[]; self.onLayoutFinish=[]
        self.execing=True
    def close(self,*result):
        self.result=result
        for callback in self.onClose: callback()
    def hide(self): pass
class Label:
    def __init__(self,text): self.text=text; self.visible=True
    def setText(self,text): self.text=text
    def show(self): self.visible=True
    def hide(self): self.visible=False
class Timer:
    def __init__(self): self.callback=[]; self.ms=None; self.stopped=False
    def start(self,ms,*args): self.ms=ms; self.stopped=False
    def stop(self): self.stopped=True
class MoviePlayer(Screen):
    def __init__(self,session,service):
        super().__init__(session); self.last=object(); self.cur_service=service
        session.nav.playService(service)
        self.onClose.append(lambda:session.nav.playService(self.last))
    def left(self): self.seeked='left'
    def right(self): self.seeked='right'
class Ref:
    def __init__(self,kind,flags,url): self.kind=kind; self.url=url; self.data={}
    def setName(self,name): self.name=name
    def setData(self,key,value): self.data[key]=value

def ch(i,group='Sport'):
    return {'name':'TV %d'%i,'url':'https://example.com/%d'%i,'group':group}

class NavigationTests(unittest.TestCase):
    def ns(self):
        names=('bouquet_rows','find_channel_position','PlaybackContext','navigator_skin','IPTVNavigator','IPTVPlayer','playback_reference','channel_category','channel_key')
        nodes=[n for n in TREE.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
        ns={'Screen':Screen,'Label':Label,'MoviePlayer':MoviePlayer,'IPTVPlayerPanel':object,
            'fit_skin':lambda skin,**kw:skin,'ActionMap':lambda contexts,actions,prio:actions,
            'media_kind':media_kind,'clean_title':clean_title,'settings':NS(slowinternet=NS(value=True),player=NS(value='5001')),
            'eServiceReference':Ref,'deferToThread':MagicMock(),'MessageBox':NS(TYPE_ERROR=1)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<navigation>','exec'),ns)
        return ns

    def test_full_grouping_and_current_position_survives_expanding_bouquets(self):
        ns=self.ns(); channels=[ch(i,'Sport' if i%2==0 else 'Polskie') for i in range(30)]
        summary=[('Telewizja na żywo',channels)]
        ctx=ns['PlaybackContext'](summary,0,19,loader=lambda:ns['bouquet_rows'](channels))
        self.assertEqual(ctx.current()['name'],'TV 19')
        ctx.replace_rows(ctx.load())
        self.assertEqual([name for name,_ in ctx.rows],['Sport','Polskie'])
        self.assertEqual(ctx.current()['name'],'TV 19')
        ctx.move(1); self.assertEqual(ctx.current()['name'],'TV 21')
        ctx.change_bouquet(1); self.assertEqual(ctx.current()['name'],'TV 0')

    def test_navigator_pages_and_cancel_does_not_zap(self):
        ns=self.ns(); rows=[('Grupa %d'%g,[ch(g*100+i,'Grupa %d'%g) for i in range(30)]) for g in range(25)]
        ctx=ns['PlaybackContext'](rows)
        session=MagicMock(); nav=ns['IPTVNavigator'](session,ctx,focus='bouquets'); nav.render()
        nav.page(1); self.assertEqual(nav.group_index,12)
        nav.move('right'); nav.page(1); self.assertEqual(nav.channel_index,12)
        self.assertIn('13–24',nav['status'].text)
        self.assertEqual(ctx.current()['name'],'TV 0')
        session.nav.playService.assert_not_called()
        nav.play_selected(); self.assertEqual(nav.result,((12,12),))
        other=ns['IPTVNavigator'](session,ctx); other.close()
        self.assertEqual(ctx.current()['name'],'TV 0')

    def test_player_remote_aliases_debounce_buffer_and_exit_restore(self):
        ns=self.ns(); context=ns['PlaybackContext']([('Sport',[ch(i) for i in range(10)])])
        session=MagicMock()
        with patch.dict(sys.modules,{'enigma':NS(eTimer=Timer)}):
            player=ns['IPTVPlayer'](session,Ref(4097,0,'initial'),context)
        actions=player['iptv_navigation']
        for _ in range(3): actions['ChannelPlusPressed']()
        self.assertEqual(context.index,3)
        self.assertEqual(session.nav.playService.call_count,1)
        self.assertEqual(player.zap_timer.ms,250)
        player.apply_zap()
        ref=session.nav.playService.call_args.args[0]
        self.assertEqual(ref.url,'https://example.com/3'); self.assertEqual(ref.data,{7:1})
        player.panel_closed(None)
        actions['ok']()
        self.assertIs(session.openWithCallback.call_args.args[1],ns['IPTVNavigator'])
        player.channel_selected((0,8)); player.apply_zap()
        self.assertEqual(session.nav.playService.call_args.args[0].url,'https://example.com/8')
        player.finish()
        self.assertEqual(player.result[0]['name'],'TV 8')
        self.assertIs(session.nav.playService.call_args.args[0],player.last)
        self.assertTrue(player.zap_timer.stopped)

    def test_vod_arrows_seek_and_channel_keys_choose_next_item(self):
        ns=self.ns(); context=ns['PlaybackContext']([('Filmy',[ch(i,'Filmy') for i in range(3)])])
        with patch.dict(sys.modules,{'enigma':NS(eTimer=Timer)}):
            player=ns['IPTVPlayer'](MagicMock(),Ref(4097,0,'initial'),context)
        player['iptv_navigation']['right']()
        self.assertEqual(player.seeked,'right'); self.assertEqual(context.index,0)
        player['iptv_navigation']['ChannelPlusPressed']()
        self.assertEqual(context.index,1)
        player.finish(); self.assertTrue(player.zap_timer.stopped)

    def test_disk_positions_and_bouquets_without_materializing_channel_list(self):
        ns=self.ns()
        with tempfile.TemporaryDirectory() as d, patch.object(catalogue,'cache_directory',return_value=d),patch.object(catalogue,'MAX_IN_MEMORY',0):
            builder=catalogue.CatalogueBuilder()
            for i in range(100): builder.append(ch(i,'Sport' if i%2==0 else 'Polskie'))
            result=builder.finish()
            try:
                rows=ns['bouquet_rows'](result)
                position=ns['find_channel_position'](rows,ch(91,'Polskie'))
                self.assertEqual(position,(1,45))
                self.assertEqual(rows[1][1][45]['name'],'TV 91')
                self.assertLessEqual(sum(len(page) for page in result.pages.values()),64)
            finally: result.close()

    def test_navigation_skin_bounds(self):
        ns=self.ns(); root=ET.fromstring(ns['navigator_skin']())
        for node in root:
            x,y=map(int,node.get('position').split(',')); w,h=map(int,node.get('size').split(','))
            self.assertLessEqual(x+w,1280); self.assertLessEqual(y+h,720)

if __name__=='__main__': unittest.main()
