"""Диалог «Заказать у Микадо то, что продано на Ozon».

Открывается из вкладки Ozon. По проданным позициям ищет их в Микадо и с
подтверждением кладёт в КОРЗИНУ Микадо (подпись в примечании). Заказ человек
оформляет вручную в кабинете Микадо — автоматической отправки заказа нет.
"""
from __future__ import annotations

import time

from .app_settings import AppSettings
from . import secret_store
from .mikado import MikadoClient, MikadoOffer
from .qt_compat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QObject,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QVBoxLayout,
    QWidget,
    Signal,
    qt_exec,
)

HEADERS = ["Артикул", "Наименование", "Прод.", "Бренд (Микадо)", "Налич.", "Срок", "Цена ₽", "Заказать", "Сумма ₽"]
C_CODE, C_NAME, C_SOLD, C_BRAND, C_STOCK, C_SROK, C_PRICE, C_QTY, C_SUM = range(9)

_SEND_QSS = (
    "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #E08A1E,stop:1 #C2700F);"
    "color:#FFFFFF;border:1px solid #A35E0B;border-radius:9px;font-weight:800;padding:0 18px;}"
    "QPushButton:hover{background:#C2700F;}"
    "QPushButton:disabled{background:#E7C79A;border-color:#E7C79A;color:#FBF4E8;}"
)
_BANNER_QSS = (
    "background:#FDF4E2;color:#92560A;border:1px solid #EFD9A6;"
    "border-radius:10px;padding:9px 12px;font-weight:600;"
)


def _fmt_money(value: float) -> str:
    out = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return out[:-3] if out.endswith(",00") else out


def make_client(settings: AppSettings) -> MikadoClient | None:
    if not (settings.mikado_client_code.strip() and settings.mikado_password_enc.strip()):
        return None
    return MikadoClient(
        settings.mikado_client_code.strip(),
        secret_store.decrypt(settings.mikado_password_enc),
        base_url=settings.mikado_base_url,
    )


def _pick_best(offers: list[MikadoOffer]) -> MikadoOffer | None:
    if not offers:
        return None

    def has_stock(o: MikadoOffer) -> int:
        s = (o.on_stocks or "").strip()
        try:
            return 1 if float(s.replace(",", ".")) > 0 else 0
        except ValueError:
            return 1 if s else 0

    return sorted(offers, key=lambda o: (-has_stock(o), o.price_rur if o.price_rur > 0 else 1e12))[0]


