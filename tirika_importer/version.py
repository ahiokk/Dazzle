from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import sys

APP_NAME = "Dazzle"
APP_VERSION = "1.0.29"

# Редакции (издания) программы. Раньше сборки назывались по версии Windows
# (win10/win7), но на деле каждая сборка — это конкретный магазин со своим
# набором функций. Ozon нужен только AUTO255.
EDITION_AUTO255 = "auto255"
EDITION_LASTOCHKA = "lastochka"
EDITION_VAG = "vag"


@dataclass(frozen=True)
class Edition:
    key: str
    display_name: str
    exe_stem: str
    ozon_enabled: bool
    manifest_file: str
    default_article_match_field: str
    legacy_qt: bool  # PySide2 + Python 3.8 (сборка под Windows 7)


EDITIONS: dict[str, Edition] = {
    EDITION_AUTO255: Edition(
        key=EDITION_AUTO255,
        display_name="Dazzle AUTO255",
        exe_stem="Dazzle",
        ozon_enabled=True,
        manifest_file="latest.json",
        default_article_match_field="product_code",
        legacy_qt=False,
    ),
    EDITION_LASTOCHKA: Edition(
        key=EDITION_LASTOCHKA,
        display_name="Dazzle Lastochka",
        # Имя exe намеренно остаётся прежним: по нему работает автообновление
        # уже установленных копий (манифест latest-win7.json).
        exe_stem="DazzleWin7",
        ozon_enabled=False,
        manifest_file="latest-win7.json",
        default_article_match_field="barcode",
        legacy_qt=True,
    ),
    EDITION_VAG: Edition(
        key=EDITION_VAG,
        display_name="Dazzle VAG",
        exe_stem="DazzleVAG",
        ozon_enabled=False,
        manifest_file="latest-vag.json",
        default_article_match_field="product_code",
        legacy_qt=False,
    ),
}

DEFAULT_EDITION = EDITION_AUTO255

# Как редакция определяется из переменных окружения (в т.ч. старые значения
# DAZZLE_UPDATE_CHANNEL, которые могли остаться на установленных машинах).
_EDITION_ALIASES: dict[str, str] = {
    "auto255": EDITION_AUTO255,
    "auto-255": EDITION_AUTO255,
    "avto255": EDITION_AUTO255,
    "win10": EDITION_AUTO255,
    "windows10": EDITION_AUTO255,
    "default": EDITION_AUTO255,
    "lastochka": EDITION_LASTOCHKA,
    "ласточка": EDITION_LASTOCHKA,
    "win7": EDITION_LASTOCHKA,
    "windows7": EDITION_LASTOCHKA,
    "vag": EDITION_VAG,
}


def _edition_from_text(value: object) -> Edition | None:
    key = _EDITION_ALIASES.get(str(value or "").strip().lower())
    if key is None:
        return None
    return EDITIONS[key]


def _edition_from_exe_stem(stem: str) -> Edition | None:
    stem = stem.lower()
    if "dazzle" not in stem:
        return None
    if "vag" in stem:
        return EDITIONS[EDITION_VAG]
    if "win7" in stem or "lastochka" in stem:
        return EDITIONS[EDITION_LASTOCHKA]
    return EDITIONS[EDITION_AUTO255]


def current_edition() -> Edition:
    """Редакция текущего запуска: переменная окружения → имя exe → AUTO255."""
    for env_name in ("DAZZLE_EDITION", "DAZZLE_UPDATE_CHANNEL"):
        edition = _edition_from_text(os.environ.get(env_name, ""))
        if edition is not None:
            return edition

    edition = _edition_from_exe_stem(Path(sys.executable).stem)
    if edition is not None:
        return edition

    # Запуск из исходников (python main.py).
    return EDITIONS[DEFAULT_EDITION]


def edition_key() -> str:
    return current_edition().key


def ozon_enabled() -> bool:
    """Вкладка Ozon есть только в AUTO255."""
    return current_edition().ozon_enabled


def is_win7_build() -> bool:
    """Сборка на PySide2/Python 3.8 (Windows 7). Сейчас это редакция Lastochka."""
    return current_edition().legacy_qt


def display_app_name() -> str:
    return current_edition().display_name


def display_app_title() -> str:
    return f"{display_app_name()} {APP_VERSION}"


# Совместимость со старым кодом/скриптами.
APP_WIN7_NAME = EDITIONS[EDITION_LASTOCHKA].display_name
