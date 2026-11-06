import ast
import importlib.util
import os
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TREE=ast.parse((ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())
spec=importlib.util.spec_from_file_location('Plugins.Extensions.IPTVPL.playlist',ROOT/'Plugins/Extensions/IPTVPL/playlist.py')
playlist=importlib.util.module_from_spec(spec)
spec.loader.exec_module(playlist)

class Screen(dict):
    def __init__(self,session):
        super().__init__(); self.session=session; self.onLayoutFinish=[]; self.onClose=[]; self.onFirstExecBegin=[]
        self.closed=False
    def close(self): self.closed=True

class Label:
    def __init__(self,text=''):
        self.text=text; self.visible=True; self.instance=MagicMock()
    def setText(self,text): self.text=text
    def show(self): self.visible=True
    def hide(self): self.visible=False

class Ref:
    def __init__(self,kind,flags,url): self.kind=kind; self.data={}
    def setData(self,key,value): self.data[key]=value
    def setName(self,name): self.name=name


def channel(i,group='Sport',logo=''):
    c={'name':'Kanał %d'%i,'url':'https://example.com/%d'%i,'group':group}
    if logo: c['logo']=logo
    return c

class StreamingTests(unittest.TestCase):
    def build(self,slow=False):
        names=('fit_skin','streaming_skin','channel_key','channel_category','bouquet_rows','find_channel_position','PlaybackContext','playback_reference','IPTVHome','IPTVBrowser')
        nodes=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        settings=NS(source=NS(value='/nonexistent/iptv.m3u'),slowinternet=NS(value=slow),player=NS(value='5001'),favourites=NS(value='[]',save=MagicMock()))
        ns={'Screen':Screen,'Label':Label,'Pixmap':Label,'MenuList':MagicMock(),'ActionMap':lambda *a:None,
            'reactor':MagicMock(),'settings':settings,'ePicLoad':MagicMock(),'deferToThread':MagicMock(),
            'discard_playlist':playlist.discard_playlist,'take_playlist_preview':playlist.take_playlist_preview,'playlist_error_message':playlist.playlist_error_message,
            'load_playlist':playlist.load_playlist,'load_artwork':playlist.load_artwork,
            'MoviePlayer':object,'IPTVPlayer':object,'IPTVNavigator':object,'eServiceReference':Ref,'configfile':MagicMock(),
            'MessageBox':NS(TYPE_INFO=1),'IPTVSettings':object,'VirtualKeyBoard':object}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<ui>','exec'),ns)
        self.ns=ns
        self.scale=ns['fit_skin']; ns['fit_skin']=lambda skin,**kw:skin
        h=ns['IPTVHome'](MagicMock()); h.render()
        return h

    def test_start_missing_source_no_network_or_modal(self):
        h=self.build(); h.start()
        self.ns['deferToThread'].assert_not_called(); h.session.open.assert_not_called()
        self.assertEqual(h['hero'].text,'Co oglądamy?')

    def test_shelves_paging_and_selected_title(self):
        h=self.build(); h.channels=[channel(i) for i in range(13)]+[channel(20,'Filmy'),channel(30,'Seriale')]
        h.rebuild_rows(); h.move('down'); h.move('down')
        for i in range(7): h.move('right')
        self.assertEqual(h.column,7); self.assertEqual(h['hero'].text,'Kanał 7')
        self.assertEqual(h['card0_2'].text,'Kanał 7'); self.assertTrue(h['frame0_2'].visible)
        h.move('down'); h.move('down')
        self.assertEqual(h.first_row,1); self.assertEqual(h.current()['group'],'Seriale')

    def test_navigation_search_and_empty_results(self):
        h=self.build(); h.channels=[channel(1,'Sport'),channel(2,'Filmy')]; h.rebuild_rows()
        h.nav=2; h.activate(); self.assertEqual(h.current()['group'],'Filmy')
        h.searched('SPORT'); self.assertEqual(h.current()['group'],'Sport')
        h.searched('missing'); self.assertEqual(h.rows,[])
        for direction in ('right','down','left','up'): h.move(direction)
        self.assertEqual(h['hero'].text,'Co oglądamy?')

    def test_favourites_persist_hashes_and_removal_safe(self):
        h=self.build(); h.channels=[channel(1)]; h.rebuild_rows(); h.toggle_favourite()
        value=self.ns['settings'].favourites.value
        self.assertNotIn('example.com',value); self.assertEqual(len(h.favourites),1)
        h.category='favourites'; h.rebuild_rows(); h.area='shelf'; h.toggle_favourite()
        self.assertEqual(h.rows,[]); h.move('right'); h.move('down')

    def test_reload_duplicate_late_and_failure_keep_content(self):
        h=self.build(True); self.ns['settings'].source.value='https://example.com/list'
        h.reload(); h.reload(); self.ns['deferToThread'].assert_called_once()
        self.assertEqual(self.ns['deferToThread'].call_args.kwargs['timeout'],60)
        request=h.request_id; h.loaded([channel(1)],request)
        h.reload(); h.failed(None,h.request_id)
        self.assertEqual(len(h.channels),1); h.session.open.assert_not_called()
        h.cleanup(); h.loaded([channel(2)],h.request_id-1)
        self.assertEqual(h.channels,[])  # Closed UI releases the current catalogue.

    def test_buffering_launch_guard_and_exception(self):
        h=self.build(True); h.channels=[channel(1)]; h.rebuild_rows()
        h.play(); h.play(); h.session.openWithCallback.assert_called_once()
        ref=h.session.openWithCallback.call_args.args[2]
        self.assertEqual((ref.kind,ref.data),(4097,{7:1}))
        h.player_closed(); h.session.openWithCallback.side_effect=RuntimeError()
        h.play(); self.assertFalse(h.player_open)

    def test_slow_mode_does_not_fetch_art(self):
        h=self.build(True); h.channels=[channel(1,logo='https://example.com/logo.png')]; h.rebuild_rows()
        self.ns['deferToThread'].assert_not_called()

    def test_artwork_serial_queue_and_stale_result_cleanup(self):
        h=self.build(); h.update_art(channel(1,logo='https://example.com/1.png'))
        h.update_art(channel(2,logo='https://example.com/2.png'))
        h.update_art(channel(3,logo='https://example.com/3.png'))
        self.assertEqual(self.ns['deferToThread'].call_count,1)
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f: path=f.name
        h.art_downloaded(path,'https://example.com/1.png',h.image_request-2)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.ns['deferToThread'].call_count,2)
        self.assertEqual(self.ns['deferToThread'].call_args.args[1],'https://example.com/3.png')

    def test_art_decode_failure_does_not_crash_ui(self):
        h=self.build(); h.decoding_request=h.image_request; h.logo_busy=True
        h.picload.getData.side_effect=RuntimeError('bad image')
        h.art_decoded()
        self.assertFalse(h.logo_busy); self.assertFalse(h['art'].visible)

    def test_playlist_menu_and_activation_save_then_reload(self):
        h=self.build(); marker=object(); self.ns['IPTVPlaylistSources']=marker
        h.nav=7; h.activate()
        self.assertIs(h.session.openWithCallback.call_args.args[1],marker)
        self.ns['settings'].source.save=MagicMock()
        h.playlist_selected('/etc/enigma2/iptvpl/playlists/test.m3u')
        self.ns['settings'].source.save.assert_called_once()
        self.assertEqual(self.ns['settings'].source.value,'/etc/enigma2/iptvpl/playlists/test.m3u')
        self.ns['deferToThread'].assert_called_once()
        self.assertEqual(h.category,'start')

    def test_focus_markers_do_not_cover_button_text(self):
        h=self.build(); root=ET.fromstring(h.skin)
        by_name={n.get('name'):n for n in root if n.get('name')}
        for i in range(2):
            button=by_name['action%d'%i]; marker=by_name['actionfocus%d'%i]
            by=int(button.get('position').split(',')[1]); bh=int(button.get('size').split(',')[1])
            my=int(marker.get('position').split(',')[1])
            self.assertGreaterEqual(my,by+bh)

    def test_confirmed_preview_is_used_without_second_download(self):
        h=self.build(); source='https://example.com/confirmed-list'
        self.ns['settings'].source.value=source
        data=[channel(1)]
        playlist.remember_playlist(source,data)
        h.reload()
        self.ns['deferToThread'].assert_not_called()
        self.assertEqual(h.channels,data)
        self.assertFalse(h.loading)

    def test_disk_catalogue_integrates_with_home_search_and_cleanup(self):
        from Plugins.Extensions.IPTVPL import catalogue
        import tempfile
        with tempfile.TemporaryDirectory() as d, patch.object(catalogue,'cache_directory',return_value=d), patch.object(catalogue,'MAX_IN_MEMORY',0):
            builder=catalogue.CatalogueBuilder()
            for i in range(12): builder.append(channel(i))
            result=builder.finish(); path=result.path
            h=self.build()
            class Deferred:
                def __init__(self,value): self.value=value
                def addCallbacks(self,good,bad): return good(self.value)
            self.ns['deferToThread'].side_effect=lambda fn,*args,**kwargs: Deferred(fn(*args,**kwargs))
            h.loaded(result,h.request_id)
            self.assertEqual(len(h.rows[0][1]),12)
            h.nav=1; h.area='nav'; h.activate()
            self.assertEqual(h.session.openWithCallback.call_args.kwargs,{'focus':'bouquets'})
            self.assertFalse(h.pending_tv)
            h.searched('Kanał 11')
            self.assertEqual(h.current()['name'],'Kanał 11')
            self.assertEqual(sum(len(items) for _,items in h.rows),1)
            h.cleanup(); self.assertFalse(Path(path).exists())

    def test_return_from_player_restores_selected_channel_page(self):
        h=self.build(); h.channels=[channel(i) for i in range(15)]; h.rebuild_rows()
        h.player_closed(channel(11))
        self.assertEqual((h.row,h.column),(0,11))
        self.assertEqual(h.current()['name'],'Kanał 11')
        self.assertTrue(h['frame0_1'].visible)
        self.assertFalse(h.player_open)

    def test_manual_refresh_forces_network_and_progress_ignores_stale_results(self):
        h=self.build(); self.ns['settings'].source.value='https://example.com/manual'
        h.reload(force=True)
        options=self.ns['deferToThread'].call_args.kwargs
        self.assertTrue(options['force']); self.assertTrue(callable(options['progress']))
        h.download_progress(h.request_id,1048576,2097152)
        self.assertIn('1.0 / 2.0',h['status'].text)
        old=h['status'].text
        h.download_progress(h.request_id-1,0,None)
        self.assertEqual(h['status'].text,old)
        h.loading=False; h.download_progress(h.request_id,0,None)
        self.assertEqual(h['status'].text,old)

    def test_tv_opens_themed_bouquets_directly(self):
        h=self.build(); h.channels=[channel(1,'Sport'),channel(2,'Polskie'),channel(3,'Muzyka'),channel(4,'Filmy')]
        h.nav=1; h.activate()
        call=h.session.openWithCallback.call_args
        self.assertIs(call.args[1],self.ns['IPTVNavigator'])
        self.assertEqual(call.kwargs,{'focus':'bouquets'})
        context=call.args[2]
        self.assertEqual([name for name,_ in context.load()],['Sport','Polskie','Muzyka'])
        self.assertEqual(h.category,'live')
        self.assertFalse(h.pending_tv)

    def test_tv_waits_for_playlist_then_opens_without_missing_source_prompt(self):
        h=self.build(); h.loading=True; h.nav=1; h.activate()
        h.session.openWithCallback.assert_not_called()
        self.assertEqual(h['hero'].text,'Wczytywanie playlisty')
        self.assertNotIn('Dodaj playlistę',h['summary'].text)
        h.loaded([channel(1,'Sport')],h.request_id)
        h.session.openWithCallback.assert_called_once()
        self.assertFalse(h.pending_tv)

    def test_leaving_tv_while_loading_cancels_auto_open(self):
        h=self.build(); h.loading=True; h.nav=1; h.activate()
        h.move('right')
        self.assertFalse(h.pending_tv)
        h.loaded([channel(1,'Sport')],h.request_id)
        h.session.openWithCallback.assert_not_called()

    def test_skin_bounds_all_resolutions(self):
        h=self.build()
        for w,hh in [(1280,720),(1920,1080),(3840,2160)]:
            e=NS(getDesktop=lambda _:NS(size=lambda:NS(width=lambda:w,height=lambda:hh)))
            with patch.dict(sys.modules,{'enigma':e}):
                root=ET.fromstring(self.scale(h.skin,fullscreen=True))
                self.assertEqual(root.get('size'),'%d,%d'%(w,hh))
                for widget in root:
                    x,y=map(int,widget.get('position').split(',')); sw,sh=map(int,widget.get('size').split(','))
                    self.assertLessEqual(x+sw,w); self.assertLessEqual(y+sh,hh)

    def test_logo_metadata_and_artwork_validation(self):
        c=playlist.parse_m3u('#EXTINF:-1 tvg-logo="logos/a.png",TV\nstream.m3u8','https://example.com/list.m3u')[0]
        self.assertEqual(c['logo'],'https://example.com/logos/a.png')
        response=MagicMock(); response.__enter__.return_value=response
        response.read.return_value=b'<html>error</html>'
        with patch.object(playlist,'urlopen',return_value=response), self.assertRaises(ValueError):
            playlist.load_artwork('https://example.com/art.png')
        response.read.return_value=b'\x89PNG\r\n\x1a\n'+b'x'*100
        with patch.object(playlist,'urlopen',return_value=response):
            path=playlist.load_artwork('https://example.com/art.png')
            try: self.assertEqual(Path(path).read_bytes(),response.read.return_value)
            finally: os.unlink(path)

if __name__=='__main__': unittest.main()
