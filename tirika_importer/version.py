from __future__ import annotations

import os
from pathlib import Path
import sys

APP_NAME = "Dazzle"
APP_WIN7_NAME = "Dazzle Win7"
APP_VERSION = "1.0.16"


def is_win7_build() -> bool:
    channel = os.environ.get("DAZZLE_UPDATE_CHANNEL", "").strip().lower()
    if channel in {"win7", "windows7"}:
        return True

    exe_stem = Path(sys.executable).stem.lower()
    return "dazzle" in exe_stem and "win7" in exe_stem


def display_app_name() -> str:
    return APP_WIN7_NAME if is_win7_build() else APP_NAME


def display_app_title() -> str:
    return f"{display_app_name()} {APP_VERSION}"
