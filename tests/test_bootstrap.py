import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class ProjectPythonTests(unittest.TestCase):
    def test_project_interpreter_does_not_launch_another_process(self):
        with patch.object(bootstrap.sys, 'prefix', str(bootstrap.ROOT / '.venv')), \
                patch.object(bootstrap.subprocess, 'Popen') as spawn:
            self.assertFalse(bootstrap.ensure_project_python())
            spawn.assert_not_called()

    def test_system_interpreter_hands_off_and_removes_python_path_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            interpreter = root / '.venv' / 'Scripts' / 'pythonw.exe'
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            with patch.object(bootstrap, 'ROOT', root), \
                    patch.object(bootstrap.sys, 'prefix', str(root / 'system-python')), \
                    patch.dict(os.environ, {'PYTHONHOME': 'wrong', 'PYTHONPATH': 'wrong',
                                            '__PYVENV_LAUNCHER__': 'wrong', 'TEMP': tmp}), \
                    patch.object(bootstrap.subprocess, 'Popen') as spawn:
                self.assertTrue(bootstrap.ensure_project_python())
                args, kwargs = spawn.call_args
                self.assertEqual([str(interpreter), str(root / 'launch.pyw')], args[0])
                self.assertEqual(str(root), kwargs['cwd'])
                self.assertEqual(tmp, kwargs['env']['TEMP'])
                for key in ('PYTHONHOME', 'PYTHONPATH', '__PYVENV_LAUNCHER__'):
                    self.assertNotIn(key, kwargs['env'])
                self.assertEqual('wrong', os.environ['PYTHONHOME'])

    def test_missing_environment_fails_without_spawning_or_installing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(bootstrap, 'ROOT', Path(tmp)), \
                patch.object(bootstrap.sys, 'prefix', str(Path(tmp) / 'system-python')), \
                patch.object(bootstrap.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, '环境缺失'):
                bootstrap.ensure_project_python()
            spawn.assert_not_called()
