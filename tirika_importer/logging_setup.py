"""Ротируемое файловое логирование Dazzle.

Лог пишется в %APPDATA%/Dazzle/logs/dazzle.log (с ротацией), чтобы можно было
разбирать инциденты импорта «в поле». Дублируется в UI-логе через _log/_error.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "dazzle"
_configured = False
_logfile_path: Path | None = None


def log_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "Dazzle" if appdata else Path.home() / ".dazzle"
    directory = base / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def setup_logging(level: int = logging.INFO) -> Path | None:
    """Идемпотентно настраивает файловый лог и хук необработанных исключений."""
    global _configured, _logfile_path
    if _configured:
        return _logfile_path

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    try:
        path = log_dir() / "dazzle.log"
        handler = RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        _logfile_path = path
    except Exception:
        # Логирование не должно мешать работе приложения.
        _logfile_path = None

    def _excepthook(exc_type, exc, tb):
        try:
            logger.error("Необработанное исключение", exc_info=(exc_type, exc, tb))
        finally:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _excepthook
    _configured = True
    return _logfile_path