class _SearchAllWorker(QObject):
    """Ищет в Микадо каждую проданную позицию, возвращает лучший оффер."""
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, client: MikadoClient, items: list[tuple[str, str, float]], from_stock_only: bool) -> None:
        super().__init__()
        self._c = client
        self._items = items
        self._fso = from_stock_only

    def run(self) -> None:
        try:
            results = []
            total = len(self._items)
            for i, (code, name, sold) in enumerate(self._items):
                offer = None
                if code.strip():
                    offers = self._c.search(code, from_stock_only=self._fso)
                    offer = _pick_best(offers)
                results.append((code, name, sold, offer))
                self.progress.emit(i + 1, total)
                time.sleep(0.12)  # вежливость к лимитам Микадо
            self.finished.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _CartWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, client: MikadoClient, items: list[tuple[str, int]], note: str) -> None:
        super().__init__()
        self._c = client
        self._items = items
        self._note = note

    def run(self) -> None:
        try:
            out = []
            for code, qty in self._items:
                out.append((code, qty, self._c.basket_add(code, qty, notes=self._note)))
                time.sleep(0.1)
            self.finished.emit(out)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MikadoOrderDialog(QDialog):
    def __init__(self, parent, app_settings: AppSettings, items: list[tuple[str, str, float]]) -> None:
        super().__init__(parent)
        self.app_settings = app_settings
        self._items = items                       # (code, name, sold_qty)
        self._rows: list[tuple[str, str, float, MikadoOffer | None]] = []
        self._qty_edits: list[QLineEdit | None] = []
        self._threads: list[QThread] = []
        self._busy = False

        from .theme import APP_STYLESHEET
        self.setWindowTitle("Заказать у Микадо (по продажам Ozon)")
        self.resize(1180, 720)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()
        self._start_search()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("Заказ в Микадо по проданному на Ozon")
        title.setObjectName("titleLabel")
        root.addWidget(title)

        banner = QLabel(
            "  ⓘ  Dazzle добавит выбранные позиции в корзину «Микадо» (примечание «"
            + (self.app_settings.mikado_order_note or "Dazzle")
            + " · Ozon»). Заказ вы оформляете вручную в кабинете Микадо — автоматической отправки нет."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(_BANNER_QSS)
        root.addWidget(banner)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(C_NAME, QHeaderView.Stretch)
        for c in (C_CODE, C_SOLD, C_BRAND, C_STOCK, C_SROK, C_PRICE, C_QTY, C_SUM):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(C_QTY, 86)
        root.addWidget(self.table, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.summary = QLabel("Поиск в Микадо…")
        self.summary.setObjectName("totalsPill")
        foot.addWidget(self.summary)
        foot.addStretch(1)
        self.send_btn = QPushButton("Отправить в корзину Микадо")
        self.send_btn.setMinimumHeight(38)
        self.send_btn.setMinimumWidth(240)
        self.send_btn.setStyleSheet(_SEND_QSS)
        self.send_btn.setEnabled(False)
        self.send_btn.clicked.connect(self._on_send)
        foot.addWidget(self.send_btn)
        close_btn = QPushButton("Закрыть")
        close_btn.setObjectName("subtleBtn")
        close_btn.clicked.connect(self.reject)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    # -- worker plumbing --------------------------------------------------- #
    def _run(self, worker: QObject, on_done, on_fail) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_done)
        worker.failed.connect(on_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        self._threads.append(thread)
        thread.start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_btn.setEnabled(not busy and any(o for _, _, _, o in self._rows))

    # -- search ------------------------------------------------------------ #
    def _start_search(self) -> None:
        client = make_client(self.app_settings)
        if client is None:
            self.summary.setText("Микадо не настроен")
            return
        self._set_busy(True)
        worker = _SearchAllWorker(client, self._items, self.app_settings.mikado_from_stock_only)
        worker.progress.connect(lambda i, n: self.summary.setText(f"Поиск в Микадо… {i}/{n}"))
        # progress signal connect needs the worker alive; keep ref via _run
        self._run(worker, self._on_search_done, self._on_error)

    def _on_search_done(self, results: list) -> None:
        self._rows = results
        self.table.setRowCount(len(results))
        self._qty_edits = [None] * len(results)
        for r, (code, name, sold, offer) in enumerate(results):
            found = offer is not None
            cells = {
                C_CODE: code,
                C_NAME: name,
                C_SOLD: _fmt_money(sold),
                C_BRAND: (offer.brand if found else "— не найдено"),
                C_STOCK: (offer.on_stocks if found else ""),
                C_SROK: (offer.srok if found else ""),
                C_PRICE: (_fmt_money(offer.price_rur) if found else ""),
            }
            for col, val in cells.items():
                it = QTableWidgetItem(val)
                if col in (C_SOLD, C_STOCK, C_SROK, C_PRICE):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not found:
                    it.setForeground(QColor("#94A3B8"))
                self.table.setItem(r, col, it)
            if found:
                qedit = QLineEdit()
                qedit.setAlignment(Qt.AlignRight)
                qedit.setMaximumWidth(70)
                qedit.setFixedHeight(26)
                qedit.setText(str(int(sold)) if float(sold).is_integer() else str(sold))
                qedit.textChanged.connect(self._recompute)
                self._qty_edits[r] = qedit
                wrap = QWidget()
                wl = QHBoxLayout(wrap)
                wl.setContentsMargins(6, 3, 6, 3)
                wl.addWidget(qedit)
                self.table.setCellWidget(r, C_QTY, wrap)
            else:
                self.table.setItem(r, C_QTY, QTableWidgetItem(""))
            self.table.setItem(r, C_SUM, QTableWidgetItem(""))
            self.table.setRowHeight(r, 34)
        self._set_busy(False)
        self._recompute()

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.summary.setText("Ошибка запроса к Микадо")
        QMessageBox.critical(self, "Микадо", message)

    def _qty(self, r: int) -> int:
        edit = self._qty_edits[r] if r < len(self._qty_edits) else None
        if edit is None:
            return 0
        try:
            return max(0, int(edit.text().strip() or "0"))
        except ValueError:
            return 0

    def _recompute(self) -> None:
        positions = total_qty = 0
        total_sum = 0.0
        for r, (code, name, sold, offer) in enumerate(self._rows):
            if offer is None:
                continue
            qty = self._qty(r)
            line_sum = qty * offer.price_rur
            sit = self.table.item(r, C_SUM)
            if sit is not None:
                sit.setText(_fmt_money(line_sum) if qty else "")
                sit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for c in range(len(HEADERS)):
                cell = self.table.item(r, c)
                if cell is not None:
                    cell.setBackground(QColor("#F4F8FE") if qty else QColor(Qt.transparent))
            if qty:
                positions += 1
                total_qty += qty
                total_sum += line_sum
        note = self.app_settings.mikado_order_note or "Dazzle"
        if positions:
            self.summary.setText(
                f"В заказе: {positions} поз. · {total_qty} шт · {_fmt_money(total_sum)} ₽   ·   подпись: «{note} · Ozon»"
            )
        else:
            not_found = sum(1 for _, _, _, o in self._rows if o is None)
            self.summary.setText(
                f"Найдено в Микадо: {len(self._rows) - not_found} из {len(self._rows)} · укажите количество"
            )

    def _draft(self) -> list[tuple[str, int, str]]:
        out = []
        for r, (code, name, sold, offer) in enumerate(self._rows):
            if offer is None:
                continue
            qty = self._qty(r)
            if qty:
                out.append((offer.zakaz_code, qty, name))
        return out

    def _on_send(self) -> None:
        if self._busy:
            return
        client = make_client(self.app_settings)
        if client is None:
            QMessageBox.information(self, "Микадо", "Микадо не настроен.")
            return
        draft = self._draft()
        if not draft:
            QMessageBox.information(self, "Микадо", "Укажите количество хотя бы по одной найденной позиции.")
            return
        note = (self.app_settings.mikado_order_note or "Dazzle") + " · Ozon"
        lines = "\n".join(f"  • {code} × {qty}  ({name})" for code, qty, name in draft)
        answer = QMessageBox.question(
            self,
            "Отправить в корзину Микадо?",
            f"В корзину «Микадо» будет добавлено {len(draft)} поз.:\n\n{lines}\n\n"
            f"Примечание: «{note}».\n\n"
            "Это НЕ оформление заказа — заказ вы подтверждаете вручную в кабинете Микадо.\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._set_busy(True)
        self.summary.setText("Отправка в корзину Микадо…")
        items = [(code, qty) for code, qty, _ in draft]
        self._run(_CartWorker(client, items, note), self._on_send_done, self._on_error)

    def _on_send_done(self, results: list) -> None:
        self._set_busy(False)
        details = "\n".join(
            f"  • {code} × {qty} → {res.message or 'добавлено'} (в корзине: {res.ordered_qty})"
            for code, qty, res in results
        )
        QMessageBox.information(
            self,
            "Корзина Микадо",
            f"Готово. Добавлено позиций: {len(results)}.\n\n{details}\n\n"
            "Зайдите в кабинет Микадо, проверьте корзину и оформите заказ вручную.",
        )
        self._recompute()
