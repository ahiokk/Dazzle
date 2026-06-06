"""Запуск Dazzle для отладки/демо без UAC-повышения.

Обычный вход — main.py (он запрашивает права администратора). Этот скрипт
поднимает то же окно без повышения прав, чтобы удобнее смотреть интерфейс и
видеть трейсбеки в консоли. Запись в shop.db (импорт) при этом может быть
недоступна без прав администратора — но просмотр и заказы (только чтение) работают.
"""

from __future__ import annotations

import sys

from tirika_importer.gui import MainWindow
from tirika_importer.qt_compat import QApplication, qt_exec


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return int(qt_exec(app))


if __name__ == "__main__":
    raise SystemExit(main())
