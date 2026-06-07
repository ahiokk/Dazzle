"""Вкладка «Заказ Zekkert → Микадо».

Безопасность: позиции уходят только в КОРЗИНУ Микадо (Basket_Add) с подписью в
примечании. Финальное оформление заказа — вручную в кабинете Микадо. Отправка в
корзину — отдельное явное действие с подтверждением.
"""
from __future__ import annotations

from .app_settings import AppSettings, save_app_settings
from . import secret_store
from .mikado import MikadoClient, MikadoError, MikadoOffer
from .qt_compat import (
    QCheckBox,
    QColor,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
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
)

HEADERS = ["Артикул", "Наименование", "Бренд", "Наличие", "Срок", "Цена, ₽", "Заказать", "Сумма, ₽"]
COL_CODE, COL_NAME, COL_BRAND, COL_STOCK, COL_SROK, COL_PRICE, COL_QTY, COL_SUM = range(8)

_SEND_BTN_QSS = (
    "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #E08A1E,stop:1 #C2700F);"
    "color:#FFFFFF;border:1px solid #A35E0B;border-radius:9px;font-weight:800;padding:0 18px;}"
    "QPushButton:hover{background:#C2700F;}"
    "QPushButton:disabled{background:#E7C79A;border-color:#E7C79A;color:#FBF4E8;}"
)
_BANNER_QSS = (
    "background:#FDF4E2;color:#92560A;border:1px solid #EFD9A6;"
    "border-radius:10px;padding:9px 12px;font-weight:600;"
)
_QTY_QSS = "border:1.5px solid #2563EB;border-radius:6px;padding:2px 6px;font-weight:700;color:#1E40AF;"
_QTY_QSS_EMPTY = "border:1px solid #CBD6E6;border-radius:6px;padding:2px 6px;"


def _fmt_money(value: float) -> str:
    out = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return out[:-3] if out.endswith(",00") else out


def _shadow(w: QWidget) -> QWidget:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(18); eff.setXOffset(0); eff.setYOffset(4)
    eff.setColor(QColor(15, 27, 61, 30)); w.setGraphicsEffect(eff)
    return w


# --------------------------------------------------------------------------- #
# Воркеры (сеть в фоне)
# --------------------------------------------------------------------------- #
class _SearchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, client: MikadoClient, code: str, from_stock_only: bool, brand: str) -> None:
        super().__init__()
        self._c = client; self._code = code; self._fso = from_stock_only; self._brand = brand

    def run(self) -> None:
        try:
            self.finished.emit(self._c.search(self._code, from_stock_only=self._fso, brand=self._brand))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _CartWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, client: MikadoClient, items: list[tuple[str, int]], note: str) -> None:
        super().__init__()
        self._c = client; self._items = items; self._note = note

    def run(self) -> None:
        try:
            results = []
            for code, qty in self._items:
                res = self._c.basket_add(code, qty, notes=self._note)
                results.append((code, qty, res))
            self.finished.emit(results)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class _IpWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, client: MikadoClient) -> None:
        super().__init__()
        self._c = client

    def run(self) -> None:
        try:
            self.finished.emit(self._c.get_my_ip())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# --------------------------------------------------------------------------- #
