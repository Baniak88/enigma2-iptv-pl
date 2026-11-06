"""Enigma2 Session.processDelay invokes callback(*retVal), including retVal=()."""
import ast
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock
import unittest

TREE=ast.parse((Path(__file__).resolve().parents[1]/'Plugins/Extensions/IPTVPL/plugin.py').read_text())

class CancelTests(unittest.TestCase):
    def test_every_screen_return_callback_accepts_empty_result(self):
        checked=[]
        for cls in TREE.body:
            if not isinstance(cls,ast.ClassDef):
                continue
            callbacks=set()
            for call in ast.walk(cls):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='openWithCallback' and call.args:
                    first=call.args[0]
                    if isinstance(first,ast.Attribute) and isinstance(first.value,ast.Name) and first.value.id=='self':
                        callbacks.add(first.attr)
            methods={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
            for name in callbacks:
                with self.subTest(screen=cls.name,callback=name):
                    ns={'settings':MagicMock(),'configfile':MagicMock()}
                    exec(compile(ast.Module(body=[methods[name]],type_ignores=[]),'<callback>','exec'),ns)
                    screen=SimpleNamespace(disposed=False,player_open=True,render=MagicMock(),hide=MagicMock(),close=MagicMock(),reload=MagicMock(),selection_changed=MagicMock(),rebuild_rows=MagicMock())
                    callback=MethodType(ns[name],screen)
                    callback()  # Exact invocation from Session.processDelay after EXIT.
                    screen.close.assert_not_called()
                    screen.reload.assert_not_called()
                    ns['configfile'].save.assert_not_called()
                    checked.append((cls.name,name))
        self.assertIn(('IPTVPlaylistSources','selected'),checked)
        self.assertIn(('IPTVHome','playlist_selected'),checked)
        self.assertGreaterEqual(len(checked),10)

if __name__=='__main__': unittest.main()
