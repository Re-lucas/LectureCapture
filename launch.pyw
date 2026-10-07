"""Run the source GUI with the installed Python; report startup errors visibly."""

import ctypes
import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    try:
        from bootstrap import ensure_project_python
        if ensure_project_python():
            raise SystemExit(0)
        runpy.run_path(str(ROOT / "LectureCapture.pyw"), run_name="__main__")
    except Exception:
        details = traceback.format_exc()
        log_path = ROOT / "runtime" / "startup.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # Keep only the latest startup failure; never log captured text.
            log_path.write_text(f"{datetime.now().astimezone().isoformat()}\n{details}", encoding="utf-8")
            message = f"LectureCapture 启动失败。\n\n错误详情已写入：\n{log_path}"
        except OSError:
            message = f"LectureCapture 启动失败：\n\n{details[-1800:]}"
        ctypes.windll.user32.MessageBoxW(None, message, "LectureCapture", 0x10)
        raise SystemExit(1)