# Панель
# --------------------------------------------------------------------------- #
class MikadoPanel(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.setObjectName("mikadoRoot")
        self.main_window = main_window
        self._offers: list[MikadoOffer] = []
        self._qty_edits: list[QLineEdit] = []
        self._threads: list[QThread] = []
        self._busy = False
        self._build_ui()
        self.reload_settings()

    # -- settings/client --------------------------------------------------- #
    def _settings(self) -> AppSettings:
        return self.main_window.app_settings

    def _is_configured(self) -> bool:
        s = self._settings()
        return bool(s.mikado_client_code.strip() and s.mikado_password_enc.strip())

    def _client(self) -> MikadoClient | None:
        if not self._is_configured():
            return None
        s = self._settings()
        return MikadoClient(
            s.mikado_client_code.strip(),
            secret_store.decrypt(s.mikado_password_enc),
            base_url=s.mikado_base_url,
        )

    # -- UI ---------------------------------------------------------------- #
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        head = QFrame(self); head.setObjectName("topCard")
        hl = QHBoxLayout(head); hl.setContentsMargins(14, 10, 14, 10); hl.setSpacing(10)
        tbox = QVBoxLayout(); tbox.setSpacing(2)
        title = QLabel("Заказ Zekkert → Микадо"); title.setObjectName("titleLabel")
        sub = QLabel("Поставщик «Микадо» · позиции уходят в корзину, без автозаказа"); sub.setObjectName("subtitleLabel")
        tbox.addWidget(title); tbox.addWidget(sub); hl.addLayout(tbox); hl.addStretch(1)
        self.conn_label = QLabel("Микадо: не настроено"); self.conn_label.setObjectName("totalsPill")
        hl.addWidget(self.conn_label)
        self.settings_btn = QPushButton("Настроить Микадо"); self.settings_btn.setObjectName("subtleBtn")
        self.settings_btn.clicked.connect(self._open_settings)
        hl.addWidget(self.settings_btn)
        _shadow(head); outer.addWidget(head)

        search = QFrame(self); search.setObjectName("topCard")
        sl = QHBoxLayout(search); sl.setContentsMargins(14, 10, 14, 10); sl.setSpacing(8)
        sl.addWidget(QLabel("Бренд:"))
        self.brand_combo = QComboBox(); self.brand_combo.addItems(["Zekkert", "(любой)"]); self.brand_combo.setMinimumWidth(130)
        sl.addWidget(self.brand_combo)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Артикул или название…")
        self.search_edit.returnPressed.connect(self._on_search)
        sl.addWidget(self.search_edit, 1)
        self.stock_cb = QCheckBox("Только в наличии")
        sl.addWidget(self.stock_cb)
        self.find_btn = QPushButton("Найти"); self.find_btn.setObjectName("primaryBtn"); self.find_btn.setMinimumWidth(110)
        self.find_btn.clicked.connect(self._on_search)
        sl.addWidget(self.find_btn)
        _shadow(search); outer.addWidget(search)

        banner = QLabel(
            "  ⓘ  Dazzle добавляет позиции в корзину «Микадо». Заказ вы оформляете и "
            "подтверждаете вручную в личном кабинете Микадо — автоматической отправки нет."
        )
        banner.setWordWrap(True); banner.setStyleSheet(_BANNER_QSS)
        outer.addWidget(banner)

        self.table = QTableWidget(0, len(HEADERS), self)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for c in (COL_CODE, COL_BRAND, COL_STOCK, COL_SROK, COL_PRICE, COL_QTY, COL_SUM):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(COL_QTY, 90)
        self.empty_hint = QLabel("Введите артикул и нажмите «Найти».")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setStyleSheet("color:#94A3B8;font-size:11pt;padding:40px;")
        outer.addWidget(self.empty_hint)
        outer.addWidget(self.table, 1)
        self.table.setVisible(False)

        foot = QFrame(self); foot.setObjectName("topCard")
        fl = QHBoxLayout(foot); fl.setContentsMargins(14, 8, 14, 8); fl.setSpacing(8)
        self.summary = QLabel("В заказе: 0 позиций · 0 ₽"); self.summary.setObjectName("totalsPill")
        fl.addWidget(self.summary); fl.addStretch(1)
        self.clear_btn = QPushButton("Очистить"); self.clear_btn.setObjectName("subtleBtn")
        self.clear_btn.clicked.connect(self._clear)
        fl.addWidget(self.clear_btn)
        self.basket_btn = QPushButton("Корзина Микадо"); self.basket_btn.setObjectName("subtleBtn")
        self.basket_btn.clicked.connect(self._show_basket)
        fl.addWidget(self.basket_btn)
        self.send_btn = QPushButton("Отправить в корзину Микадо")
        self.send_btn.setMinimumHeight(38); self.send_btn.setMinimumWidth(240)
        self.send_btn.setStyleSheet(_SEND_BTN_QSS)
        self.send_btn.clicked.connect(self._on_send)
        fl.addWidget(self.send_btn)
        _shadow(foot); outer.addWidget(foot)

    # -- worker runner ----------------------------------------------------- #
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
        for b in (self.find_btn, self.send_btn, self.basket_btn, self.clear_btn):
            b.setEnabled(not busy)

    # -- actions ----------------------------------------------------------- #
    def _open_settings(self) -> None:
        opener = getattr(self.main_window, "_open_settings_dialog", None)
        if callable(opener):
            opener()

    def reload_settings(self) -> None:
        s = self._settings()
        if self._is_configured():
            self.conn_label.setText(f"Микадо: код {s.mikado_client_code.strip()}")
            self.settings_btn.setVisible(False)
        else:
            self.conn_label.setText("Микадо: не настроено")
            self.settings_btn.setVisible(True)
        configured = self._is_configured()
        self.find_btn.setEnabled(configured)
        self.send_btn.setEnabled(configured)
        self.basket_btn.setEnabled(configured)

    def _on_search(self) -> None:
        if self._busy:
            return
        client = self._client()
        if client is None:
            QMessageBox.information(self, "Микадо", "Сначала укажите код клиента и пароль в Настройках.")
            return
        code = self.search_edit.text().strip()
        if not code:
            QMessageBox.information(self, "Микадо", "Введите артикул или название для поиска.")
            return
        brand = "" if self.brand_combo.currentText() == "(любой)" else self.brand_combo.currentText()
        self._set_busy(True)
        self.summary.setText("Поиск в Микадо…")
        worker = _SearchWorker(client, code, self.stock_cb.isChecked(), brand)
        self._run(worker, self._on_search_done, self._on_error)

    def _on_search_done(self, offers: list[MikadoOffer]) -> None:
        self._set_busy(False)
        self._fill(offers)

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.summary.setText("Ошибка запроса к Микадо")
        QMessageBox.critical(self, "Микадо", message)

    def _fill(self, offers: list[MikadoOffer]) -> None:
        self._offers = list(offers)
        self._qty_edits = []
        self.table.setRowCount(0)
        if not offers:
            self.empty_hint.setText("Ничего не найдено в Микадо.")
            self.empty_hint.setVisible(True)
            self.table.setVisible(False)
            self._recompute()
            return
        self.empty_hint.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(len(offers))
        mono_cols = {COL_CODE, COL_SROK, COL_PRICE, COL_SUM}
        for r, o in enumerate(offers):
            cells = {
                COL_CODE: o.zakaz_code, COL_NAME: o.name, COL_BRAND: o.brand,
                COL_STOCK: o.on_stocks, COL_SROK: o.srok, COL_PRICE: _fmt_money(o.price_rur),
            }
            for col, val in cells.items():
                it = QTableWidgetItem(val)
                if col in mono_cols:
                    f = it.font(); f.setFamily("Consolas"); it.setFont(f)
                if col in (COL_STOCK, COL_SROK, COL_PRICE):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, col, it)
            qedit = QLineEdit(); qedit.setPlaceholderText("0"); qedit.setAlignment(Qt.AlignRight)
            qedit.setMaximumWidth(72); qedit.setStyleSheet(_QTY_QSS_EMPTY)
            qedit.textChanged.connect(self._recompute)
            self._qty_edits.append(qedit)
            wrap = QWidget(); wl = QHBoxLayout(wrap); wl.setContentsMargins(6, 3, 6, 3); wl.addWidget(qedit)
            self.table.setCellWidget(r, COL_QTY, wrap)
            self.table.setItem(r, COL_SUM, QTableWidgetItem(""))
            self.table.setRowHeight(r, 32)
        self._recompute()

    def _qty(self, idx: int) -> int:
        try:
            return max(0, int(self._qty_edits[idx].text().strip() or "0"))
        except (ValueError, IndexError):
            return 0

    def _recompute(self) -> None:
        positions = 0
        total_qty = 0
        total_sum = 0.0
        mono = None
        for i, o in enumerate(self._offers):
            qty = self._qty(i)
            line_sum = qty * o.price_rur
            sit = self.table.item(i, COL_SUM)
            if sit is not None:
                sit.setText(_fmt_money(line_sum) if qty else "")
                sit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                f = sit.font(); f.setFamily("Consolas"); f.setBold(qty > 0); sit.setFont(f)
            if i < len(self._qty_edits):
                self._qty_edits[i].setStyleSheet(_QTY_QSS if qty else _QTY_QSS_EMPTY)
            for c in range(len(HEADERS)):
                cell = self.table.item(i, c)
                if cell is not None:
                    cell.setBackground(QColor("#F4F8FE") if qty else QColor(Qt.transparent))
            if qty:
                positions += 1
                total_qty += qty
                total_sum += line_sum
        note = self._settings().mikado_order_note or "Dazzle"
        if positions:
            self.summary.setText(
                f"В заказе: {positions} поз. · {total_qty} шт · {_fmt_money(total_sum)} ₽   ·   подпись: «{note}»"
            )
        else:
            self.summary.setText("В заказе: 0 позиций · 0 ₽")

    def _draft(self) -> list[tuple[str, int, str, float]]:
        out = []
        for i, o in enumerate(self._offers):
            qty = self._qty(i)
            if qty:
                out.append((o.zakaz_code, qty, o.name, o.price_rur))
        return out

    def _clear(self) -> None:
        for e in self._qty_edits:
            e.clear()
        self._recompute()

    def _on_send(self) -> None:
        if self._busy:
            return
        client = self._client()
        if client is None:
            QMessageBox.information(self, "Микадо", "Сначала настройте Микадо.")
            return
        draft = self._draft()
        if not draft:
            QMessageBox.information(self, "Микадо", "Укажите количество хотя бы по одной позиции.")
            return
        note = self._settings().mikado_order_note or "Dazzle"
        lines = "\n".join(f"  • {code} × {qty}  ({name})" for code, qty, name, _ in draft)
        total = sum(qty * price for _, qty, _, price in draft)
        answer = QMessageBox.question(
            self,
            "Отправить в корзину Микадо?",
            f"В корзину «Микадо» будет добавлено {len(draft)} поз. на сумму {_fmt_money(total)} ₽:\n\n"
            f"{lines}\n\nПримечание к позициям: «{note}».\n\n"
            "Это НЕ оформление заказа — заказ вы подтверждаете вручную в кабинете Микадо.\n"
            "Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._set_busy(True)
        self.summary.setText("Отправка в корзину Микадо…")
        items = [(code, qty) for code, qty, _, _ in draft]
        worker = _CartWorker(client, items, note)
        self._run(worker, self._on_send_done, self._on_error)

    def _on_send_done(self, results: list) -> None:
        self._set_busy(False)
        ok = sum(1 for _, _, res in results if res.ordered_qty > 0 or (res.message or "").lower() in ("ok", "ок", ""))
        details = "\n".join(
            f"  • {code} × {qty} → {res.message or 'добавлено'} (в корзине: {res.ordered_qty})"
            for code, qty, res in results
        )
        QMessageBox.information(
            self,
            "Корзина Микадо",
            f"Готово. Позиции добавлены в корзину Микадо ({ok} из {len(results)}).\n\n{details}\n\n"
            "Зайдите в личный кабинет Микадо, проверьте корзину и оформите заказ вручную.",
        )
        self._recompute()

    def _show_basket(self) -> None:
        if self._busy:
            return
        client = self._client()
        if client is None:
            QMessageBox.information(self, "Микадо", "Сначала настройте Микадо.")
            return

        class _ListWorker(QObject):
            finished = Signal(object)
            failed = Signal(str)

            def __init__(self, c):
                super().__init__(); self._c = c

            def run(self):
                try:
                    self.finished.emit(self._c.basket_list())
                except Exception as exc:  # noqa: BLE001
                    self.failed.emit(str(exc))

        self._set_busy(True)
        self._run(_ListWorker(client), self._on_basket_done, self._on_error)

    def _on_basket_done(self, lines: list) -> None:
        self._set_busy(False)
        if not lines:
            QMessageBox.information(self, "Корзина Микадо", "Корзина Микадо пуста.")
            return
        body = "\n".join(
            f"  • {ln.zakaz_code} × {int(ln.qty)} — {ln.name}  [{ln.status}]"
            + (f"  ⟨{ln.notes}⟩" if ln.notes else "")
            for ln in lines
        )
        QMessageBox.information(
            self, "Корзина Микадо",
            f"В корзине Микадо {len(lines)} поз.:\n\n{body}\n\n"
            "Оформление заказа — вручную в кабинете Микадо.",
        )
