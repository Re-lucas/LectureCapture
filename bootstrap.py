"""Keep every GUI entry point on this project's Python environment."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def ensure_project_python():
    """Return True when this process handed off to the project interpreter."""
    environment = ROOT / '.venv'
    if Path(sys.prefix).resolve() == environment.resolve():
        return False
    interpreter = environment / 'Scripts' / 'pythonw.exe'
    if not interpreter.is_file():
        raise RuntimeError('项目 Python 环境缺失，请按 README.md 重建 .venv。')
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', '__PYVENV_LAUNCHER__'):
        env.pop(key, None)
    subprocess.Popen(
        [str(interpreter), str(ROOT / 'launch.pyw')],
        cwd=str(ROOT), env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return True
