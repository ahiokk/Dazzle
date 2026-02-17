from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import win32com.client  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    win32com = None  # type: ignore[assignment]


class StartupError(RuntimeError):
    pass


APP_LINK_NAME = "Dazzle.lnk"


def is_supported() -> bool:
    return os.name == "nt" and win32com is not None


def get_startup_link_path() -> Path:
    startup_dir = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    return startup_dir / APP_LINK_NAME


def is_enabled() -> bool:
    return get_startup_link_path().exists()


def enable_startup() -> Path:
    if not is_supported():
        raise StartupError("Автозапуск поддерживается только в Windows с установленным pywin32.")

    target_path, args, workdir = _resolve_launch_command()
    link_path = get_startup_link_path()
    link_path.parent.mkdir(parents=True, exist_ok=True)

    shell = win32com.client.Dispatch("WScript.Shell")  # type: ignore[union-attr]
    shortcut = shell.CreateShortCut(str(link_path))
    shortcut.TargetPath = str(target_path)
    shortcut.Arguments = args
    shortcut.WorkingDirectory = str(workdir)
    shortcut.WindowStyle = 1
    shortcut.IconLocation = str(target_path)
    shortcut.Save()
    return link_path


def disable_startup() -> None:
    link_path = get_startup_link_path()
    if link_path.exists():
        link_path.unlink()


def _resolve_launch_command() -> tuple[Path, str, Path]:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return exe, "", exe.parent

    python_exe = Path(sys.executable).resolve()
    pythonw = python_exe.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else python_exe

    project_root = Path(__file__).resolve().parent.parent
    main_script = project_root / "main.py"
    if not main_script.exists():
        raise StartupError(f"Файл запуска не найден: {main_script}")

    return launcher, f"\"{main_script}\"", project_root
