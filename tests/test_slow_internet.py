import io
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1] / 'Plugins/Extensions/IPTVPL'
spec=importlib.util.spec_from_file_location('Plugins.Extensions.IPTVPL.playlist', ROOT/'playlist.py')
playlist=importlib.util.module_from_spec(spec)
spec.loader.exec_module(playlist)
tree=ast.parse((ROOT/'plugin.py').read_text())

class Ref:
    def __init__(self,kind,flags,url): self.kind=kind; self.data={}
    def setData(self,key,value): self.data[key]=value
    def setName(self,name): self.name=name

class Tests(unittest.TestCase):
    def browser(self,slow):
        settings=NS(slowinternet=NS(value=slow),player=NS(value='5001'),source=NS(value='https://example.com/list'))
        ns={'Screen':dict,'settings':settings,'eServiceReference':Ref,'MoviePlayer':object,'MessageBox':NS(TYPE_ERROR=1)}
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IPTVBrowser')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<browser>','exec'),ns)
        b=ns['IPTVBrowser'].__new__(ns['IPTVBrowser'])
        dict.__init__(b)
        b.player_open=False; b.disposed=False; b.loading=False
        b.session=MagicMock()
        b['channels']=NS(getCurrent=lambda:('TV',{'name':'TV','url':'https://example.com/live','group':'Sport'}))
        b['selection']=MagicMock(); b['detail']=MagicMock(); b['status']=MagicMock()
        return b,ns

    def test_buffer_and_duplicate_guard(self):
        b,_=self.browser(True)
        b.play(); b.play()
        self.assertEqual(b.session.openWithCallback.call_count,1)
        ref=b.session.openWithCallback.call_args.args[2]
        self.assertEqual((ref.kind,ref.data),(4097,{7:1}))
        b.player_closed(); b.play()
        self.assertEqual(b.session.openWithCallback.call_count,2)

    def test_normal_player_unchanged(self):
        b,_=self.browser(False); b.play()
        ref=b.session.openWithCallback.call_args.args[2]
        self.assertEqual((ref.kind,ref.data),(5001,{}))

    def test_open_failure_unlocks(self):
        b,_=self.browser(True)
        b.session.openWithCallback.side_effect=RuntimeError('unavailable')
        b.play()
        self.assertFalse(b.player_open)
        b.session.open.assert_called_once()

    def test_background_timeout_and_duplicate_reload(self):
        for slow,expected in [(False,20),(True,60)]:
            b,ns=self.browser(slow)
            ns['load_playlist']=playlist.load_playlist
            ns['deferToThread']=MagicMock()
            b.reload(); b.reload()
            self.assertEqual(ns['deferToThread'].call_count,1)
            self.assertEqual(ns['deferToThread'].call_args.kwargs,{'timeout':expected})

    def test_loader_passes_timeout(self):
        r=MagicMock(); r.__enter__.return_value=r
        r.read.side_effect=io.BytesIO(b'https://example.com/live').read
        r.geturl.return_value='https://example.com/list'
        with patch.object(playlist,'urlopen',return_value=r) as op:
            playlist.load_playlist('https://example.com/list',timeout=60)
            self.assertEqual(op.call_args.kwargs['timeout'],60)

    def test_skin_xml(self):
        for cls in tree.body:
            if isinstance(cls,ast.ClassDef):
                for stmt in cls.body:
                    if isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='skin' for t in stmt.targets):
                        if isinstance(stmt.value, ast.Constant):
                            ET.fromstring(ast.literal_eval(stmt.value))
                        # Generated home skin is tested at HD, FHD and UHD in test_home.

if __name__=='__main__': unittest.main()

