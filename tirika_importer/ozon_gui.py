"""Вкладка Ozon: разбор выгрузки отправлений и продажа в Tirika.

Жила внутри gui.py; вынесена отдельно — вкладка самостоятельная, и правки
в накладных её больше не задевают. Показывается только в редакции AUTO255
(version.ozon_enabled).
"""
from __future__ import annotations

from pathlib import Path
from .app_settings import AppSettings, load_app_settings
from .db import TirikaDB, TirikaDBError
from .matcher import GoodsMatcher
from .models import (
    OzonComponentLine,
    OzonImportOptions,
    OzonImportResult,
    OzonSaleDocument,
    ParsedOzonCsv,
)
from .ozon import OzonParseError, match_ozon_lines, parse_ozon_csv, recalculate_ozon_prices
from .qt_compat import (
    QApplication,
    QColor,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QThread,
    QVBoxLayout,
    QWidget,
    Qt,
    qt_exec,
)
from .theme import APP_STYLESHEET
from .workers import OzonImportWorker
from .constants import (
    OZ_COL_LINE,
    OZ_COL_QTY,
    OZ_COL_PRICE,
    OZ_COL_SUM,
    OZ_COL_REMAINDER,
    OZ_COL_ACTION,
)
from .gui_common import GoodsPickerDialog, _copy_current_cell, _copy_current_row, _fmt_number


