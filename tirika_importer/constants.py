"""Константы интерфейса Dazzle: индексы колонок таблиц, роли, варианты оплаты.

Вынесено из gui.py, чтобы их можно было переиспользовать (в т.ч. в тестах).
"""
from __future__ import annotations

from .qt_compat import Qt


COL_LINE = 0
COL_ARTICLE = 1
COL_NAME = 2
COL_NOTE = 3
COL_QTY = 4
COL_BUY_PRICE = 5
COL_SUM = 6
COL_SELL_PRICE = 7
COL_SELL_PRICE_OLD = 8
COL_SELL_DIFF = 9
COL_MARKUP = 10
COL_STATUS = 11
COL_ACTION = 12
COL_GOOD_ID = 13
COL_GOOD_CODE = 14
COL_GOOD_NAME = 15
COL_SIMILAR = 16
COL_METHOD = 17
COL_WARNING = 18

DB_ONLY_COLUMNS = (
    COL_GOOD_ID,
    COL_SIMILAR,
    COL_METHOD,
)

# Колонки с числами/кодами — моноширинный шрифт для выравнивания по разрядам.
MONO_COLUMNS = (
    COL_LINE,
    COL_ARTICLE,
    COL_QTY,
    COL_BUY_PRICE,
    COL_SUM,
    COL_SELL_PRICE,
    COL_SELL_PRICE_OLD,
    COL_SELL_DIFF,
    COL_MARKUP,
    COL_GOOD_ID,
    COL_GOOD_CODE,
)

MAX_HISTORY_STATES = 80
ROLE_SELL_DB_OLD_PRICE = Qt.UserRole + 101

OZ_COL_LINE = 0
OZ_COL_ORDER = 1
OZ_COL_POSTING = 2
OZ_COL_SOURCE_ARTICLE = 3
OZ_COL_GOOD_CODE = 4
OZ_COL_NAME = 5
OZ_COL_QTY = 6
OZ_COL_PRICE = 7
OZ_COL_SUM = 8
OZ_COL_REMAINDER = 9
OZ_COL_STATUS = 10
OZ_COL_ACTION = 11
OZ_COL_WARNING = 12

PAYMENT_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Не оплачено", -1),
    ("Наличные", 0),
    ("Безнал", 1),
    ("Карта", 5),
    ("QR", 7),
)


__all__ = [
    "COL_LINE",
    "COL_ARTICLE",
    "COL_NAME",
    "COL_NOTE",
    "COL_QTY",
    "COL_BUY_PRICE",
    "COL_SUM",
    "COL_SELL_PRICE",
    "COL_SELL_PRICE_OLD",
    "COL_SELL_DIFF",
    "COL_MARKUP",
    "COL_STATUS",
    "COL_ACTION",
    "COL_GOOD_ID",
    "COL_GOOD_CODE",
    "COL_GOOD_NAME",
    "COL_SIMILAR",
    "COL_METHOD",
    "COL_WARNING",
    "DB_ONLY_COLUMNS",
    "MONO_COLUMNS",
    "MAX_HISTORY_STATES",
    "ROLE_SELL_DB_OLD_PRICE",
    "OZ_COL_LINE",
    "OZ_COL_ORDER",
    "OZ_COL_POSTING",
    "OZ_COL_SOURCE_ARTICLE",
    "OZ_COL_GOOD_CODE",
    "OZ_COL_NAME",
    "OZ_COL_QTY",
    "OZ_COL_PRICE",
    "OZ_COL_SUM",
    "OZ_COL_REMAINDER",
    "OZ_COL_STATUS",
    "OZ_COL_ACTION",
    "OZ_COL_WARNING",
    "PAYMENT_OPTIONS",
]
