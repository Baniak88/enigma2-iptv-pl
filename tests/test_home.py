import ast
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=ROOT/'Plugins/Extensions/IPTVPL/plugin.py'
TREE=ast.parse(PLUGIN.read_text())

class Screen(dict):
    def __init__(self, session):
        super().__init__(); self.session=session
        self.onLayoutFinish=[]; self.onClose=[]; self.onFirstExecBegin=[]
    def close(self): pass

class Label:
    def __init__(self,text): self.text=text; self.visible=True
    def setText(self,text): self.text=text
    def show(self): self.visible=True
    def hide(self): self.visible=False

class HomeTests(unittest.TestCase):
    def namespace(self):
        names=('fit_skin','IPTVHome','channel_category','IPTVBrowser')
        nodes=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
        ns={'Screen':Screen,'Label':Label,'settings':NS(source=NS(value='/etc/enigma2/iptv.m3u')),
            'ActionMap':lambda *args:None, 'IPTVSettings':object}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<home>','exec'),ns)
        return ns

    def test_home_no_network_and_remote_navigation(self):
        ns=self.namespace(); ns['fit_skin']=lambda skin,**kw:skin
        session=MagicMock(); h=ns['IPTVHome'](session)
        session.open.assert_not_called()
        self.assertEqual(len(h.onFirstExecBegin),0)
        h.update_focus()
        self.assertEqual([i for i in range(6) if h['focus%d'%i].visible],[0])
        h.move('down'); h.move('right'); h.move('down')
        self.assertEqual(h.selected,5)
        h.activate(); session.openWithCallback.assert_called_once()
        for tile,category in [(0,'live'),(1,'movies'),(2,'series'),(4,'all')]:
            h.selected=tile; h.activate()
            self.assertEqual(session.open.call_args.kwargs,{'category':category})

    def test_category_uses_group_metadata(self):
        f=self.namespace()['channel_category']
        for group,expected in [('Filmy PL','movies'),('SERIALE','series'),('Sport','live'),('','live')]:
            self.assertEqual(f({'group':group}),expected)

    def test_scaling_hd_fhd_uhd(self):
        ns=self.namespace()
        for w,h in [(1280,720),(1920,1080),(3840,2160)]:
            enigma=NS(getDesktop=lambda _:NS(size=lambda:NS(width=lambda:w,height=lambda:h)))
            with patch.dict(sys.modules,{'enigma':enigma}):
                for cls in ('IPTVHome','IPTVBrowser'):
                    root=ET.fromstring(ns['fit_skin'](ns[cls].skin,fullscreen=cls=='IPTVHome'))
                    sw,sh=map(int,root.get('size').split(','))
                    self.assertLessEqual(sw,w); self.assertLessEqual(sh,h)
                    if cls=='IPTVHome': self.assertEqual((sw,sh),(w,h))
                    for widget in root:
                        x,y=map(int,widget.get('position').split(','))
                        ww,hh=map(int,widget.get('size').split(','))
                        self.assertLessEqual(x+ww,sw); self.assertLessEqual(y+hh,sh)

    def test_load_failure_is_inline(self):
        ns=self.namespace(); b=ns['IPTVBrowser'].__new__(ns['IPTVBrowser']); dict.__init__(b)
        b.disposed=False; b.loading=True; b.session=MagicMock(); b.render=MagicMock()
        for name in ('status','selection','detail'): b[name]=Label('')
        b.failed(None)
        b.session.open.assert_not_called()
        self.assertFalse(b.loading)
        self.assertIn('M3U',b['detail'].text)

if __name__=='__main__': unittest.main()