class OzonDialog(QDialog):
    def __init__(
        self,
        db: TirikaDB,
        matcher: GoodsMatcher,
        app_settings: AppSettings,
        suppliers: list[tuple[int, str]],
        users: list[tuple[int, str]],
        shops: list[tuple[int, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.matcher = matcher
        self.app_settings = app_settings
        self.suppliers = suppliers
        self.users = users
        self.shops = shops
        self.parsed: ParsedOzonCsv | None = None
        self.ozon_sales: list[OzonSaleDocument] = []
        self._line_by_row: list[OzonComponentLine] = []
        self._table_locked = False
        self._import_thread: QThread | None = None
        self._import_worker: OzonImportWorker | None = None

        self.setWindowTitle("Ozon CSV")
        self.resize(1320, 760)
        self.setStyleSheet(APP_STYLESHEET)
        self._build_ui()

    def closeEvent(self, event) -> None:
        if self._import_thread is not None and self._import_thread.isRunning():
            QMessageBox.warning(self, "Ozon", "Дождитесь завершения операции Ozon.")
            event.ignore()
            return
        super().closeEvent(event)

    def _order_from_mikado(self) -> None:
        """Заказать проданные на Ozon позиции у поставщика Микадо (в корзину)."""
        from .mikado_gui import MikadoOrderDialog, make_client

        # Перечитываем настройки с диска: копия в панели Ozon могла устареть
        # (креды Микадо могли быть введены уже после открытия вкладки).
        self.app_settings = load_app_settings()
        if make_client(self.app_settings) is None:
            QMessageBox.information(
                self,
                "Микадо",
                "Не вижу данные Микадо. Откройте «Настройки» → раздел «Микадо», "
                "введите код клиента и пароль и нажмите «Сохранить», затем повторите.",
            )
            return
        lines = list(self.parsed.lines) if self.parsed else []
        agg: dict[str, dict] = {}
        for ln in lines:
            if ln.action != "import":
                continue
            qty = float(ln.quantity or 0)
            if qty <= 0:
                continue
            code = (ln.matched_product_code or ln.article or ln.source_article or "").strip()
            if not code:
                continue
            name = ln.matched_name or ln.name or code
            if code in agg:
                agg[code]["qty"] += qty
            else:
                agg[code] = {"name": name, "qty": qty}
        items = [(code, v["name"], v["qty"]) for code, v in agg.items()]
        if not items:
            QMessageBox.information(
                self,
                "Микадо",
                "Нет проданных позиций к заказу. Загрузите CSV Ozon и убедитесь, "
                "что для нужных позиций выбрано действие «import».",
            )
            return
        dlg = MikadoOrderDialog(self, self.app_settings, items)
        qt_exec(dlg)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QFrame(self)
        header.setObjectName("topCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(6)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        file_row.addWidget(QLabel("CSV Ozon:"))
        self.file_edit = QLineEdit(self)
        self.file_edit.setPlaceholderText("Выберите postings.csv от Ozon")
        file_row.addWidget(self.file_edit, 1)
        self.browse_btn = QPushButton("Выбрать", self)
        self.browse_btn.setObjectName("subtleBtn")
        self.load_btn = QPushButton("Загрузить", self)
        self.load_btn.setObjectName("primaryBtn")
        file_row.addWidget(self.browse_btn)
        file_row.addWidget(self.load_btn)
        header_layout.addLayout(file_row)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        settings_row.addWidget(QLabel("Из:"))
        self.source_shop_combo = QComboBox(self)
        for sid, name in self.shops:
            self.source_shop_combo.addItem(f"{name} [{sid}]", userData=int(sid))
        self._set_combo_by_data(self.source_shop_combo, self._default_shop_id("авто", 0))
        settings_row.addWidget(self.source_shop_combo)

        settings_row.addWidget(QLabel("В:"))
        self.target_shop_combo = QComboBox(self)
        for sid, name in self.shops:
            self.target_shop_combo.addItem(f"{name} [{sid}]", userData=int(sid))
        self._set_combo_by_data(self.target_shop_combo, self._default_shop_id("озон", 1))
        settings_row.addWidget(self.target_shop_combo)

        settings_row.addWidget(QLabel("Пользователь:"))
        self.user_combo = QComboBox(self)
        for uid, name in self.users:
            self.user_combo.addItem(f"{name} [{uid}]", userData=int(uid))
        self._set_combo_by_data(self.user_combo, self.app_settings.user_id)
        settings_row.addWidget(self.user_combo)

        self.payment_label = QLabel("Оплата: Безнал", self)
        self.payment_label.setObjectName("subtitleLabel")
        self.payment_label.setMinimumWidth(110)
        settings_row.addWidget(self.payment_label)

        self.sale_number_label = QLabel("Номер: авто", self)
        self.sale_number_label.setObjectName("subtitleLabel")
        self.sale_number_label.setMinimumWidth(95)
        settings_row.addWidget(self.sale_number_label)

        self.summary_label = QLabel("Строк: 0 | К импорту: 0 | Сумма: 0", self)
        self.summary_label.setObjectName("totalsPill")
        self.summary_label.setMinimumHeight(32)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        settings_row.addWidget(self.summary_label, 1)
        header_layout.addLayout(settings_row)

        sale_row = QHBoxLayout()
        sale_row.setSpacing(8)
        sale_row.addWidget(QLabel("Запись:"))
        self.sale_mode_combo = QComboBox(self)
        self.sale_mode_combo.addItem("Создать новую продажу", userData="new")
        self.sale_mode_combo.addItem("Добавить в существующую продажу", userData="existing")
        self.sale_mode_combo.setMaximumWidth(250)
        sale_row.addWidget(self.sale_mode_combo)

        self.existing_sale_combo = QComboBox(self)
        self.existing_sale_combo.setMinimumWidth(460)
        self.existing_sale_combo.setToolTip("Последние продажи Ozon: дата, номер, сумма, количество строк и краткое содержимое.")
        sale_row.addWidget(self.existing_sale_combo, 1)

        self.refresh_sales_btn = QPushButton("Обновить продажи", self)
        self.refresh_sales_btn.setObjectName("subtleBtn")
        self.refresh_sales_btn.setMinimumWidth(145)
        sale_row.addWidget(self.refresh_sales_btn)

        self.existing_sale_info = QLabel("", self)
        self.existing_sale_info.setObjectName("subtitleLabel")
        self.existing_sale_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sale_row.addWidget(self.existing_sale_info, 1)
        header_layout.addLayout(sale_row)
        root.addWidget(header)

        self.table = QTableWidget(self)
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels(
            [
                "№",
                "Заказ",
                "Отправление",
                "Артикул Ozon",
                "Код в БД",
                "Товар",
                "Кол-во",
                "Цена",
                "Сумма",
                "Остаток Авто",
                "Статус",
                "Действие",
                "Предупреждение",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(lambda _: self._pick_good_for_selected())
        root.addWidget(self.table, 1)

        footer = QFrame(self)
        footer.setObjectName("topCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 6)
        footer_layout.setSpacing(8)
        self.status_label = QLabel("Загрузите CSV Ozon.", self)
        self.status_label.setObjectName("subtitleLabel")
        footer_layout.addWidget(self.status_label, 1)
        self.pick_btn = QPushButton("Назначить товар вручную", self)
        self.pick_btn.setObjectName("subtleBtn")
        self.check_btn = QPushButton("Проверка", self)
        self.check_btn.setObjectName("subtleBtn")
        self.import_btn = QPushButton("Создать документы Ozon", self)
        self.import_btn.setObjectName("successBtn")
        self.mikado_btn = QPushButton("Заказать у Микадо", self)
        self.mikado_btn.setObjectName("subtleBtn")
        self.mikado_btn.setToolTip(
            "Заказать проданные позиции у поставщика Микадо (кладёт в корзину; "
            "заказ оформляется вручную в кабинете Микадо)."
        )
        self.close_btn = QPushButton("Закрыть", self)
        footer_layout.addWidget(self.pick_btn)
        footer_layout.addWidget(self.check_btn)
        footer_layout.addWidget(self.mikado_btn)
        footer_layout.addWidget(self.import_btn)
        footer_layout.addWidget(self.close_btn)
        root.addWidget(footer)

        for widget in (
            self.browse_btn,
            self.load_btn,
            self.source_shop_combo,
            self.target_shop_combo,
            self.user_combo,
            self.sale_mode_combo,
            self.existing_sale_combo,
            self.refresh_sales_btn,
            self.pick_btn,
            self.check_btn,
            self.import_btn,
            self.close_btn,
        ):
            widget.setMinimumHeight(32)

        self.browse_btn.clicked.connect(self._browse_file)
        self.load_btn.clicked.connect(self._load_csv)
        self.pick_btn.clicked.connect(self._pick_good_for_selected)
        self.check_btn.clicked.connect(lambda: self._run_import(dry_run=True))
        self.import_btn.clicked.connect(lambda: self._run_import(dry_run=False))
        self.mikado_btn.clicked.connect(self._order_from_mikado)
        self.close_btn.clicked.connect(self.reject)
        self.sale_mode_combo.currentIndexChanged.connect(self._on_sale_mode_changed)
        self.target_shop_combo.currentIndexChanged.connect(self._refresh_ozon_sales)
        self.refresh_sales_btn.clicked.connect(self._refresh_ozon_sales)
        self.existing_sale_combo.currentIndexChanged.connect(self._update_existing_sale_info)
        self.table.itemChanged.connect(self._on_table_item_changed)
        self._refresh_ozon_sales()
        self._on_sale_mode_changed()
        self._update_buttons()

    def _browse_file(self) -> None:
        start_dir = self.app_settings.invoices_dir.strip() or str(Path.home() / "Downloads")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите CSV Ozon",
            start_dir,
            "CSV files (*.csv);;All files (*.*)",
        )
        if file_path:
            self.file_edit.setText(file_path)

    def _refresh_ozon_sales(self) -> None:
        self.existing_sale_combo.blockSignals(True)
        self.existing_sale_combo.clear()
        self.ozon_sales = []
        try:
            target_shop_id = self._selected_data(self.target_shop_combo, 1)
            self.ozon_sales = self.db.list_ozon_sales(
                shop_id=target_shop_id,
                ozon_contractor_id=self._ozon_supplier_id(),
                limit=80,
            )
            for doc in self.ozon_sales:
                text = (
                    f"#{doc.waybill_id} | {doc.waybill_date.strftime('%d.%m.%Y %H:%M')} | "
                    f"номер {doc.number or 'без номера'} | {_fmt_number(doc.cost, 2)} | "
                    f"строк {doc.item_count} | {doc.display[:80]}"
                )
                self.existing_sale_combo.addItem(text, userData=doc.waybill_id)
        except Exception as exc:
            self.existing_sale_combo.addItem(f"Не удалось загрузить продажи: {exc}", userData=None)
        finally:
            self.existing_sale_combo.blockSignals(False)
        self._update_existing_sale_info()
        self._on_sale_mode_changed()

    def _on_sale_mode_changed(self) -> None:
        use_existing = self._sale_mode() == "existing"
        self.existing_sale_combo.setEnabled(use_existing)
        self.refresh_sales_btn.setEnabled(use_existing)
        self._update_existing_sale_info()
        self._update_summary()
        self._update_buttons()

    def _update_existing_sale_info(self) -> None:
        if self._sale_mode() != "existing":
            self.existing_sale_info.setText("Будет создана новая продажа Ozon.")
            self._update_buttons()
            return
        doc = self._selected_ozon_sale_doc()
        if doc is None:
            self.existing_sale_info.setText("Выберите продажу Ozon из списка.")
            self._update_buttons()
            return
        auto_number = self._auto_sale_number(existing_doc=doc)
        self.existing_sale_info.setText(
            f"Добавление в #{doc.waybill_id}: номер станет {auto_number or doc.number or 'без номера'}."
        )
        self._update_buttons()

    def _sale_mode(self) -> str:
        data = self.sale_mode_combo.currentData()
        return str(data or "new")

    def _selected_ozon_sale_doc(self) -> OzonSaleDocument | None:
        sale_id = self._selected_data(self.existing_sale_combo, 0)
        if sale_id <= 0:
            return None
        for doc in self.ozon_sales:
            if int(doc.waybill_id) == sale_id:
                return doc
        return None

    def _selected_existing_sale_id(self) -> int | None:
        if self._sale_mode() != "existing":
            return None
        doc = self._selected_ozon_sale_doc()
        return int(doc.waybill_id) if doc is not None else None

    def _auto_sale_number(self, *, existing_doc: OzonSaleDocument | None = None) -> str:
        import_lines = [line for line in self._line_by_row if line.action == "import"]
        card_keys = {
            (line.line_no, line.order_number, line.posting_number, line.source_article)
            for line in import_lines
        }
        add_count = len(card_keys) if card_keys else len(import_lines)
        if existing_doc is not None:
            old_number = str(existing_doc.number or "").strip()
            if old_number.isdigit():
                return str(int(old_number) + add_count)
            return old_number
        return str(add_count)

    def _load_csv(self) -> None:
        raw = self.file_edit.text().strip()
        if not raw:
            QMessageBox.warning(self, "Ozon", "Выберите CSV-файл Ozon.")
            return
        path = Path(raw)
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            source_shop_id = self._selected_data(self.source_shop_combo, 0)
            matcher = self.matcher
            if source_shop_id != int(self.app_settings.shop_id):
                catalog = self.db.load_goods_catalog(shop_id=source_shop_id)
                matcher = GoodsMatcher(catalog, article_match_field=self.app_settings.article_match_field)
                self.matcher = matcher
            parsed = parse_ozon_csv(path)
            match_ozon_lines(parsed, matcher)
        except (OzonParseError, TirikaDBError, Exception) as exc:
            QMessageBox.critical(self, "Ozon", f"Не удалось загрузить CSV Ozon:\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.parsed = parsed
        self._populate_table()
        self.status_label.setText(f"CSV загружен: {path.name}")
        self._update_buttons()

    def _populate_table(self) -> None:
        if self.parsed is None:
            return
        self._table_locked = True
        try:
            self.table.setRowCount(len(self.parsed.lines))
            self._line_by_row = list(self.parsed.lines)
            for row, line in enumerate(self._line_by_row):
                values = [
                    str(row + 1),
                    line.order_number,
                    line.posting_number,
                    line.source_article,
                    line.matched_product_code or line.article,
                    line.matched_name or line.name,
                    _fmt_number(line.quantity, 3),
                    _fmt_number(float(line.sale_price or 0.0), 2),
                    _fmt_number(float(line.sale_total or 0.0), 2),
                    "" if line.remainder_source is None else _fmt_number(float(line.remainder_source), 3),
                    self._status_text(line),
                    "",
                    line.warning,
                ]
                for col, value in enumerate(values):
                    if col == OZ_COL_ACTION:
                        continue
                    item = QTableWidgetItem(value)
                    if col in {OZ_COL_LINE, OZ_COL_QTY, OZ_COL_PRICE, OZ_COL_SUM, OZ_COL_REMAINDER}:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    if col not in {OZ_COL_QTY, OZ_COL_PRICE}:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self._paint_item(item, line)
                    self.table.setItem(row, col, item)

                combo = QComboBox(self.table)
                combo.addItem("import")
                combo.addItem("skip")
                combo.setCurrentText(line.action if line.action in {"import", "skip"} else "skip")
                combo.setProperty("actionKind", combo.currentText())
                combo.currentTextChanged.connect(lambda text, r=row: self._on_action_changed(r, text))
                self.table.setCellWidget(row, OZ_COL_ACTION, combo)
            self.table.resizeColumnsToContents()
        finally:
            self._table_locked = False
        self._update_summary()

    def _paint_item(self, item: QTableWidgetItem, line: OzonComponentLine) -> None:
        if line.action == "skip":
            item.setBackground(QColor("#fff1f2") if line.warning == "Товар отменен" else QColor("#fff7ed"))
            if line.warning == "Товар отменен":
                item.setForeground(QColor("#b91c1c"))
            return
        if line.match_status in {"found", "manual"}:
            item.setBackground(QColor("#dcfce7"))
        elif line.match_status == "ambiguous":
            item.setBackground(QColor("#fef3c7"))
        else:
            item.setBackground(QColor("#fee2e2"))

    def _status_text(self, line: OzonComponentLine) -> str:
        if line.match_status == "found":
            return "Найден"
        if line.match_status == "manual":
            return "Выбран вручную"
        if line.match_status == "ambiguous":
            return "Несколько"
        return "Не найден"

    def _on_action_changed(self, row: int, text: str) -> None:
        if self._table_locked or row < 0 or row >= len(self._line_by_row):
            return
        line = self._line_by_row[row]
        line.action = text if text in {"import", "skip"} else "skip"
        widget = self.table.cellWidget(row, OZ_COL_ACTION)
        if widget is not None:
            widget.setProperty("actionKind", line.action)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._update_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._table_locked:
            return
        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self._line_by_row):
            return
        line = self._line_by_row[row]
        if col == OZ_COL_QTY:
            try:
                line.quantity = max(0.0, float(item.text().replace(",", ".")))
                recalculate_ozon_prices(self._line_by_row)
                self._populate_table()
            except Exception:
                item.setText(_fmt_number(line.quantity, 3))
        elif col == OZ_COL_PRICE:
            try:
                line.sale_price = max(0.0, float(item.text().replace(",", ".")))
                line.sale_total = round(line.sale_price * line.quantity, 2)
                self._update_summary()
            except Exception:
                item.setText(_fmt_number(float(line.sale_price or 0.0), 2))

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        action_pick = menu.addAction("Назначить товар вручную")
        action_import = menu.addAction("Поставить import")
        action_skip = menu.addAction("Поставить skip")
        menu.addSeparator()
        action_copy_cell = menu.addAction("Копировать ячейку")
        action_copy_row = menu.addAction("Копировать строку")
        chosen = qt_exec(menu, self.table.viewport().mapToGlobal(pos))
        if chosen == action_pick:
            self._pick_good_for_selected()
        elif chosen == action_import:
            self._set_selected_actions("import")
        elif chosen == action_skip:
            self._set_selected_actions("skip")
        elif chosen == action_copy_cell:
            _copy_current_cell(self.table)
        elif chosen == action_copy_row:
            _copy_current_row(self.table)

    def _set_selected_actions(self, action: str) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        for row in rows:
            if 0 <= row < len(self._line_by_row):
                self._line_by_row[row].action = action
                combo = self.table.cellWidget(row, OZ_COL_ACTION)
                if isinstance(combo, QComboBox):
                    combo.setCurrentText(action)
        self._update_summary()

    def _pick_good_for_selected(self) -> None:
        if self.parsed is None:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._line_by_row):
            QMessageBox.information(self, "Ozon", "Выберите строку товара.")
            return
        line = self._line_by_row[row]
        dialog = GoodsPickerDialog(
            self.matcher,
            line.article or line.source_article,
            line.candidates,
            self,
        )
        if qt_exec(dialog) != QDialog.Accepted or dialog.selected_good_id is None:
            return
        good = self.matcher.catalog.get(dialog.selected_good_id)
        if good is None:
            QMessageBox.warning(self, "Ozon", "Выбранный товар не найден в каталоге.")
            return
        line.matched_good_id = good.good_id
        line.matched_product_code = good.product_code
        line.matched_name = good.name
        line.matched_buy_price = good.buy_price
        line.existing_sell_price = good.sell_price
        line.remainder_source = good.remainder
        line.matched_tax_mode = good.tax_mode
        line.match_status = "manual"
        line.match_method = "manual"
        line.action = "import"
        line.warning = ""
        recalculate_ozon_prices(self._line_by_row)
        self._populate_table()

    def _run_import(self, dry_run: bool) -> None:
        if self.parsed is None:
            QMessageBox.warning(self, "Ozon", "Сначала загрузите CSV Ozon.")
            return
        if self._import_thread is not None and self._import_thread.isRunning():
            return
        import_count = sum(1 for line in self.parsed.lines if line.action == "import")
        skip_count = len(self.parsed.lines) - import_count
        if import_count <= 0:
            QMessageBox.warning(self, "Ozon", "Нет строк с действием import.")
            return
        existing_sale_id = self._selected_existing_sale_id()
        if self._sale_mode() == "existing" and existing_sale_id is None:
            QMessageBox.warning(self, "Ozon", "Выберите существующую продажу Ozon.")
            return
        if not dry_run:
            action_text = (
                f"Добавить товары в продажу #{existing_sale_id}?"
                if existing_sale_id is not None
                else "Создать перемещение и новую продажу Ozon?"
            )
            answer = QMessageBox.question(
                self,
                "Подтверждение Ozon",
                f"Будет импортировано строк: {import_count}\n"
                f"Будет пропущено строк: {skip_count}\n\n"
                f"{action_text}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        options = OzonImportOptions(
            user_id=self._selected_data(self.user_combo, self.app_settings.user_id),
            source_shop_id=self._selected_data(self.source_shop_combo, 0),
            target_shop_id=self._selected_data(self.target_shop_combo, 1),
            ozon_contractor_id=self._ozon_supplier_id(),
            payment_type=1,
            dry_run=dry_run,
            backup_before_import=self.app_settings.backup_before_import,
            sale_number="",
            existing_sale_waybill_id=existing_sale_id,
        )
        self._set_busy(True)
        self._import_thread = QThread(self)
        self._import_worker = OzonImportWorker(self.db, self.parsed, options)
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.failed.connect(self._on_import_failed)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.failed.connect(self._import_thread.quit)
        self._import_thread.finished.connect(self._cleanup_import_worker)
        self._import_thread.start()

    def _on_import_finished(self, result: OzonImportResult) -> None:
        self._set_busy(False)
        title = "Проверка Ozon" if result.dry_run else "Ozon импорт"
        doc_text = (
            "Проверка прошла успешно, запись не выполнялась."
            if result.dry_run
            else f"Документы Ozon записаны: перемещение #{result.transfer_waybill_id}, продажа #{result.sale_waybill_id}."
        )
        warnings_text = ""
        if result.warnings:
            warnings_text = "\n\nПредупреждения:\n" + "\n".join(f"- {w}" for w in result.warnings[:12])
            if len(result.warnings) > 12:
                warnings_text += f"\n... еще {len(result.warnings) - 12}"
        QMessageBox.information(
            self,
            title,
            f"{doc_text}\n\n"
            f"Импортировано строк: {result.imported_lines}\n"
            f"SKIP: {result.skipped_lines}\n"
            f"Отправлений: {result.posting_count}\n"
            f"Сумма продажи: {_fmt_number(result.sale_cost, 2)}"
            f"{warnings_text}",
        )
        if not result.dry_run:
            self.accept()

    def _on_import_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Ozon", f"Операция Ozon не выполнена:\n{message}")

    def _cleanup_import_worker(self) -> None:
        if self._import_worker is not None:
            self._import_worker.deleteLater()
            self._import_worker = None
        if self._import_thread is not None:
            self._import_thread.deleteLater()
            self._import_thread = None
        self._update_buttons()

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.browse_btn,
            self.load_btn,
            self.sale_mode_combo,
            self.existing_sale_combo,
            self.refresh_sales_btn,
            self.pick_btn,
            self.check_btn,
            self.import_btn,
            self.close_btn,
        ):
            widget.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.status_label.setText("Операция Ozon выполняется...")
        else:
            QApplication.restoreOverrideCursor()
            self._on_sale_mode_changed()

    def _update_summary(self) -> None:
        if self.parsed is None:
            self.summary_label.setText("Строк: 0 | К импорту: 0 | Сумма: 0")
            self.sale_number_label.setText("Номер: авто")
            return
        import_lines = [line for line in self.parsed.lines if line.action == "import"]
        total = sum(float(line.sale_total or 0.0) for line in import_lines)
        found = sum(1 for line in self.parsed.lines if line.match_status in {"found", "manual"})
        ambiguous = sum(1 for line in self.parsed.lines if line.match_status == "ambiguous")
        missing = sum(1 for line in self.parsed.lines if line.match_status == "not_found")
        selected_doc = self._selected_ozon_sale_doc() if self._sale_mode() == "existing" else None
        self.sale_number_label.setText(f"Номер: {self._auto_sale_number(existing_doc=selected_doc) or 'авто'}")
        self.summary_label.setText(
            f"Строк: {len(self.parsed.lines)} | К импорту: {len(import_lines)} | "
            f"Сумма: {_fmt_number(total, 2)} | Найдено: {found} | Неоднозначно: {ambiguous} | Не найдено: {missing}"
        )
        self._update_existing_sale_info()

    def _update_buttons(self) -> None:
        loaded = self.parsed is not None
        self.pick_btn.setEnabled(loaded)
        self.check_btn.setEnabled(loaded)
        self.import_btn.setEnabled(loaded and (self._sale_mode() != "existing" or self._selected_existing_sale_id() is not None))

    def _default_shop_id(self, needle: str, fallback: int) -> int:
        needle = needle.lower()
        for shop_id, name in self.shops:
            if needle in name.lower():
                return int(shop_id)
        return fallback

    def _ozon_supplier_id(self) -> int:
        for supplier_id, name in self.suppliers:
            if "озон" in name.lower():
                return int(supplier_id)
        return 115

    @staticmethod
    def _selected_data(combo: QComboBox, default: int) -> int:
        data = combo.currentData()
        try:
            return int(data)
        except Exception:
            return default

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, target: int) -> None:
        for idx in range(combo.count()):
            if int(combo.itemData(idx) or -999999) == int(target):
                combo.setCurrentIndex(idx)
                return


class OzonPanel(OzonDialog):
    """Встраиваемый во вкладку вариант окна Ozon (без модального закрытия)."""

    def __init__(self, *args, on_imported=None, **kwargs):
        self._on_imported_cb = on_imported
        super().__init__(*args, **kwargs)
        self.setWindowFlags(Qt.Widget)
        close_btn = getattr(self, "close_btn", None)
        if close_btn is not None:
            close_btn.setVisible(False)

    def accept(self):
        cb = getattr(self, "_on_imported_cb", None)
        if callable(cb):
            cb()

    def reject(self):
        pass
