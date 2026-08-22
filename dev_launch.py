"""Запуск Dazzle для отладки/демо без UAC-повышения.

Обычный вход — main.py (он запрашивает права администратора). Этот скрипт
поднимает то же окно без повышения прав, чтобы удобнее смотреть интерфейс и
видеть трейсбеки в консоли. Запись в shop.db (импорт) при этом может быть
недоступна без прав администратора — но просмотр и заказы (только чтение) работают.

Полезные ключи:
    python dev_launch.py --invoice "C:\\путь\\накладная.xls"   загрузить накладную сразу
    set DAZZLE_EDITION=vag & python dev_launch.py             посмотреть другую редакцию
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tirika_importer.gui import MainWindow
from tirika_importer.qt_compat import QApplication, QTimer, qt_exec


def _autoload_invoice(window: MainWindow, invoice_path: Path) -> None:
    """Дождаться открытия базы и загрузить накладную, как будто выбрали её в списке."""
    timer = QTimer(window)
    timer.setInterval(400)
    attempts = {"count": 0}

    def tick() -> None:
        attempts["count"] += 1
        if attempts["count"] > 90:  # ~36 секунд — дальше не ждём
            timer.stop()
            return
        if window._is_ui_busy():
            return
        # Ждём каталог товаров, но не бесконечно: без базы накладную тоже видно.
        if window.matcher is None and attempts["count"] < 30:
            return

        timer.stop()
        combo = window.invoice_file_combo
        index = -1
        for i in range(combo.count()):
            if str(combo.itemData(i) or "") == str(invoice_path):
                index = i
                break
        if index < 0:
            combo.addItem(invoice_path.name, userData=str(invoice_path))
            index = combo.count() - 1
        combo.setCurrentIndex(index)
        window._load_invoice()

    timer.timeout.connect(tick)
    timer.start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Запуск Dazzle без UAC (отладка/демо).")
    parser.add_argument(
        "--invoice",
        default="",
        help="путь к накладной .xls/.xlsx — загрузить сразу после старта",
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()

    if args.invoice:
        invoice_path = Path(args.invoice).expanduser()
        if not invoice_path.exists():
            print(f"Накладная не найдена: {invoice_path}", file=sys.stderr)
        else:
            _autoload_invoice(window, invoice_path)

    return int(qt_exec(app))


if __name__ == "__main__":
    raise SystemExit(main())
