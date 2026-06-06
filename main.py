from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys

from tirika_importer.gui import MainWindow
from tirika_importer.qt_compat import QApplication, qt_exec


def _is_windows_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _restart_as_admin() -> bool:
    if os.name != "nt":
        return False

    exe_path = _elevation_executable()
    if getattr(sys, "frozen", False):
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        script_path = os.path.abspath(sys.argv[0])
        params = subprocess.list2cmdline([script_path, *sys.argv[1:]])

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe_path,
            params,
            None,
            1,
        )
        return result > 32
    except Exception:
        return False


def _elevation_executable() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable

    exe_path = Path(sys.executable)
    if exe_path.name.lower() == "python.exe":
        pythonw = exe_path.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(exe_path)


def ensure_admin() -> None:
    if _is_windows_admin():
        return

    if _restart_as_admin():
        raise SystemExit(0)

    ctypes.windll.user32.MessageBoxW(
        None,
        "Dazzle требует запуск с правами администратора.",
        "Dazzle",
        0x10,
    )
    raise SystemExit(1)


def main() -> int:
    from tirika_importer.logging_setup import setup_logging, get_logger
    from tirika_importer.version import APP_VERSION

    log_path = setup_logging()
    get_logger().info("Запуск Dazzle %s (лог: %s)", APP_VERSION, log_path)

    ensure_admin()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return int(qt_exec(app))


if __name__ == "__main__":
    raise SystemExit(main())
