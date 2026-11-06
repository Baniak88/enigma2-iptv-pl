import ast
from pathlib import Path
import random
import string
import sys
from types import SimpleNamespace as NS, MethodType
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

TREE=ast.parse((Path(__file__).resolve().parents[1]/'Plugins/Extensions/IPTVPL/plugin.py').read_text())

class Screen(dict):
    def __init__(self,session):
        super().__init__(); self.session=session; self.onExecBegin=[]; self.onClose=[]; self.onLayoutFinish=[]
    def close(self,value=None): self.result=value
class Label:
    def __init__(self,text): self.text=text; self.visible=True
    def setText(self,text): self.text=text
    def show(self): self.visible=True
    def hide(self): self.visible=False

class KeyboardTests(unittest.TestCase):
    def ns(self):
        names=('keyboard_rows','keyboard_skin','KeyboardText','IPTVKeyboard','fit_skin')
        nodes=[n for n in TREE.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
        ns={'Screen':Screen,'Label':Label,'ActionMap':lambda contexts,actions,priority:actions}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<keyboard>','exec'),ns)
        return ns

    def test_complete_ascii_and_polish_characters(self):
        ns=self.ns()
        chars=set(''.join(''.join(row) for shift in (False,True) for row in ns['keyboard_rows'](shift)[:5]))
        self.assertTrue(set(chr(i) for i in range(32,127))<=chars)
        self.assertTrue(set('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ')<=chars)
        for shift in (False,True): self.assertEqual([len(r) for r in ns['keyboard_rows'](shift)],[12,12,12,12,12,6])

    def test_full_url_unchanged_and_cursor_editing(self):
        ns=self.ns(); value='https://example.com/get.php?username=a%2Bb&password=x%26y+z&type=m3u_plus&output=ts'
        b=ns['KeyboardText'](value)
        self.assertEqual(b.value,value)
        b.move(-len(value)); b.insert('X'); self.assertEqual(b.value,'X'+value)
        b.backspace(); self.assertEqual(b.value,value)
        b.move(len(value)); self.assertEqual(b.cursor,len(value))
        b.insert('&token=ąŁ_@'); self.assertTrue(b.value.endswith('&token=ąŁ_@'))
        self.assertIn('|',b.window())
        long=ns['KeyboardText']('x'*16000)
        self.assertLess(len(long.window()),110); self.assertEqual(len(long.value),16000)

    def test_navigation_shift_numbers_accept_and_cancel(self):
        ns=self.ns(); ns['fit_skin']=lambda skin,**kw:skin
        k=ns['IPTVKeyboard'](None,text='')
        k.move('down'); k.press(); self.assertEqual(k.buffer.value,'q')
        k['actions']['blue'](); k.press(); k['actions']['5']()
        self.assertEqual(k.buffer.value,'qQ5')
        k['actions']['yellow'](); self.assertEqual(k.buffer.value,'qQ')
        rng=random.Random(1)
        for _ in range(100):
            k.move(rng.choice(['left','right','up','down']))
            self.assertTrue(0<=k.row<6)
            self.assertTrue(0<=k.col<len(ns['keyboard_rows'](k.shift)[k.row]))
        focus=[v for name,v in k.items() if name.startswith('keyfocus') and v.visible]
        self.assertEqual(len(focus),1)
        k['actions']['green'](); self.assertEqual(k.result,'qQ')
        k['actions']['red'](); self.assertIsNone(k.result)

    def test_keyboard_bounds_hd_fhd_4k(self):
        ns=self.ns()
        for w,h in [(1280,720),(1920,1080),(3840,2160)]:
            enigma=NS(getDesktop=lambda _:NS(size=lambda:NS(width=lambda:w,height=lambda:h)))
            with patch.dict(sys.modules,{'enigma':enigma}):
                root=ET.fromstring(ns['fit_skin'](ns['keyboard_skin'](),fullscreen=True))
                for node in root:
                    x,y=map(int,node.get('position').split(',')); width,height=map(int,node.get('size').split(','))
                    self.assertLessEqual(x+width,w); self.assertLessEqual(y+height,h)

    def test_settings_ok_opens_full_keyboard_and_cancel_keeps_source(self):
        cls=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='IPTVSettings')
        methods=[m for m in cls.body if isinstance(m,ast.FunctionDef) and m.name in ('keyOK','keyboard_done')]
        source=NS(value='https://example.com/list?password=a%2Bb&x=1')
        ns={'settings':NS(source=source),'IPTVKeyboard':object}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'<settings>','exec'),ns)
        screen=MagicMock(); screen['config'].getCurrent.return_value=('Lista M3U',source)
        screen.keyboard_done=MethodType(ns['keyboard_done'],screen)
        MethodType(ns['keyOK'],screen)()
        args=screen.session.openWithCallback.call_args
        self.assertIs(args.args[1],object); self.assertEqual(args.kwargs['text'],source.value)
        screen.keyboard_done(None); self.assertEqual(source.value,'https://example.com/list?password=a%2Bb&x=1')
        screen.keyboard_done('https://example.com/new?a=1&b=2'); self.assertTrue(source.value.endswith('a=1&b=2'))

if __name__=='__main__': unittest.main()
