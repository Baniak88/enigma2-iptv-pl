import ast
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())

class RecoveryTests(unittest.TestCase):
    def functions(self):
        nodes=[node for node in TREE.body if isinstance(node,ast.FunctionDef) and node.name in ('report_ui_error','guarded_render','main')]
        ns={'VERSION':'1.1.1','MessageBox':SimpleNamespace(TYPE_ERROR=1),'IPTVHome':object}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<recovery>','exec'),ns)
        return ns

    def test_render_failure_records_frames_without_secret_exception_message(self):
        ns=self.functions();screen=SimpleNamespace(session=MagicMock())
        def broken(self):raise ValueError('https://provider.invalid/?password=secret')
        with tempfile.TemporaryFile(mode='w+') as log:
            from contextlib import nullcontext
            with patch('builtins.open',return_value=nullcontext(log)):
                ns['guarded_render'](broken)(screen)
            log.seek(0);data=log.read()
        self.assertIn('broken',data);self.assertIn('ValueError',data)
        self.assertNotIn('password',data);screen.session.open.assert_called_once()

    def test_startup_failure_opens_error_dialog(self):
        ns=self.functions();session=MagicMock();session.open.side_effect=[RuntimeError('skin'),None]
        with patch.dict(ns,report_ui_error=MagicMock()) as unused:
            ns['main'](session)
            ns['report_ui_error'].assert_called_once_with(session)

    def test_icon_is_packaged_and_registered(self):
        from PIL import Image
        with Image.open(ROOT/'Plugins/Extensions/IPTVPL/plugin.png') as image:
            self.assertEqual(image.size,(100,100));self.assertEqual(image.mode,'RGBA')
        self.assertIn("icon='plugin.png'",(ROOT/'Plugins/Extensions/IPTVPL/plugin.py').read_text())
        self.assertEqual((ROOT/'install.sh').read_text().count('plugin.py plugin.png;'),2)
