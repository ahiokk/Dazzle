from __future__ import annotations

import copy
from datetime import datetime
import os
from pathlib import Path
import re
import traceback

from PySide6.QtCore import QByteArray, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .app_settings import AppSettings, load_app_settings, save_app_settings
from .config import load_config
from .db import (
    ImportValidationError,
    TirikaDB,
    TirikaDBError,
    calculate_suggested_sell_price,
    normalize_article,
    normalize_text_field,
)
from .matcher import GoodsMatcher
from .models import ImportOptions, ImportResult, InvoiceLine, MatchCandidate, ParsedInvoice
from .parsers import InvoiceParseError, parse_invoice_file
from .startup import StartupError, disable_startup, enable_startup, is_enabled, is_supported
from .updater import UpdateError, UpdateInfo, check_for_update, download_installer, run_installer
from .version import APP_NAME, APP_VERSION


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

MAX_HISTORY_STATES = 80

PAYMENT_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Наличные", 0),
    ("Безнал", 1),
    ("Карта", 5),
    ("QR", 7),
)


APP_STYLESHEET = """
QWidget {
    background: #f4f6fb;
    color: #1f2a37;
    font-family: Segoe UI;
    font-size: 10pt;
}
QMainWindow {
    background: #eef2f9;
}
QFrame#topCard, QFrame#logCard {
    background: #ffffff;
    border: 1px solid #d7e0ec;
    border-radius: 10px;
}
QLabel#titleLabel {
    font-size: 18pt;
    font-weight: 700;
    color: #0f172a;
}
QLabel#subtitleLabel {
    color: #475569;
    font-size: 10pt;
}
QLabel#totalsPill {
    color: #0f2b60;
    font-size: 11pt;
    font-weight: 700;
    background: #eaf2ff;
    border: 1px solid #c7d7f2;
    border-radius: 8px;
    padding: 6px 10px;
}
QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #c7d3e3;
    border-radius: 8px;
    padding: 6px 8px;
}
QLineEdit:focus, QComboBox:focus, QTableWidget:focus, QPlainTextEdit:focus {
    border: 1px solid #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QPushButton {
    background: #e6edf8;
    color: #0f172a;
    border: 1px solid #c7d3e3;
    border-radius: 8px;
    padding: 7px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background: #dbe7f8;
}
QPushButton#primaryBtn {
    background: #2563eb;
    color: #ffffff;
    border: 1px solid #1f56cd;
}
QPushButton#primaryBtn:hover {
    background: #1d4ed8;
}
QPushButton#successBtn {
    background: #0f766e;
    color: #ffffff;
    border: 1px solid #0b5f58;
}
QPushButton#successBtn:hover {
    background: #0b5f58;
}
QGroupBox {
    border: 1px solid #dbe3ef;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    background: #fbfcff;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #334155;
}
QTabWidget::pane {
    border: 1px solid #d2ddec;
    border-radius: 10px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #e9eff9;
    border: 1px solid #c6d4e8;
    color: #334155;
    padding: 8px 14px;
    margin-right: 6px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #2563eb;
    border: 1px solid #1f56cd;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background: #dbe7f8;
    color: #1e3a8a;
}
QHeaderView::section {
    background: #eff4fb;
    color: #1e293b;
    border: 0;
    border-right: 1px solid #d3deec;
    border-bottom: 1px solid #cbd6e4;
    padding: 7px 6px;
    font-weight: 700;
}
QTableWidget {
    gridline-color: #e2e8f0;
    alternate-background-color: #f8fbff;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QCheckBox::indicator:unchecked {
    border: 1px solid #9fb0c8;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    border: 1px solid #2563eb;
    border-radius: 4px;
    background: #2563eb;
}
QToolButton#helpBtn {
    background: #eef4ff;
    color: #1d4ed8;
    border: 1px solid #9db5df;
    border-radius: 9px;
    font-weight: 700;
    padding: 0;
}
QToolButton#helpBtn:hover {
    background: #dce9ff;
}
QToolButton#debugToggleBtn {
    background: #dbe7f8;
    border: 1px solid #9fb0c8;
    border-radius: 6px;
    color: #1e3a8a;
    font-size: 8pt;
    font-weight: 700;
    padding: 0 4px;
}
QToolButton#debugToggleBtn:checked {
    background: #2563eb;
    border: 1px solid #1f56cd;
    color: #ffffff;
}
QFrame#resultHeader {
    background: #f8fbff;
    border: 1px solid #d5e3f7;
    border-radius: 10px;
}
QLabel#resultStateOk {
    background: #dcfce7;
    color: #166534;
    border: 1px solid #86efac;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}
QLabel#resultStateDry {
    background: #dbeafe;
    color: #1d4ed8;
    border: 1px solid #93c5fd;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}
QFrame#metricCard {
    background: #ffffff;
    border: 1px solid #d8e3f1;
    border-radius: 10px;
}
QLabel#metricTitle {
    color: #64748b;
    font-size: 9pt;
}
QLabel#metricValue {
    color: #0f172a;
    font-size: 14pt;
    font-weight: 700;
}
QListWidget#warningsList {
    background: #ffffff;
    border: 1px solid #c7d3e3;
    border-radius: 8px;
    padding: 4px;
}
QLabel#resultTagImport {
    background: #dcfce7;
    color: #14532d;
    border: 1px solid #86efac;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}
QLabel#resultTagSkip {
    background: #eef2f7;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}
QLabel#resultTagCreate {
    background: #e0ecff;
    color: #1e3a8a;
    border: 1px solid #9ab8ea;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: 700;
}
"""


class GoodsPickerDialog(QDialog):
    def __init__(
        self,
        matcher: GoodsMatcher,
        initial_query: str,
        initial_candidates: list[MatchCandidate],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Выбор товара")
        self.resize(980, 560)
        self.matcher = matcher
        self.selected_good_id: int | None = None
        self.setStyleSheet(APP_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        top = QHBoxLayout()
        root.addLayout(top)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Поиск по артикулу / названию / бренду")
        self.search_edit.setText(initial_query)
        top.addWidget(self.search_edit, 1)

        self.search_btn = QPushButton("Найти", self)
        self.search_btn.setObjectName("primaryBtn")
        top.addWidget(self.search_btn)

        self.table = QTableWidget(self)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["good_id", "Код", "Наименование", "Бренд", "Закуп", "Продажа", "Остаток", "Метод", "Score"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: _show_table_copy_menu(self.table, pos, self)
        )
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        root.addLayout(buttons)
        self.select_btn = QPushButton("Выбрать", self)
        self.select_btn.setObjectName("successBtn")
        self.cancel_btn = QPushButton("Отмена", self)
        buttons.addStretch(1)
        buttons.addWidget(self.select_btn)
        buttons.addWidget(self.cancel_btn)

        self.search_btn.clicked.connect(self.refresh)
        self.search_edit.returnPressed.connect(self.refresh)
        self.select_btn.clicked.connect(self.accept_selected)
        self.cancel_btn.clicked.connect(self.reject)
        self.table.itemDoubleClicked.connect(lambda _: self.accept_selected())

        if initial_candidates:
            self._set_rows(initial_candidates)
        else:
            self.refresh()

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        rows = self.matcher.search_goods(query, limit=250)
        self._set_rows(rows)

    def accept_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        self.selected_good_id = int(item.text())
        self.accept()

    def _set_rows(self, rows: list[MatchCandidate]) -> None:
        self.table.setRowCount(len(rows))
        for i, cand in enumerate(rows):
            values = [
                str(cand.good_id),
                cand.product_code,
                cand.name,
                cand.manufacturer,
                f"{cand.buy_price:.2f}",
                f"{cand.sell_price:.2f}",
                f"{cand.remainder:.2f}",
                cand.match_method,
                f"{cand.score:.3f}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in {0, 4, 5, 6, 8}:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, col, item)


class ImportConfirmDialog(QDialog):
    def __init__(self, lines: list[InvoiceLine], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Подтверждение импорта")
        self.resize(1160, 560)
        self.setStyleSheet(APP_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel(
            "Есть строки с неоднозначным/похожим сопоставлением или созданием новых товаров. Проверьте перед записью:",
            self,
        )
        title.setWordWrap(True)
        title.setObjectName("subtitleLabel")
        root.addWidget(title)

        ambiguous = sum(1 for x in lines if x.match_status == "ambiguous")
        hints = sum(1 for x in lines if x.match_status == "hint")
        not_found = sum(1 for x in lines if x.match_status == "not_found")
        to_create = sum(1 for x in lines if x.action == "create")
        info = QLabel(
            f"Строк для внимания: {len(lines)} | Неоднозначные: {ambiguous} | Похожие (1 вариант): {hints} | Не найдено: {not_found} | К созданию: {to_create}",
            self,
        )
        info.setObjectName("subtitleLabel")
        root.addWidget(info)

        self.table = QTableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["№", "Артикул", "Название", "Статус", "Действие", "Код в БД", "Похожие", "Предупреждение"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: _show_table_copy_menu(self.table, pos, self)
        )
        root.addWidget(self.table, 1)

        self.table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            values = [
                str(line.line_no),
                line.article,
                line.name,
                _status_text_ru(line.match_status),
                line.action,
                str(line.matched_good_id or ""),
                line.similar_articles,
                line.warning,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, col, item)

            status_item = self.table.item(row, 3)
            if status_item is not None:
                color = _status_color_for_dialog(line.match_status)
                if color is not None:
                    status_item.setBackground(color)
                    status_item.setForeground(QColor(20, 20, 20))

        self.table.resizeColumnsToContents()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setText("Импортировать")
            ok_btn.setObjectName("successBtn")
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


class ImportResultDialog(QDialog):
    def __init__(
        self,
        result: ImportResult,
        *,
        dry_run: bool,
        debug_mode: bool,
        supplier_name: str,
        payment_name: str,
        invoice_lines: list[InvoiceLine] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Проверка завершена" if dry_run else "Импорт выполнен")
        self.resize(860, 620)
        self.setStyleSheet(APP_STYLESHEET)

        processed = result.imported_lines + result.skipped_lines
        doc_value = f"№ {result.waybill_id}" if result.waybill_id is not None else "—"

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QFrame(self)
        header.setObjectName("resultHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(10)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(2)
        title = QLabel("Проверка завершена" if dry_run else "Импорт выполнен успешно", self)
        title.setObjectName("titleLabel")
        title_wrap.addWidget(title)

        subtitle = QLabel(
            "Изменения в базу не записывались (режим проверки)." if dry_run else "Документ записан в базу Tirika.",
            self,
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        title_wrap.addWidget(subtitle)
        header_layout.addLayout(title_wrap, 1)

        state_label = QLabel("DRY-RUN" if dry_run else "УСПЕШНО", self)
        state_label.setObjectName("resultStateDry" if dry_run else "resultStateOk")
        header_layout.addWidget(state_label, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(header)

        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(8)
        tags_layout.addWidget(self._result_tag("ИМПОРТ", result.imported_lines, "import"))
        tags_layout.addWidget(self._result_tag("SKIP", result.skipped_lines, "skip"))
        tags_layout.addWidget(self._result_tag("СОЗДАНО", result.created_goods, "create"))
        tags_layout.addStretch(1)
        root.addLayout(tags_layout)

        tags_hint = QLabel(
            "Формат списка ниже: [СТАТУС] АРТИКУЛ — ПРИЧИНА",
            self,
        )
        tags_hint.setObjectName("subtitleLabel")
        tags_hint.setWordWrap(True)
        root.addWidget(tags_hint)

        metrics_group = QGroupBox("Итоги", self)
        metrics_layout = QGridLayout(metrics_group)
        metrics_layout.setHorizontalSpacing(10)
        metrics_layout.setVerticalSpacing(10)

        metrics = [
            ("Обработано строк", str(processed)),
            ("Импортировано (в БД)", str(result.imported_lines)),
            ("SKIP (без записи)", str(result.skipped_lines)),
            ("Создано карточек", str(result.created_goods)),
            ("Сумма накладной", _fmt_number(result.total_cost, 2)),
            ("Документ в базе", doc_value),
            ("Поставщик", supplier_name.strip() or "—"),
            ("Оплата", payment_name.strip() or "—"),
        ]
        for idx, (label, value) in enumerate(metrics):
            row = idx // 4
            col = idx % 4
            metrics_layout.addWidget(self._metric_card(label, value), row, col)
        root.addWidget(metrics_group)

        warnings_group = QGroupBox("Предупреждения", self)
        warnings_layout = QVBoxLayout(warnings_group)
        warnings_layout.setContentsMargins(10, 10, 10, 10)
        warnings_layout.setSpacing(8)
        line_by_no = {
            int(line.line_no): line
            for line in (invoice_lines or [])
            if int(line.line_no) > 0
        }
        if result.warnings:
            warnings_hint = QLabel(f"Найдено предупреждений: {len(result.warnings)}", self)
            warnings_hint.setObjectName("subtitleLabel")
            warnings_layout.addWidget(warnings_hint)
            legend = QLabel(
                "<span style='color:#dc2626;'>●</span> критично &nbsp;&nbsp; "
                "<span style='color:#b29829;'>●</span> проверить вручную",
                self,
            )
            legend.setObjectName("subtitleLabel")
            warnings_layout.addWidget(legend)
            warnings_list = QListWidget(self)
            warnings_list.setObjectName("warningsList")
            for warning in result.warnings:
                display_text, severity = self._format_warning_display(warning, line_by_no)
                item = QListWidgetItem(display_text)
                if severity == "error":
                    item.setIcon(self._warning_icon(QColor(220, 38, 38)))
                    item.setForeground(QColor(153, 27, 27))
                else:
                    item.setIcon(self._warning_icon(QColor(178, 152, 41)))
                    item.setForeground(QColor(122, 104, 27))
                warnings_list.addItem(item)
            warnings_layout.addWidget(warnings_list, 1)
        else:
            no_warn = QLabel("Предупреждений нет.", self)
            no_warn.setObjectName("subtitleLabel")
            warnings_layout.addWidget(no_warn)
        root.addWidget(warnings_group, 1)

        if result.backup_path:
            backup_label = QLabel(f"Backup базы: {result.backup_path}", self)
            backup_label.setObjectName("subtitleLabel")
            backup_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            backup_label.setWordWrap(True)
            root.addWidget(backup_label)

        if debug_mode:
            debug_group = QGroupBox("Технические детали (LOG)", self)
            debug_layout = QVBoxLayout(debug_group)
            debug_layout.setContentsMargins(10, 10, 10, 10)
            details = QPlainTextEdit(self)
            details.setReadOnly(True)
            details.setMaximumBlockCount(500)
            details_lines = [
                f"dry-run: {result.dry_run}",
                f"imported_lines: {result.imported_lines}",
                f"skipped_lines: {result.skipped_lines}",
                f"created_goods: {result.created_goods}",
                f"total_cost: {result.total_cost:.2f}",
            ]
            if result.waybill_id is not None:
                details_lines.append(f"waybill_id: {result.waybill_id}")
            if result.backup_path:
                details_lines.append(f"backup: {result.backup_path}")
            if result.warnings:
                details_lines.append("warnings:")
                details_lines.extend([f"- {w}" for w in result.warnings])
            details.setPlainText("\n".join(details_lines))
            debug_layout.addWidget(details)
            root.addWidget(debug_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, parent=self)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setText("Закрыть")
            ok_btn.setObjectName("primaryBtn")
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _metric_card(self, title: str, value: str) -> QWidget:
        card = QFrame(self)
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title_label = QLabel(title, self)
        title_label.setObjectName("metricTitle")
        layout.addWidget(title_label)

        value_label = QLabel(value, self)
        value_label.setObjectName("metricValue")
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(value_label)
        return card

    def _format_warning_display(
        self,
        warning: str,
        line_by_no: dict[int, InvoiceLine],
    ) -> tuple[str, str]:
        raw = (warning or "").strip()
        line_no = self._extract_warning_line_no(raw)
        reason = re.sub(r"^\s*строка\s+\d+\s*:\s*", "", raw, flags=re.IGNORECASE).strip() or raw

        line = line_by_no.get(line_no or -1)
        article = line.article.strip() if line else ""
        status = self._warning_status_label(reason, line)
        severity = self._warning_severity(reason)
        if not article:
            article = "без артикула"
        return f"[{status}] {article} — {reason}", severity

    def _warning_status_label(self, reason: str, line: InvoiceLine | None) -> str:
        low = reason.lower()
        if line is not None:
            if line.action == "skip":
                return "SKIP"
            if line.action == "create":
                return "СОЗДАНО"
            if line.action == "import":
                return "ИМПОРТ"
        if "пропущ" in low:
            return "SKIP"
        if "созда" in low:
            return "СОЗДАНО"
        if "не найден" in low or "неоднознач" in low or "несколько" in low:
            return "SKIP"
        return "ВНИМАНИЕ"

    def _extract_warning_line_no(self, warning: str) -> int | None:
        m = re.search(r"строка\s+(\d+)", warning, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _result_tag(self, label: str, value: int, kind: str) -> QLabel:
        tag = QLabel(f"{label}: {value}", self)
        if kind == "import":
            tag.setObjectName("resultTagImport")
        elif kind == "create":
            tag.setObjectName("resultTagCreate")
        else:
            tag.setObjectName("resultTagSkip")
        return tag

    def _warning_severity(self, warning: str) -> str:
        text = (warning or "").lower()
        if "похож" in text and "не найден" in text:
            return "warning"
        error_markers = (
            "ошибка",
            "error",
            "не найден",
            "неоднознач",
            "несколько",
            "некоррект",
            "ambiguous",
        )
        for marker in error_markers:
            if marker in text:
                return "error"
        return "warning"

    def _warning_icon(self, color: QColor) -> QIcon:
        pixmap = QPixmap(14, 14)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(color.darker(120), 1))
        painter.setBrush(color)
        painter.drawEllipse(1, 1, 12, 12)
        painter.end()
        return QIcon(pixmap)


class SettingsDialog(QDialog):
    check_updates_requested = Signal(str)

    def __init__(
        self,
        current: AppSettings,
        users: list[tuple[int, str]],
        shops: list[tuple[int, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._supplier_id = current.supplier_id
        self._payment_type_default = current.payment_type
        self._table_header_state = current.table_header_state
        self._ignored_update_version = current.ignored_update_version
        self.setWindowTitle("Настройки Dazzle")
        self.resize(920, 640)
        self.setStyleSheet(APP_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        hint = QLabel(
            "Постоянные параметры хранятся здесь. На главном экране остаются только импорт и работа с таблицей.",
            self,
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        tabs_hint = QLabel("Разделы настроек: 'Основные' и 'Импорт'. Нажмите на вкладку сверху.", self)
        tabs_hint.setObjectName("subtitleLabel")
        tabs_hint.setWordWrap(True)
        root.addWidget(tabs_hint)

        tabs = QTabWidget(self)
        root.addWidget(tabs, 1)

        general_tab = QWidget(self)
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(6, 6, 6, 6)
        general_layout.setSpacing(10)
        tabs.addTab(general_tab, "Основные")

        import_tab = QWidget(self)
        import_layout_root = QVBoxLayout(import_tab)
        import_layout_root.setContentsMargins(6, 6, 6, 6)
        import_layout_root.setSpacing(10)
        tabs.addTab(import_tab, "Импорт")

        paths_group = QGroupBox("Пути", self)
        paths_layout = QGridLayout(paths_group)
        paths_layout.setHorizontalSpacing(8)
        paths_layout.setVerticalSpacing(8)

        paths_layout.addWidget(QLabel("Файл базы shop.db:"), 0, 0)
        self.db_path_edit = QLineEdit(self)
        self.db_path_edit.setText(current.db_path)
        self.db_path_edit.setToolTip("Полный путь к базе данных Tirika (обычно shop.db).")
        paths_layout.addWidget(self.db_path_edit, 0, 1)
        self.db_pick_btn = QPushButton("Выбрать", self)
        self.db_pick_btn.setToolTip("Открыть выбор файла базы.")
        paths_layout.addWidget(self.db_pick_btn, 0, 2)

        paths_layout.addWidget(QLabel("Папка накладных:"), 1, 0)
        self.invoices_dir_edit = QLineEdit(self)
        self.invoices_dir_edit.setText(current.invoices_dir)
        self.invoices_dir_edit.setToolTip("Папка, из которой Dazzle берет Excel-накладные.")
        paths_layout.addWidget(self.invoices_dir_edit, 1, 1)
        self.invoices_pick_btn = QPushButton("Выбрать", self)
        self.invoices_pick_btn.setToolTip("Открыть выбор папки накладных.")
        paths_layout.addWidget(self.invoices_pick_btn, 1, 2)
        general_layout.addWidget(paths_group)

        updates_group = QGroupBox("Обновления", self)
        updates_layout = QGridLayout(updates_group)
        updates_layout.setHorizontalSpacing(8)
        updates_layout.setVerticalSpacing(8)

        self.auto_update_check_cb = QCheckBox("Проверять обновления при запуске", self)
        self.auto_update_check_cb.setChecked(current.auto_check_updates)
        self.auto_update_check_cb.setToolTip(
            "Если включено, Dazzle при старте проверяет наличие новой версии по ссылке ниже."
        )
        updates_layout.addWidget(self.auto_update_check_cb, 0, 0, 1, 3)

        updates_layout.addWidget(QLabel("URL latest.json:"), 1, 0)
        self.update_manifest_url_edit = QLineEdit(self)
        self.update_manifest_url_edit.setText(current.update_manifest_url)
        self.update_manifest_url_edit.setPlaceholderText(
            "https://raw.githubusercontent.com/<owner>/<repo>/main/updates/latest.json"
        )
        self.update_manifest_url_edit.setToolTip(
            "Ссылка на JSON с описанием последнего релиза: version, url, sha256."
        )
        updates_layout.addWidget(self.update_manifest_url_edit, 1, 1, 1, 2)

        updates_hint = QLabel(
            "Источник обновлений можно хранить в GitHub (raw latest.json + asset установщика в Releases).",
            self,
        )
        updates_hint.setObjectName("subtitleLabel")
        updates_hint.setWordWrap(True)
        updates_layout.addWidget(updates_hint, 2, 0, 1, 3)

        self.check_updates_now_btn = QPushButton("Проверить обновления сейчас", self)
        self.check_updates_now_btn.setObjectName("primaryBtn")
        self.check_updates_now_btn.setToolTip(
            "Проверяет наличие новой версии по URL latest.json из этого раздела."
        )
        updates_layout.addWidget(self.check_updates_now_btn, 3, 0, 1, 3)
        general_layout.addWidget(updates_group)

        price_group = QGroupBox("Ценообразование", self)
        price_layout = QGridLayout(price_group)
        price_layout.setHorizontalSpacing(8)
        price_layout.setVerticalSpacing(8)

        price_layout.addWidget(QLabel("Наценка, %:"), 0, 0)
        self.markup_spin = QDoubleSpinBox(self)
        self.markup_spin.setRange(0.0, 500.0)
        self.markup_spin.setDecimals(1)
        self.markup_spin.setValue(current.markup_percent)
        self.markup_spin.setToolTip("Наценка к закупочной цене при расчете продажи.")
        price_layout.addWidget(self.markup_spin, 0, 1)

        price_layout.addWidget(QLabel("Округление вверх до шага:"), 1, 0)
        self.round_step_spin = QDoubleSpinBox(self)
        self.round_step_spin.setRange(1.0, 10000.0)
        self.round_step_spin.setDecimals(0)
        self.round_step_spin.setValue(current.round_step)
        self.round_step_spin.setToolTip("Шаг округления в большую сторону (например, 50).")
        price_layout.addWidget(self.round_step_spin, 1, 1)

        price_layout.addWidget(QLabel("Порог красного, %:"), 2, 0)
        self.price_alert_spin = QDoubleSpinBox(self)
        self.price_alert_spin.setRange(0.0, 1000.0)
        self.price_alert_spin.setDecimals(1)
        self.price_alert_spin.setValue(current.price_alert_threshold_percent)
        self.price_alert_spin.setToolTip(
            "Если новая продажная цена отличается от цены в базе на этот % и больше, строка краснеет."
        )
        price_layout.addWidget(self.price_alert_spin, 2, 1)
        general_layout.addWidget(price_group)

        import_group = QGroupBox("Импорт по умолчанию", self)
        import_layout = QGridLayout(import_group)
        import_layout.setHorizontalSpacing(8)
        import_layout.setVerticalSpacing(8)
        general_layout.addWidget(import_group)

        import_layout.addWidget(QLabel("Пользователь:"), 0, 0)
        self.user_combo = QComboBox(self)
        for user_id, name in users:
            self.user_combo.addItem(f"{name} [{user_id}]", userData=user_id)
        self.user_combo.setToolTip("Пользователь, от имени которого создается закупка.")
        import_layout.addWidget(self.user_combo, 0, 1)

        import_layout.addWidget(QLabel("Склад:"), 0, 2)
        self.shop_combo = QComboBox(self)
        for shop_id, name in shops:
            self.shop_combo.addItem(f"{name} [{shop_id}]", userData=shop_id)
        self.shop_combo.setToolTip("Склад, на который будет приход товара.")
        import_layout.addWidget(self.shop_combo, 0, 3)

        import_layout.addWidget(QLabel("Оплата:"), 1, 0)
        self.payment_combo = QComboBox(self)
        _fill_payment_combo(self.payment_combo)
        self.payment_combo.setToolTip("Тип оплаты, который попадет в документ закупки.")
        import_layout.addWidget(self.payment_combo, 1, 1)

        options_group = QGroupBox("Поведение импорта", self)
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(10, 10, 10, 10)
        options_layout.setSpacing(10)
        import_layout_root.addWidget(options_group)

        existing_group = QGroupBox("Если товар уже найден в базе", self)
        existing_layout = QGridLayout(existing_group)
        existing_layout.setHorizontalSpacing(10)
        existing_layout.setVerticalSpacing(8)

        existing_hint = QLabel(
            "Эти параметры изменяют уже существующую карточку товара в БД.",
            self,
        )
        existing_hint.setObjectName("subtitleLabel")
        existing_hint.setWordWrap(True)
        existing_layout.addWidget(existing_hint, 0, 0, 1, 2)

        self.update_existing_buy_cb = QCheckBox(
            "Обновлять закупочную цену у найденного товара",
            self,
        )
        self.update_existing_buy_cb.setChecked(current.update_existing_buy_price)
        self.update_existing_buy_cb.setToolTip("Меняет только закупочную цену товара, который уже найден в базе.")
        existing_layout.addWidget(self.update_existing_buy_cb, 1, 0)

        self.update_existing_supplier_cb = QCheckBox(
            "Обновлять поставщика у найденного товара (карточка БД)",
            self,
        )
        self.update_existing_supplier_cb.setChecked(current.update_existing_supplier)
        self.update_existing_supplier_cb.setToolTip("Меняет поставщика в карточке уже найденного товара.")
        existing_layout.addWidget(self.update_existing_supplier_cb, 1, 1)

        self.update_existing_sell_cb = QCheckBox(
            "Обновлять продажную цену у найденного товара",
            self,
        )
        self.update_existing_sell_cb.setChecked(current.update_existing_sell_price)
        self.update_existing_sell_cb.setToolTip("Меняет продажную цену уже найденного товара.")
        existing_layout.addWidget(self.update_existing_sell_cb, 2, 0)

        self.update_existing_name_cb = QCheckBox(
            "Обновлять название у найденного товара",
            self,
        )
        self.update_existing_name_cb.setChecked(current.update_existing_name)
        self.update_existing_name_cb.setToolTip("Меняет название уже найденного товара.")
        existing_layout.addWidget(self.update_existing_name_cb, 2, 1)

        self.update_existing_manufacturer_cb = QCheckBox(
            "Обновлять производителя у найденного товара",
            self,
        )
        self.update_existing_manufacturer_cb.setChecked(current.update_existing_manufacturer)
        self.update_existing_manufacturer_cb.setToolTip("Меняет производителя уже найденного товара.")
        existing_layout.addWidget(self.update_existing_manufacturer_cb, 3, 0)

        options_layout.addWidget(existing_group)

        missing_group = QGroupBox("Если товар не найден (новая карточка)", self)
        missing_layout = QVBoxLayout(missing_group)
        missing_layout.setContentsMargins(10, 10, 10, 10)
        missing_layout.setSpacing(8)

        self.create_missing_cb = QCheckBox("Создавать новую карточку товара", self)
        self.create_missing_cb.setChecked(current.create_missing_goods)
        self.create_missing_cb.setToolTip("Если товар из накладной не найден в базе, создается новая карточка.")
        missing_layout.addWidget(self.create_missing_cb)

        self.prefix_order_name_cb = QCheckBox(
            "Добавлять префикс 'ЗАКАЗ--' к названию новых товаров",
            self,
        )
        self.prefix_order_name_cb.setChecked(current.prefix_new_goods_with_order)
        self.prefix_order_name_cb.setToolTip(
            "Для новых карточек, созданных из накладной, добавляет префикс 'ЗАКАЗ--' к названию."
        )
        missing_layout.addWidget(self.prefix_order_name_cb)

        options_layout.addWidget(missing_group)

        doc_group = QGroupBox("Документ и безопасность", self)
        doc_layout = QGridLayout(doc_group)
        doc_layout.setHorizontalSpacing(10)
        doc_layout.setVerticalSpacing(8)

        self.auto_pay_cb = QCheckBox("Считать закупку оплаченной", self)
        self.auto_pay_cb.setChecked(current.auto_pay)
        self.auto_pay_cb.setToolTip("Автоматически создает запись оплаты по накладной.")
        doc_layout.addWidget(self.auto_pay_cb, 0, 0)

        self.backup_cb = QCheckBox("Backup перед импортом", self)
        self.backup_cb.setChecked(current.backup_before_import)
        self.backup_cb.setToolTip("Перед импортом делает резервную копию базы.")
        doc_layout.addWidget(self.backup_cb, 0, 1)

        options_layout.addWidget(doc_group)

        system_group = QGroupBox("Система", self)
        system_layout = QHBoxLayout(system_group)
        system_layout.setContentsMargins(10, 10, 10, 10)
        system_layout.setSpacing(10)
        system_layout.addWidget(QLabel("Автозапуск приложения:", self))
        self.startup_btn = QPushButton("...", self)
        self.startup_btn.setMinimumWidth(220)
        self.startup_btn.setToolTip("Включает/выключает запуск Dazzle вместе с Windows.")
        system_layout.addWidget(self.startup_btn)
        system_layout.addStretch(1)
        import_layout_root.addWidget(system_group)
        general_layout.addStretch(1)
        import_layout_root.addStretch(1)

        self._set_combo_by_data(self.user_combo, current.user_id)
        self._set_combo_by_data(self.shop_combo, current.shop_id)
        self._set_combo_by_data(self.payment_combo, current.payment_type)
        self._refresh_startup_button()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            parent=self,
        )
        root.addWidget(buttons)

        self.db_pick_btn.clicked.connect(self._pick_db_file)
        self.invoices_pick_btn.clicked.connect(self._pick_invoices_dir)
        self.check_updates_now_btn.clicked.connect(self._request_check_updates)
        self.startup_btn.clicked.connect(self._toggle_startup)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def _refresh_startup_button(self) -> None:
        if not is_supported():
            self.startup_btn.setText("Автозапуск недоступен")
            self.startup_btn.setEnabled(False)
            return
        self.startup_btn.setEnabled(True)
        if is_enabled():
            self.startup_btn.setText("Убрать из автозапуска")
            self.startup_btn.setObjectName("successBtn")
        else:
            self.startup_btn.setText("Добавить в автозапуск")
            self.startup_btn.setObjectName("primaryBtn")
        self.startup_btn.style().unpolish(self.startup_btn)
        self.startup_btn.style().polish(self.startup_btn)

    def _toggle_startup(self) -> None:
        if not is_supported():
            QMessageBox.warning(self, "Автозапуск", "Автозапуск недоступен: нужен Windows и pywin32.")
            return
        try:
            if is_enabled():
                disable_startup()
                QMessageBox.information(self, "Автозапуск", "Приложение удалено из автозапуска.")
            else:
                link_path = enable_startup()
                QMessageBox.information(self, "Автозапуск", f"Автозапуск включен: {link_path}")
            self._refresh_startup_button()
        except StartupError as exc:
            QMessageBox.critical(self, "Автозапуск", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Автозапуск", f"Не удалось изменить автозапуск: {exc}")

    def values(self) -> AppSettings:
        return AppSettings(
            db_path=self.db_path_edit.text().strip(),
            invoices_dir=self.invoices_dir_edit.text().strip(),
            markup_percent=float(self.markup_spin.value()),
            round_step=float(self.round_step_spin.value()),
            price_alert_threshold_percent=float(self.price_alert_spin.value()),
            supplier_id=self._supplier_id,
            user_id=self._selected_data(self.user_combo, 1),
            shop_id=self._selected_data(self.shop_combo, 0),
            payment_type=self._selected_data(self.payment_combo, self._payment_type_default),
            create_missing_goods=self.create_missing_cb.isChecked(),
            update_existing_goods_fields=False,
            update_goods_buy_price=self.update_existing_buy_cb.isChecked(),
            update_existing_sell_price=self.update_existing_sell_cb.isChecked(),
            update_existing_buy_price=self.update_existing_buy_cb.isChecked(),
            update_existing_supplier=self.update_existing_supplier_cb.isChecked(),
            update_existing_name=self.update_existing_name_cb.isChecked(),
            update_existing_manufacturer=self.update_existing_manufacturer_cb.isChecked(),
            auto_pay=self.auto_pay_cb.isChecked(),
            backup_before_import=self.backup_cb.isChecked(),
            prefix_new_goods_with_order=self.prefix_order_name_cb.isChecked(),
            table_header_state=self._table_header_state,
            update_manifest_url=self.update_manifest_url_edit.text().strip(),
            auto_check_updates=self.auto_update_check_cb.isChecked(),
            ignored_update_version=self._ignored_update_version,
        )

    def _pick_db_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл базы Tirika",
            str(Path.cwd()),
            "SQLite DB (*.db);;Все файлы (*.*)",
        )
        if path:
            self.db_path_edit.setText(path)

    def _pick_invoices_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку с накладными",
            self.invoices_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.invoices_dir_edit.setText(path)

    def _request_check_updates(self) -> None:
        self.check_updates_requested.emit(self.update_manifest_url_edit.text().strip())

    @staticmethod
    def _selected_data(combo: QComboBox, default: int) -> int:
        data = combo.currentData()
        if data is None:
            return default
        return int(data)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, target: int) -> None:
        for idx in range(combo.count()):
            data = combo.itemData(idx)
            if data is not None and int(data) == int(target):
                combo.setCurrentIndex(idx)
                return


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1480, 860)

        self.db: TirikaDB | None = None
        self.matcher: GoodsMatcher | None = None
        self.current_invoice: ParsedInvoice | None = None
        self.app_settings = load_app_settings()
        self._table_locked = False
        self.debug_log_enabled = False
        self._restoring_header_state = False
        self._column_layout_initialized = False
        self._history: list[list[InvoiceLine]] = []
        self._history_index = -1
        self._history_restoring = False
        self._column_state_save_timer = QTimer(self)
        self._column_state_save_timer.setSingleShot(True)
        self._column_state_save_timer.setInterval(350)
        self._column_state_save_timer.timeout.connect(
            lambda: self._save_table_header_state(silent=True)
        )

        self._build_ui()
        self._apply_styles()
        self._load_initial_config()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        header_card = QFrame(self)
        header_card.setObjectName("topCard")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(12)

        self.debug_toggle_btn = QToolButton(self)
        self.debug_toggle_btn.setObjectName("debugToggleBtn")
        self.debug_toggle_btn.setToolTip(
            "Включить/выключить LOG: показывает нижний debug-лог и колонки, связанные с БД."
        )
        self.debug_toggle_btn.setCheckable(True)
        self.debug_toggle_btn.setChecked(False)
        self.debug_toggle_btn.setText("LOG")
        self.debug_toggle_btn.setFixedSize(42, 22)
        header_layout.addWidget(self.debug_toggle_btn, 0, Qt.AlignTop)

        logo_path = Path(__file__).resolve().parent.parent / "store-business-and-finance-svgrepo-com.svg"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
            logo = QSvgWidget(str(logo_path), self)
            logo.setFixedSize(42, 42)
            header_layout.addWidget(logo, 0, Qt.AlignVCenter)

        header_text = QVBoxLayout()
        title = QLabel("Dazzle", self)
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Импорт накладных в Tirika: проверка, сопоставление и контроль цен",
            self,
        )
        subtitle.setObjectName("subtitleLabel")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text, 1)

        self.db_state_label = QLabel("База: не открыта", self)
        self.db_state_label.setObjectName("subtitleLabel")
        self.db_state_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.db_state_label.setVisible(False)

        self.settings_btn = QPushButton("Настройки", self)
        self.settings_btn.setObjectName("primaryBtn")
        self.settings_btn.setMinimumWidth(130)
        self.settings_btn.setToolTip(
            "Открывает постоянные настройки: база, папка накладных, параметры импорта и автозапуск."
        )
        header_layout.addWidget(self.settings_btn)

        self.db_open_btn = QPushButton("Переподключить БД", self)
        self.db_open_btn.setObjectName("primaryBtn")
        self.db_open_btn.setMinimumWidth(170)
        header_layout.addWidget(
            self._with_help(
                self.db_open_btn,
                "Принудительно переподключает базу shop.db из текущих настроек.",
            )
        )
        root.addWidget(header_card)

        top_card = QFrame(self)
        top_card.setObjectName("topCard")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(10)

        file_group = QGroupBox("Документ", self)
        file_layout = QGridLayout(file_group)
        file_layout.setHorizontalSpacing(10)
        file_layout.setVerticalSpacing(8)

        file_layout.addWidget(QLabel("Накладная:"), 0, 0)
        self.invoice_file_combo = QComboBox(self)
        self.invoice_file_combo.setMinimumWidth(520)
        self.invoice_file_combo.setToolTip("Выберите Excel-файл накладной для загрузки.")
        file_layout.addWidget(self.invoice_file_combo, 0, 1)

        self.invoice_refresh_btn = QPushButton("Обновить список", self)
        self.invoice_refresh_btn.setToolTip("Перечитывает папку накладных и обновляет список Excel-файлов.")
        file_layout.addWidget(self.invoice_refresh_btn, 0, 2)

        self.load_invoice_btn = QPushButton("Загрузить", self)
        self.load_invoice_btn.setObjectName("primaryBtn")
        self.load_invoice_btn.setToolTip(
            "Загружает выбранную накладную в таблицу для проверки, сопоставления и импорта."
        )
        file_layout.addWidget(self.load_invoice_btn, 0, 3)

        file_layout.addWidget(QLabel("Оплата в документе:"), 1, 0)
        self.payment_combo = QComboBox(self)
        _fill_payment_combo(self.payment_combo)
        self.payment_combo.setToolTip("Тип оплаты для создаваемой закупки.")
        file_layout.addWidget(self.payment_combo, 1, 1)
        file_layout.addWidget(QLabel("Поставщик:"), 2, 0)
        self.supplier_combo = QComboBox(self)
        self.supplier_combo.setToolTip(
            "Поставщик документа для импорта. Определяется автоматически по накладной, "
            "при необходимости можно выбрать вручную."
        )
        file_layout.addWidget(self.supplier_combo, 2, 1)
        self.supplier_detect_label = QLabel("Автоопределение поставщика: ожидается загрузка накладной", self)
        self.supplier_detect_label.setObjectName("subtitleLabel")
        self.supplier_detect_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        file_layout.addWidget(self.supplier_detect_label, 2, 2, 1, 2)
        file_layout.setColumnStretch(1, 1)

        # Постоянные параметры импорта скрыты с главного экрана и настраиваются в диалоге "Настройки".
        self.user_combo = QComboBox()
        self.shop_combo = QComboBox()

        self.create_missing_cb = QCheckBox()
        self.update_goods_card_cb = QCheckBox()
        self.update_buy_price_cb = QCheckBox()
        self.auto_pay_cb = QCheckBox()
        self.backup_cb = QCheckBox()
        self._apply_settings_to_runtime_controls()

        actions_group = QGroupBox("Действия", self)
        actions = QHBoxLayout(actions_group)
        actions.setContentsMargins(10, 10, 10, 10)
        actions.setSpacing(10)
        self.match_btn = QPushButton("Найти товары автоматически", self)
        self.pick_btn = QPushButton("Назначить товар вручную", self)
        self.apply_suggested_price_btn = QPushButton("Применить цену +50%", self)
        self.import_btn = QPushButton("Импорт в базу", self)
        self.import_btn.setObjectName("successBtn")
        self.match_btn.setToolTip("Автоматически ищет товары в базе по артикулу и названию.")
        self.pick_btn.setToolTip("Ручной выбор товара для текущей строки.")
        self.apply_suggested_price_btn.setToolTip(
            "Ставит рассчитанную цену (+наценка и округление) для выделенных или красных строк."
        )
        self.import_btn.setToolTip("Выполняет реальную запись накладной в базу Tirika.")
        actions.addWidget(self.match_btn)
        actions.addWidget(self.pick_btn)
        actions.addSpacing(8)
        actions.addWidget(self.apply_suggested_price_btn)
        self.undo_btn = QPushButton("Назад", self)
        self.redo_btn = QPushButton("Вперед", self)
        self.undo_btn.setToolTip("Отменить последнее изменение в таблице.")
        self.redo_btn.setToolTip("Вернуть отмененное изменение.")
        self.undo_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)
        actions.addWidget(self.undo_btn)
        actions.addWidget(self.redo_btn)
        self.invoice_totals_label = QLabel("Товаров: 0 | Сумма накладной: 0", self)
        self.invoice_totals_label.setObjectName("totalsPill")
        self.invoice_totals_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.invoice_totals_label.setMinimumWidth(360)
        actions.addWidget(self.invoice_totals_label)
        actions.addStretch(1)
        actions.addWidget(self.import_btn)

        top_layout.addWidget(file_group)
        top_layout.addWidget(actions_group)
        root.addWidget(top_card)

        self.table = QTableWidget(self)
        self.table.setColumnCount(19)
        self.table.setHorizontalHeaderLabels(
            [
                "№",
                "Артикул",
                "Название из накладной",
                "Примечание",
                "Кол-во",
                "Закуп",
                "Сумма",
                "Продажа (новая)",
                "Продажа в БД",
                "Δ, %",
                "Наценка, %",
                "Статус",
                "Действие",
                "Good ID",
                "Код в БД",
                "Товар в БД",
                "Похожие артикулы",
                "Метод",
                "Предупреждение",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: _show_table_copy_menu(self.table, pos, self)
        )
        self.table.setWordWrap(False)

        self.log_card = QFrame(self)
        self.log_card.setObjectName("logCard")
        log_layout = QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(6)
        log_title = QLabel("Debug-лог", self)
        log_title.setObjectName("subtitleLabel")
        log_layout.addWidget(log_title)
        self.log_box = QPlainTextEdit(self)
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(400)
        self.log_box.setPlaceholderText("Здесь будет журнал операций и проверок...")
        log_layout.addWidget(self.log_box)

        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.log_card)
        self.splitter.setStretchFactor(0, 8)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([640, 190])
        root.addWidget(self.splitter, 1)

        footer_card = QFrame(self)
        footer_card.setObjectName("topCard")
        footer_layout = QHBoxLayout(footer_card)
        footer_layout.setContentsMargins(10, 8, 10, 8)
        footer_layout.setSpacing(10)
        self.summary_label = QLabel("Готово к работе.", self)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setObjectName("subtitleLabel")
        footer_layout.addWidget(self.summary_label, 1)
        root.addWidget(footer_card)

        self.settings_btn.clicked.connect(self._open_settings_dialog)
        self.db_open_btn.clicked.connect(self._open_db)
        self.debug_toggle_btn.toggled.connect(self._set_debug_log_enabled)
        self.invoice_refresh_btn.clicked.connect(self._refresh_invoice_files)
        self.load_invoice_btn.clicked.connect(self._load_invoice)
        self.invoice_file_combo.activated.connect(lambda _: self._load_invoice())
        self.match_btn.clicked.connect(self._run_matching)
        self.pick_btn.clicked.connect(self._pick_good_for_selected)
        self.apply_suggested_price_btn.clicked.connect(self._apply_suggested_prices)
        self.undo_btn.clicked.connect(self._undo_history)
        self.redo_btn.clicked.connect(self._redo_history)
        self.import_btn.clicked.connect(lambda: self._run_import(dry_run=False))
        self.table.itemChanged.connect(self._on_table_item_changed)
        self.shop_combo.currentIndexChanged.connect(self._on_shop_changed)
        self.payment_combo.currentIndexChanged.connect(self._on_payment_changed)
        self.supplier_combo.currentIndexChanged.connect(self._on_supplier_changed)
        self.table.horizontalHeader().sectionMoved.connect(self._on_table_header_layout_changed)
        self.table.horizontalHeader().sectionResized.connect(self._on_table_header_layout_changed)
        self._set_debug_log_enabled(False)
        self._restore_table_header_state()
        self._update_history_buttons()

    def _load_initial_config(self) -> None:
        cfg = load_config()
        if not self.app_settings.db_path and cfg.db_dir:
            db_path = cfg.db_dir
            if db_path.is_dir():
                db_path = db_path / "shop.db"
            self.app_settings.db_path = str(db_path)
            self._save_settings(silent=True)

        self._apply_settings_to_runtime_controls()
        self._refresh_invoice_files()
        if self.app_settings.db_path.strip():
            self._open_db()
        else:
            self._log("Укажите путь к базе в настройках и загрузите накладную.")
        if self.app_settings.auto_check_updates:
            QTimer.singleShot(1200, lambda: self._check_for_updates(interactive=False))

    def _apply_styles(self) -> None:
        self.setStyleSheet(APP_STYLESHEET)

    def _set_debug_log_enabled(self, enabled: bool) -> None:
        self.debug_log_enabled = bool(enabled)
        self.debug_toggle_btn.setText("LOG ON" if self.debug_log_enabled else "LOG")
        self.log_card.setVisible(self.debug_log_enabled)
        self._apply_db_columns_visibility()
        if self.debug_log_enabled:
            self.splitter.setSizes([640, 190])
        else:
            self.splitter.setSizes([1000, 0])
        self._log("Режим LOG включен." if self.debug_log_enabled else "Режим LOG выключен.")

    def _apply_db_columns_visibility(self) -> None:
        show_db_columns = self.debug_log_enabled
        hidden_when_off = set(DB_ONLY_COLUMNS)
        for col in range(self.table.columnCount()):
            should_hide = (col in hidden_when_off) and (not show_db_columns)
            self.table.setColumnHidden(col, should_hide)

    def _on_payment_changed(self) -> None:
        self.app_settings.payment_type = self._selected_data(self.payment_combo, self.app_settings.payment_type)
        self._save_settings(silent=True)

    def _on_supplier_changed(self) -> None:
        if self.supplier_combo.count() == 0:
            return
        supplier_name = _extract_supplier_name(self.supplier_combo.currentText())
        if not supplier_name:
            return
        self.supplier_detect_label.setText(f"Поставщик выбран вручную: {supplier_name}")

    def _help_btn(self, text: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("helpBtn")
        btn.setText("?")
        btn.setToolTip(text)
        btn.clicked.connect(lambda: QMessageBox.information(self, "Подсказка", text))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(18, 18)
        return btn

    def _with_help(self, widget: QWidget, help_text: str) -> QWidget:
        box = QWidget(self)
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(widget)
        layout.addWidget(self._help_btn(help_text))
        return box

    def _save_settings(self, *, silent: bool = False) -> None:
        try:
            path = save_app_settings(self.app_settings)
            if not silent:
                self._log(f"Настройки сохранены: {path}")
        except Exception as exc:
            if not silent:
                self._error("Не удалось сохранить настройки", exc=exc)

    def _update_cache_dir(self) -> Path:
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Dazzle" / "updates"
        return Path.home() / "Dazzle" / "updates"

    def _check_for_updates(
        self,
        *,
        interactive: bool,
        manifest_url_override: str | None = None,
    ) -> None:
        manifest_url = (
            manifest_url_override
            if manifest_url_override is not None
            else self.app_settings.update_manifest_url
        ).strip()
        if not manifest_url:
            if interactive:
                QMessageBox.information(
                    self,
                    "Обновления",
                    "Ссылка на обновления не настроена.\n"
                    "Укажите URL latest.json в Настройках -> Обновления.",
                )
            return

        try:
            update = check_for_update(APP_VERSION, manifest_url)
        except UpdateError as exc:
            if interactive:
                QMessageBox.warning(self, "Обновления", f"Не удалось проверить обновления:\n{exc}")
            else:
                if self.debug_log_enabled:
                    self._log(f"Проверка обновлений: ошибка: {exc}")
            return

        if update is None:
            if interactive:
                QMessageBox.information(
                    self,
                    "Обновления",
                    f"У вас уже актуальная версия: {APP_VERSION}.",
                )
            return

        ignored = self.app_settings.ignored_update_version.strip()
        if not interactive and ignored and ignored == update.version:
            return

        msg = [
            f"Доступна новая версия: {update.version}",
            f"Текущая версия: {APP_VERSION}",
        ]
        if update.notes:
            msg.append("")
            msg.append(update.notes)

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Information)
        dialog.setWindowTitle("Доступно обновление")
        dialog.setText("\n".join(msg))
        btn_install = dialog.addButton("Скачать и установить", QMessageBox.AcceptRole)
        btn_later = dialog.addButton("Напомнить позже", QMessageBox.RejectRole)
        btn_ignore = dialog.addButton("Пропустить эту версию", QMessageBox.DestructiveRole)
        dialog.setDefaultButton(btn_install)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked == btn_ignore:
            self.app_settings.ignored_update_version = update.version
            self._save_settings(silent=True)
            self._log(f"Версия {update.version} помечена как пропущенная.")
            return
        if clicked == btn_later:
            return
        if clicked != btn_install:
            return

        self._download_and_install_update(update)

    def _download_and_install_update(self, update: UpdateInfo) -> None:
        try:
            self._log(f"Скачивание обновления {update.version}...")
            installer_path = download_installer(update, self._update_cache_dir())
            self._log(f"Установщик скачан: {installer_path}")
            run_installer(installer_path)
        except UpdateError as exc:
            QMessageBox.critical(self, "Обновления", str(exc))
            return

        self.app_settings.ignored_update_version = ""
        self._save_settings(silent=True)
        QMessageBox.information(
            self,
            "Обновление",
            "Установщик запущен.\n"
            "Приложение закроется, затем обновление установится автоматически.",
        )
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _reset_history(self) -> None:
        self._history.clear()
        self._history_index = -1
        self._update_history_buttons()

    def _record_history_state(self, *, force: bool = False) -> None:
        if self.current_invoice is None or self._history_restoring:
            self._update_history_buttons()
            return

        snapshot = copy.deepcopy(self.current_invoice.lines)
        if (
            not force
            and self._history_index >= 0
            and self._history_index < len(self._history)
            and self._history[self._history_index] == snapshot
        ):
            self._update_history_buttons()
            return

        if self._history_index + 1 < len(self._history):
            self._history = self._history[: self._history_index + 1]

        self._history.append(snapshot)
        if len(self._history) > MAX_HISTORY_STATES:
            overflow = len(self._history) - MAX_HISTORY_STATES
            self._history = self._history[overflow:]
            self._history_index = max(-1, self._history_index - overflow)

        self._history_index = len(self._history) - 1
        self._update_history_buttons()

    def _restore_history_state(self, index: int) -> None:
        if self.current_invoice is None:
            return
        if index < 0 or index >= len(self._history):
            return
        self._history_restoring = True
        try:
            self._history_index = index
            self.current_invoice.lines = copy.deepcopy(self._history[index])
            self._populate_table(self.current_invoice.lines)
        finally:
            self._history_restoring = False
        self._update_history_buttons()

    def _undo_history(self) -> None:
        if self._history_index <= 0:
            return
        self._restore_history_state(self._history_index - 1)
        self._log("Отмена последнего действия выполнена.")

    def _redo_history(self) -> None:
        if self._history_index < 0 or self._history_index + 1 >= len(self._history):
            return
        self._restore_history_state(self._history_index + 1)
        self._log("Повтор действия выполнен.")

    def _update_history_buttons(self) -> None:
        history_len = len(self._history)
        if history_len <= 1:
            can_undo = False
            can_redo = False
        else:
            can_undo = self._history_index > 0
            can_redo = self._history_index >= 0 and self._history_index + 1 < history_len
        if hasattr(self, "undo_btn"):
            self.undo_btn.setEnabled(can_undo)
        if hasattr(self, "redo_btn"):
            self.redo_btn.setEnabled(can_redo)

    def _on_table_header_layout_changed(self, *_args) -> None:
        if self._restoring_header_state:
            return
        self._column_layout_initialized = True
        self._column_state_save_timer.start()

    def _restore_table_header_state(self) -> None:
        raw_state = (self.app_settings.table_header_state or "").strip()
        if not raw_state:
            return
        restored = False
        self._restoring_header_state = True
        try:
            state = QByteArray.fromBase64(raw_state.encode("ascii"))
            if not state.isEmpty():
                restored = self.table.horizontalHeader().restoreState(state)
        except Exception as exc:
            self._log(f"Предупреждение: не удалось восстановить расположение столбцов: {exc}")
        finally:
            self._restoring_header_state = False
        if restored:
            self._column_layout_initialized = True
            self._apply_db_columns_visibility()

    def _save_table_header_state(self, *, silent: bool = True) -> None:
        try:
            state = self.table.horizontalHeader().saveState()
            encoded = bytes(state.toBase64()).decode("ascii")
        except Exception as exc:
            if not silent:
                self._error("Не удалось сохранить расположение столбцов", exc=exc)
            return
        if encoded == self.app_settings.table_header_state:
            return
        self.app_settings.table_header_state = encoded
        self._save_settings(silent=silent)

    def _apply_settings_to_runtime_controls(self) -> None:
        self.create_missing_cb.setChecked(self.app_settings.create_missing_goods)
        self.update_goods_card_cb.setChecked(self.app_settings.update_existing_sell_price)
        self.update_buy_price_cb.setChecked(self.app_settings.update_existing_buy_price)
        self.auto_pay_cb.setChecked(self.app_settings.auto_pay)
        self.backup_cb.setChecked(self.app_settings.backup_before_import)

        combos = (
            (self.user_combo, self.app_settings.user_id),
            (self.shop_combo, self.app_settings.shop_id),
            (self.payment_combo, self.app_settings.payment_type),
        )
        for combo, target in combos:
            combo.blockSignals(True)
            self._set_combo_by_data(combo, target)
            combo.blockSignals(False)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, target: int) -> None:
        for idx in range(combo.count()):
            data = combo.itemData(idx)
            if data is not None and int(data) == int(target):
                combo.setCurrentIndex(idx)
                return

    @staticmethod
    def _combo_id_name_pairs(combo: QComboBox) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for idx in range(combo.count()):
            data = combo.itemData(idx)
            if data is None:
                continue
            try:
                item_id = int(data)
            except Exception:
                continue
            text = combo.itemText(idx).strip()
            suffix = f"[{item_id}]"
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
            if not text:
                text = f"ID {item_id}"
            out.append((item_id, text))
        return out

    def _refresh_invoice_files(self) -> None:
        self.invoice_file_combo.clear()
        raw = self.app_settings.invoices_dir.strip()
        if not raw:
            self.invoice_file_combo.addItem("Сначала укажите папку в настройках", userData="")
            return

        invoices_dir = Path(raw)
        if not invoices_dir.exists() or not invoices_dir.is_dir():
            self.invoice_file_combo.addItem("Папка не найдена", userData="")
            return

        files = [
            p
            for p in invoices_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".xls", ".xlsx"}
        ]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if not files:
            self.invoice_file_combo.addItem("Excel-файлы не найдены", userData="")
            return

        for file in files:
            self.invoice_file_combo.addItem(file.name, userData=str(file))

    def _open_settings_dialog(self) -> None:
        users = self._combo_id_name_pairs(self.user_combo)
        shops = self._combo_id_name_pairs(self.shop_combo)
        previous_db_path = self.app_settings.db_path.strip()

        dialog = SettingsDialog(self.app_settings, users, shops, self)
        dialog.check_updates_requested.connect(
            lambda manifest_url: self._check_for_updates(
                interactive=True,
                manifest_url_override=manifest_url,
            )
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self.app_settings = dialog.values()
        self._save_settings()
        self._apply_settings_to_runtime_controls()
        self._refresh_invoice_files()
        new_db_path = self.app_settings.db_path.strip()
        if not new_db_path:
            self.db = None
            self.matcher = None
            self.db_state_label.setText("База: не указана")
            return

        if self.db is None or new_db_path != previous_db_path:
            self._open_db()
        else:
            self._reload_catalog()
            if self.current_invoice is not None:
                self._run_matching()

    def _open_db(self) -> None:
        raw = self.app_settings.db_path.strip()
        if not raw:
            self.db_state_label.setText("База: не указана")
            self._error("Укажите путь к shop.db в настройках.")
            return

        db_path = Path(raw)
        if db_path.is_dir():
            db_path = db_path / "shop.db"
            self.app_settings.db_path = str(db_path)
            self._save_settings(silent=True)

        try:
            self.db = TirikaDB(db_path)
            self._load_reference_data()
            self._log(f"База открыта: {db_path}")
            self.db_state_label.setText(f"База: {db_path}")
            if self.current_invoice is not None:
                self._run_matching()
        except Exception as exc:
            self.db = None
            self.matcher = None
            self.db_state_label.setText("База: ошибка открытия")
            self._error("Ошибка открытия базы", exc=exc)

    def _load_reference_data(self) -> None:
        if self.db is None:
            return

        suppliers = self.db.list_suppliers()
        users = self.db.list_users()
        shops = self.db.list_shops()

        self.supplier_combo.clear()
        for supplier_id, name in suppliers:
            self.supplier_combo.addItem(f"{name} [{supplier_id}]", userData=supplier_id)
        if self.supplier_combo.count() > 0:
            supplier_name = _extract_supplier_name(self.supplier_combo.currentText())
            self.supplier_detect_label.setText(
                f"Поставщик выбран вручную: {supplier_name}"
            )
        else:
            self.supplier_detect_label.setText("Поставщики в базе не найдены")

        self.user_combo.clear()
        for user_id, name in users:
            self.user_combo.addItem(f"{name} [{user_id}]", userData=user_id)

        self.shop_combo.blockSignals(True)
        self.shop_combo.clear()
        for shop_id, name in shops:
            self.shop_combo.addItem(f"{name} [{shop_id}]", userData=shop_id)
        self.shop_combo.blockSignals(False)
        self._apply_settings_to_runtime_controls()
        self._reload_catalog()

    def _reload_catalog(self) -> None:
        if self.db is None:
            return
        shop_id = self._selected_data(self.shop_combo, 0)
        catalog = self.db.load_goods_catalog(shop_id=shop_id)
        self.matcher = GoodsMatcher(catalog)
        self._log(f"Каталог загружен: {len(catalog)} товаров.")

    def _on_shop_changed(self) -> None:
        self.app_settings.shop_id = self._selected_data(self.shop_combo, self.app_settings.shop_id)
        self._save_settings(silent=True)
        if self.db is None:
            return
        self._reload_catalog()
        if self.current_invoice:
            self._run_matching()

    def _load_invoice(self) -> None:
        raw = str(self.invoice_file_combo.currentData() or "").strip()
        if not raw:
            self._error("Выберите накладную из списка.")
            return

        try:
            self._reset_history()
            invoice = parse_invoice_file(Path(raw))
            self.current_invoice = invoice
            self._select_supplier_by_hint(invoice.supplier_hint)
            self._populate_table(invoice.lines)
            self._log(
                f"Накладная загружена: {invoice.file_path.name}, "
                f"строк={len(invoice.lines)}, поставщик={invoice.supplier_hint}."
            )
            if self.matcher:
                self._run_matching(record_history=False)
            self._record_history_state(force=True)
        except InvoiceParseError as exc:
            self._error(str(exc), exc=exc)
        except Exception as exc:
            self._error("Ошибка чтения накладной", exc=exc)

    def _run_matching(self, *, record_history: bool = True) -> None:
        if self.current_invoice is None:
            self._error("Сначала загрузите накладную.")
            return
        if self.matcher is None:
            self._error("Сначала откройте базу.")
            return

        try:
            self._sync_lines_from_table(strict=False)
            self.matcher.match_lines(self.current_invoice.lines)
            self._populate_table(self.current_invoice.lines)
            if record_history:
                self._record_history_state()
            self._log("Автосопоставление выполнено.")
        except ImportValidationError as exc:
            self._error(str(exc), exc=exc)

    def _pick_good_for_selected(self) -> None:
        if self.current_invoice is None or self.matcher is None:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.current_invoice.lines):
            self._error("Выберите строку в таблице.")
            return
        line = self.current_invoice.lines[row]
        dialog = GoodsPickerDialog(
            matcher=self.matcher,
            initial_query=line.article or line.name,
            initial_candidates=line.candidates,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.selected_good_id is None:
            return
        try:
            self.matcher.apply_manual_good(line, dialog.selected_good_id)
            line.action = "import"
            line.raw_data["_manual_edited"] = True
            self._populate_table(self.current_invoice.lines)
            self._record_history_state()
            self._log(f"Строка {line.line_no}: вручную выбран good_id={dialog.selected_good_id}.")
        except Exception as exc:
            self._error("Ошибка ручного выбора товара", exc=exc)

    def _apply_suggested_prices(self) -> None:
        if self.current_invoice is None:
            self._error("Сначала загрузите накладную.")
            return

        try:
            self._sync_lines_from_table(strict=False)
        except Exception as exc:
            self._log(f"Предупреждение: не удалось синхронизировать таблицу перед ценой: {exc}")

        selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if selected_rows:
            target_rows = [row for row in selected_rows if 0 <= row < len(self.current_invoice.lines)]
        else:
            target_rows = list(range(len(self.current_invoice.lines)))

        if not target_rows:
            self._log("Нет строк для применения рассчитанной цены.")
            return

        changed = 0
        marked_for_db = 0
        for row in target_rows:
            line = self.current_invoice.lines[row]
            self._refresh_line_price_state(line)
            if line.suggested_sell_price is None:
                continue

            if (
                line.existing_sell_price is not None
                and abs(line.existing_sell_price - line.suggested_sell_price) > 0.0001
            ):
                if not line.raw_data.get("_force_update_sell_price", False):
                    marked_for_db += 1
                line.raw_data["_force_update_sell_price"] = True
                line.raw_data["_price_applied"] = True

            if line.sell_price is None or abs(line.sell_price - line.suggested_sell_price) > 0.0001:
                line.sell_price = line.suggested_sell_price
                line.raw_data["_sell_initialized"] = True
                line.raw_data["_price_applied"] = True
                changed += 1
                self._refresh_line_price_state(line)

        self._populate_table(self.current_invoice.lines)
        if changed > 0 or marked_for_db > 0:
            self._record_history_state()
        self._log(
            f"Применена рассчитанная цена (+{self.app_settings.markup_percent:.1f}%): "
            f"изменено строк={changed}, отмечено к обновлению продажи в БД={marked_for_db}."
        )

    def _run_import(self, dry_run: bool) -> None:
        if self.current_invoice is None:
            self._error("Сначала загрузите накладную.")
            return
        if self.db is None:
            self._error("Сначала откройте базу.")
            return
        if self.supplier_combo.count() == 0:
            self._error("Список поставщиков пуст. Проверьте открытие базы.")
            return

        try:
            self._sync_lines_from_table(strict=True)
            if not dry_run:
                attention_lines = self._collect_import_attention_lines(self.current_invoice.lines)
                if attention_lines:
                    dialog = ImportConfirmDialog(attention_lines, self)
                    if dialog.exec() != QDialog.Accepted:
                        self._log("Импорт отменен пользователем после просмотра проблемных строк.")
                        return

            options = ImportOptions(
                supplier_id=self._selected_data(self.supplier_combo, 1),
                user_id=self._selected_data(self.user_combo, 1),
                shop_id=self._selected_data(self.shop_combo, 0),
                payment_type=self._selected_data(self.payment_combo, self.app_settings.payment_type),
                dry_run=dry_run,
                create_missing_goods=self.create_missing_cb.isChecked(),
                update_existing_goods_fields=False,
                update_goods_buy_price=self.app_settings.update_existing_buy_price,
                update_existing_sell_price=self.app_settings.update_existing_sell_price,
                update_existing_buy_price=self.app_settings.update_existing_buy_price,
                update_existing_supplier=self.app_settings.update_existing_supplier,
                update_existing_name=self.app_settings.update_existing_name,
                update_existing_manufacturer=self.app_settings.update_existing_manufacturer,
                backup_before_import=self.backup_cb.isChecked(),
                auto_pay=self.auto_pay_cb.isChecked(),
                prefix_new_goods_with_order=self.app_settings.prefix_new_goods_with_order,
                waybill_date=datetime.now(),
            )
            supplier_name = _extract_supplier_name(self.supplier_combo.currentText())
            payment_name = self.payment_combo.currentText().strip()
            result = self.db.import_invoice(self.current_invoice, options)
            detailed_lines = [
                f"dry-run: {result.dry_run}",
                f"импортировано строк: {result.imported_lines}",
                f"skip строк: {result.skipped_lines}",
                f"создано товаров: {result.created_goods}",
                f"сумма документа: {result.total_cost:.2f}",
                f"поставщик: {supplier_name}",
                f"оплата: {payment_name}",
            ]
            if result.waybill_id is not None:
                detailed_lines.append(f"waybill_id: {result.waybill_id}")
            if result.backup_path:
                detailed_lines.append(f"backup: {result.backup_path}")

            if result.warnings:
                detailed_lines.append("предупреждения:")
                detailed_lines.extend([f"- {w}" for w in result.warnings[:20]])

            simple_lines = [
                f"Успешно обработано строк: {result.imported_lines + result.skipped_lines}",
                f"Импортировано: {result.imported_lines}",
                f"SKIP: {result.skipped_lines}",
                f"Новых товаров: {result.created_goods}",
                f"Сумма накладной: {_fmt_number(result.total_cost, 2)}",
                f"Поставщик: {supplier_name}",
                f"Оплата: {payment_name}",
            ]
            if result.waybill_id is not None:
                simple_lines.append(f"Документ в базе: № {result.waybill_id}")
            if result.warnings:
                simple_lines.append(f"Есть предупреждения: {len(result.warnings)}")
                simple_lines.extend([f"- {w}" for w in result.warnings[:3]])
                if len(result.warnings) > 3:
                    simple_lines.append("...")

            if self.debug_log_enabled:
                self._log("\n".join(detailed_lines))
            else:
                self._log(" | ".join(simple_lines[:6]))

            result_dialog = ImportResultDialog(
                result,
                dry_run=dry_run,
                debug_mode=self.debug_log_enabled,
                supplier_name=supplier_name,
                payment_name=payment_name,
                invoice_lines=self.current_invoice.lines if self.current_invoice is not None else None,
                parent=self,
            )
            result_dialog.exec()
        except ImportValidationError as exc:
            self._error(str(exc), exc=exc)
        except TirikaDBError as exc:
            self._error(str(exc), exc=exc)
        except Exception as exc:
            self._error("Ошибка импорта", exc=exc)

    def _collect_import_attention_lines(self, lines: list[InvoiceLine]) -> list[InvoiceLine]:
        out: list[InvoiceLine] = []
        for line in lines:
            if (
                line.match_status in {"ambiguous", "hint", "not_found"}
                or line.action == "create"
                or bool(line.warning.strip())
            ):
                out.append(line)
        return out

    def _populate_table(self, lines: list[InvoiceLine]) -> None:
        self._table_locked = True
        try:
            sorting_was_enabled = self.table.isSortingEnabled()
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(lines))
            for row, line in enumerate(lines):
                self._refresh_line_price_state(line)
                sell_price = line.sell_price if line.sell_price is not None else line.price
                sell_old = self._display_sell_price_in_db(line)
                diff_pct = line.sell_price_diff_percent
                markup_pct = self._calculate_markup_percent(buy_price=line.price, sell_price=sell_old)
                values = [
                    str(line.line_no),
                    line.article,
                    line.name,
                    line.note,
                    _fmt_number(line.quantity, 3),
                    _fmt_number(line.price, 2),
                    _fmt_number(line.total, 2),
                    _fmt_number(sell_price, 2),
                    _fmt_number(sell_old, 2) if sell_old is not None else "",
                    _fmt_number(diff_pct, 1) if diff_pct is not None else "",
                    _fmt_number(markup_pct, 1) if markup_pct is not None else "",
                    self._status_text(line.match_status),
                    "",
                    str(line.matched_good_id or ""),
                    line.matched_product_code or line.article,
                    line.matched_name or line.name,
                    line.similar_articles,
                    line.match_method,
                    self._display_warning(line),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col in {
                        COL_LINE,
                        COL_QTY,
                        COL_BUY_PRICE,
                        COL_SELL_PRICE,
                        COL_SELL_PRICE_OLD,
                        COL_SELL_DIFF,
                        COL_MARKUP,
                        COL_SUM,
                        COL_GOOD_ID,
                    }:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if col in {
                        COL_LINE,
                        COL_STATUS,
                        COL_METHOD,
                        COL_SELL_PRICE_OLD,
                        COL_SELL_DIFF,
                        COL_MARKUP,
                        COL_SIMILAR,
                        COL_WARNING,
                    }:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if col in {COL_STATUS, COL_WARNING, COL_GOOD_CODE, COL_GOOD_NAME, COL_METHOD}:
                        item.setForeground(QColor(20, 20, 20))
                    if col == COL_STATUS:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                    self.table.setItem(row, col, item)

                status_color = self._status_color(line.match_status)
                if status_color:
                    for col in (COL_STATUS, COL_GOOD_ID, COL_GOOD_CODE, COL_GOOD_NAME):
                        item = self.table.item(row, col)
                        if item is not None:
                            item.setBackground(status_color)
                            item.setForeground(QColor(20, 20, 20))

                if line.price_alert:
                    for col in (COL_SELL_PRICE, COL_SELL_PRICE_OLD, COL_SELL_DIFF, COL_MARKUP):
                        item = self.table.item(row, col)
                        if item is not None:
                            item.setBackground(QColor(255, 184, 184))
                            item.setForeground(QColor(92, 0, 0))
                elif line.raw_data.get("_price_applied", False):
                    for col in (COL_SELL_PRICE, COL_SELL_PRICE_OLD, COL_SELL_DIFF, COL_MARKUP):
                        item = self.table.item(row, col)
                        if item is not None:
                            item.setBackground(QColor(221, 236, 255))

                if line.raw_data.get("_manual_edited", False):
                    for col in (COL_ARTICLE, COL_NAME, COL_NOTE, COL_QTY, COL_BUY_PRICE, COL_SUM):
                        item = self.table.item(row, col)
                        if item is not None:
                            item.setBackground(QColor(232, 243, 255))
                    if not line.price_alert:
                        sell_item = self.table.item(row, COL_SELL_PRICE)
                        if sell_item is not None:
                            sell_item.setBackground(QColor(232, 243, 255))

                combo = QComboBox(self.table)
                combo.addItem("import")
                combo.addItem("create")
                combo.addItem("skip")
                action = line.action if line.action in {"import", "create", "skip"} else "skip"
                combo.setCurrentText(action)
                combo.currentTextChanged.connect(
                    lambda val, row_idx=row: self._on_action_changed(row_idx, val)
                )
                self.table.setCellWidget(row, COL_ACTION, combo)

            self.summary_label.setText(self._build_summary(lines))
            self.invoice_totals_label.setText(self._build_invoice_totals(lines))
            if lines and not self._column_layout_initialized:
                self._restoring_header_state = True
                try:
                    self.table.resizeColumnsToContents()
                finally:
                    self._restoring_header_state = False
                self._column_layout_initialized = True
                self._save_table_header_state(silent=True)
            self._apply_table_filter()
            self.table.setSortingEnabled(sorting_was_enabled)
        finally:
            self._table_locked = False

    def _sync_lines_from_table(self, strict: bool = True) -> None:
        if self.current_invoice is None or self.matcher is None:
            return
        for row, line in enumerate(self.current_invoice.lines):
            before_good_id = line.matched_good_id
            combo = self.table.cellWidget(row, COL_ACTION)
            if isinstance(combo, QComboBox):
                line.action = combo.currentText().strip()

            article = normalize_article(self._item_text(row, COL_ARTICLE))
            name = normalize_text_field(self._item_text(row, COL_NAME), max_len=120)
            note = normalize_text_field(self._item_text(row, COL_NOTE), max_len=250)
            if not article:
                article = normalize_article(line.article)
            if not name:
                name = normalize_text_field(line.name, max_len=120)
            if strict and not article:
                raise ImportValidationError(f"Строка {line.line_no}: артикул пустой.")
            if strict and not name:
                raise ImportValidationError(f"Строка {line.line_no}: название пустое.")

            qty = self._parse_float_input(
                self._item_text(row, COL_QTY),
                line_no=line.line_no,
                field_name="кол-во",
                strict=strict,
                default=line.quantity,
            )
            buy_price = self._parse_float_input(
                self._item_text(row, COL_BUY_PRICE),
                line_no=line.line_no,
                field_name="закупка",
                strict=strict,
                default=line.price,
            )
            sell_price = self._parse_float_input(
                self._item_text(row, COL_SELL_PRICE),
                line_no=line.line_no,
                field_name="продажа",
                strict=strict,
                default=line.sell_price if line.sell_price is not None else line.price,
            )
            total = self._parse_float_input(
                self._item_text(row, COL_SUM),
                line_no=line.line_no,
                field_name="сумма",
                strict=False,
                default=0.0,
            )
            if total <= 0:
                total = round(qty * buy_price, 2)

            line.article = article
            line.name = name
            line.note = note
            line.quantity = qty
            line.price = buy_price
            line.sell_price = sell_price
            line.total = total
            line.raw_data["_sell_initialized"] = True

            raw_good = self._item_text(row, COL_GOOD_ID)
            if raw_good:
                try:
                    good_id = int(raw_good)
                except ValueError:
                    if strict:
                        raise ImportValidationError(
                            f"Строка {line.line_no}: некорректный Good ID '{raw_good}'."
                        ) from None
                    good_id = -1
                good = self.matcher.catalog.get(good_id)
                if good is None and strict:
                    raise ImportValidationError(
                        f"Строка {line.line_no}: Good ID '{good_id}' не найден в базе."
                    )
                if good is not None:
                    line.matched_good_id = good_id
                    if before_good_id != good_id:
                        line.match_status = "manual"
                        line.match_method = "manual"
                        if line.action == "skip":
                            line.action = "import"
                    line.matched_tax_mode = good.tax_mode
                    line.existing_sell_price = good.sell_price
                else:
                    line.matched_good_id = None
                    line.existing_sell_price = None
            else:
                line.matched_good_id = None
                line.existing_sell_price = None

            target_code = normalize_article(self._item_text(row, COL_GOOD_CODE) or line.article)
            target_name = normalize_text_field(
                self._item_text(row, COL_GOOD_NAME) or line.name,
                max_len=120,
            )
            line.matched_product_code = target_code
            line.matched_name = target_name
            self._refresh_line_price_state(line)

    def _on_action_changed(self, row: int, action: str) -> None:
        if self.current_invoice is None:
            return
        if 0 <= row < len(self.current_invoice.lines):
            line = self.current_invoice.lines[row]
            changed = line.action != action
            if line.action != action:
                line.raw_data["_manual_edited"] = True
            line.action = action
            if changed:
                self._record_history_state()
            self._apply_table_filter()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._table_locked:
            return
        if self.current_invoice is None or self.matcher is None:
            return
        row = item.row()
        if row < 0 or row >= len(self.current_invoice.lines):
            return
        line = self.current_invoice.lines[row]
        line.raw_data["_manual_edited"] = True
        if item.column() != COL_GOOD_ID:
            try:
                self._sync_lines_from_table(strict=False)
                self._populate_table(self.current_invoice.lines)
                self._record_history_state()
            except Exception as exc:
                self._log(f"Предупреждение: не удалось синхронизировать строку после ручного изменения: {exc}")
            return
        try:
            self._sync_lines_from_table(strict=False)
        except Exception as exc:
            self._log(f"Предупреждение: не удалось синхронизировать строку после ручного ввода Good ID: {exc}")
        raw = item.text().strip()
        if not raw:
            line.matched_good_id = None
            line.matched_name = line.name
            line.matched_product_code = line.article
            line.existing_sell_price = None
            line.match_status = "not_found"
            line.warning = "Good ID очищен вручную."
            self._refresh_line_price_state(line)
            self._populate_table(self.current_invoice.lines)
            self._record_history_state()
            return
        try:
            good_id = int(raw)
            self.matcher.apply_manual_good(line, good_id)
            if line.action == "skip":
                line.action = "import"
            self._refresh_line_price_state(line)
            self._populate_table(self.current_invoice.lines)
            self._record_history_state()
        except Exception as exc:
            self._error("Ошибка ручного ввода Good ID", exc=exc)
            self._populate_table(self.current_invoice.lines)

    def _select_supplier_by_hint(self, hint: str) -> None:
        target = _normalize_supplier_name(hint)
        if not target:
            return

        best_index = -1
        best_score = 0
        best_len_delta = 10_000

        for idx in range(self.supplier_combo.count()):
            raw_text = self.supplier_combo.itemText(idx)
            supplier_name = _extract_supplier_name(raw_text)
            normalized_name = _normalize_supplier_name(supplier_name)
            score = _supplier_match_score(normalized_name, target)
            if score <= 0:
                continue
            len_delta = abs(len(normalized_name) - len(target))
            if score > best_score or (score == best_score and len_delta < best_len_delta):
                best_index = idx
                best_score = score
                best_len_delta = len_delta

        if best_index < 0:
            if hasattr(self, "supplier_detect_label"):
                self.supplier_detect_label.setText(f"Поставщик не определен автоматически: {hint}")
            return

        self.supplier_combo.setCurrentIndex(best_index)
        supplier_name = _extract_supplier_name(self.supplier_combo.itemText(best_index))
        if hasattr(self, "supplier_detect_label"):
            self.supplier_detect_label.setText(
                f"Автоопределение поставщика: {supplier_name}"
            )

    def _refresh_line_price_state(self, line: InvoiceLine) -> None:
        existing_sell: float | None = line.existing_sell_price
        if self.matcher is not None and line.matched_good_id is not None:
            good = self.matcher.catalog.get(line.matched_good_id)
            if good is not None:
                existing_sell = float(good.sell_price or 0.0)
        line.existing_sell_price = existing_sell

        suggested = calculate_suggested_sell_price(
            line.price,
            markup_percent=self.app_settings.markup_percent,
            round_step=self.app_settings.round_step,
        )
        line.suggested_sell_price = suggested

        if not line.raw_data.get("_sell_initialized", False):
            if line.sell_price is None:
                line.sell_price = suggested
            elif existing_sell is not None and abs(line.sell_price - existing_sell) <= 0.0001:
                line.sell_price = suggested
            elif existing_sell is None and abs(line.sell_price - line.price) <= 0.0001:
                line.sell_price = suggested
            line.raw_data["_sell_initialized"] = True

        # If user returned sale price to current DB value, cancel forced DB-sale update.
        if line.raw_data.get("_force_update_sell_price", False):
            if existing_sell is None or line.sell_price is None:
                line.raw_data.pop("_force_update_sell_price", None)
            elif abs(line.sell_price - existing_sell) <= 0.0001:
                line.raw_data.pop("_force_update_sell_price", None)

        if line.raw_data.get("_price_applied", False):
            if existing_sell is None or line.sell_price is None:
                line.raw_data.pop("_price_applied", None)
            elif abs(line.sell_price - existing_sell) <= 0.0001:
                line.raw_data.pop("_price_applied", None)

        if existing_sell is None:
            line.sell_price_diff_percent = None
            line.price_alert = False
            return

        # When sale price is accepted for DB update, red alert is no longer needed.
        will_update_sell = self.app_settings.update_existing_sell_price or bool(
            line.raw_data.get("_force_update_sell_price", False)
        )
        if will_update_sell:
            line.sell_price_diff_percent = 0.0
            line.price_alert = False
            return

        if existing_sell <= 0:
            diff_pct = 100.0 if (line.sell_price or 0.0) > 0 else 0.0
        else:
            diff_pct = abs((line.sell_price or 0.0) - existing_sell) / existing_sell * 100.0
        line.sell_price_diff_percent = diff_pct
        line.price_alert = diff_pct >= self.app_settings.price_alert_threshold_percent

    def _display_sell_price_in_db(self, line: InvoiceLine) -> float | None:
        existing_sell = line.existing_sell_price
        if existing_sell is None:
            return None
        if line.sell_price is None:
            return existing_sell
        will_update_sell = self.app_settings.update_existing_sell_price or bool(
            line.raw_data.get("_force_update_sell_price", False)
        )
        if will_update_sell:
            return float(line.sell_price)
        return existing_sell

    def _calculate_markup_percent(
        self,
        *,
        buy_price: float | None,
        sell_price: float | None,
    ) -> float | None:
        if buy_price is None or sell_price is None:
            return None
        if buy_price <= 0:
            return None
        return ((sell_price - buy_price) / buy_price) * 100.0

    def _display_warning(self, line: InvoiceLine) -> str:
        parts: list[str] = []
        if line.warning.strip():
            parts.append(line.warning.strip())
        if line.price_alert and line.sell_price_diff_percent is not None:
            parts.append(
                "Расхождение продажи: "
                f"{line.sell_price_diff_percent:.1f}% (порог {self.app_settings.price_alert_threshold_percent:.1f}%)"
            )
        return " | ".join(parts)

    def _status_text(self, status: str) -> str:
        return {
            "exact": "Найден",
            "manual": "Выбран вручную",
            "fuzzy": "По названию",
            "hint": "Похожий (1 вариант)",
            "ambiguous": "Несколько совпадений",
            "not_found": "Не найден",
        }.get(status, status or "")

    def _status_color(self, status: str) -> QColor | None:
        if status in {"exact", "manual"}:
            return QColor(214, 242, 214)
        if status == "fuzzy":
            return QColor(225, 238, 255)
        if status == "hint":
            return QColor(255, 244, 205)
        if status == "ambiguous":
            return QColor(255, 236, 186)
        if status == "not_found":
            return QColor(255, 210, 210)
        return None

    def _build_summary(self, lines: list[InvoiceLine]) -> str:
        total = len(lines)
        exact = sum(1 for x in lines if x.match_status in {"exact", "manual"})
        fuzzy = sum(1 for x in lines if x.match_status == "fuzzy")
        hints = sum(1 for x in lines if x.match_status == "hint")
        ambiguous = sum(1 for x in lines if x.match_status == "ambiguous")
        missing = sum(1 for x in lines if x.match_status == "not_found")
        price_alerts = sum(1 for x in lines if x.price_alert)
        return (
            f"Строк: {total} | Найдено: {exact} | По названию: {fuzzy} | "
            f"Похожие (1): {hints} | Неоднозначно: {ambiguous} | Не найдено: {missing} | Цена-красных: {price_alerts}"
        )

    def _build_invoice_totals(self, lines: list[InvoiceLine]) -> str:
        total_qty = sum(max(float(x.quantity), 0.0) for x in lines)
        total_sum = sum(
            (x.total if x.total > 0 else x.quantity * x.price)
            for x in lines
        )
        return (
            f"Товаров: {_fmt_number(total_qty, 3)} | "
            f"Сумма накладной: {_fmt_number(total_sum, 2)}"
        )

    def _selected_data(self, combo: QComboBox, default: int) -> int:
        data = combo.currentData()
        if data is None:
            return default
        return int(data)

    def _item_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        if item is None:
            return ""
        return item.text().strip()

    def _parse_float_input(
        self,
        value: str,
        *,
        line_no: int,
        field_name: str,
        strict: bool,
        default: float,
    ) -> float:
        text = value.strip().replace(" ", "").replace(",", ".")
        if not text:
            return default
        try:
            return float(text)
        except ValueError:
            if strict:
                raise ImportValidationError(
                    f"Строка {line_no}: поле '{field_name}' имеет некорректное число '{value}'."
                ) from None
            return default

    def _clear_filters(self) -> None:
        self._apply_table_filter()

    def _apply_table_filter(self) -> None:
        if self.current_invoice is None:
            return
        for row in range(len(self.current_invoice.lines)):
            self.table.setRowHidden(row, False)
        self.summary_label.setText(self._build_summary(self.current_invoice.lines))
        self.invoice_totals_label.setText(self._build_invoice_totals(self.current_invoice.lines))

    def _log(self, text: str) -> None:
        message = str(text)
        self.log_box.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def _error(self, text: str, exc: Exception | None = None) -> None:
        message = f"ERROR: {text}"
        if exc is not None:
            tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
            message = f"{message}: {exc}\n{''.join(tb).rstrip()}"
        self.log_box.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        QMessageBox.critical(self, "Ошибка", text)


def _fmt_number(value: float, digits: int) -> str:
    fmt = f"{{:.{digits}f}}"
    out = fmt.format(value)
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out


def _fill_payment_combo(combo: QComboBox) -> None:
    combo.clear()
    for label, payment_type in PAYMENT_OPTIONS:
        combo.addItem(label, userData=payment_type)


def _extract_supplier_name(combo_text: str) -> str:
    text = combo_text.strip()
    match = re.match(r"^(.*?)(?:\s*\[\d+\])?$", text)
    if match:
        return match.group(1).strip()
    return text


def _normalize_supplier_name(value: str) -> str:
    text = value.strip().lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def _supplier_match_score(supplier_name: str, target: str) -> int:
    if not supplier_name or not target:
        return 0
    if supplier_name == target:
        return 300
    if supplier_name.startswith(target) or target.startswith(supplier_name):
        return 220
    if target in supplier_name:
        return 140

    supplier_tokens = set(supplier_name.split())
    target_tokens = set(target.split())
    if not supplier_tokens or not target_tokens:
        return 0
    overlap = supplier_tokens & target_tokens
    if not overlap:
        return 0
    if target_tokens.issubset(supplier_tokens):
        return 110
    return 70


def _status_text_ru(status: str) -> str:
    return {
        "exact": "Найден",
        "manual": "Выбран вручную",
        "fuzzy": "По названию",
        "hint": "Похожий (1 вариант)",
        "ambiguous": "Несколько совпадений",
        "not_found": "Не найден",
    }.get(status, status or "")


def _status_color_for_dialog(status: str) -> QColor | None:
    if status in {"exact", "manual"}:
        return QColor(214, 242, 214)
    if status == "fuzzy":
        return QColor(225, 238, 255)
    if status == "hint":
        return QColor(255, 244, 205)
    if status == "ambiguous":
        return QColor(255, 236, 186)
    if status == "not_found":
        return QColor(255, 210, 210)
    return None


def _show_table_copy_menu(table: QTableWidget, pos, parent: QWidget) -> None:
    menu = QMenu(parent)
    action_copy_cell = menu.addAction("Копировать ячейку")
    action_copy_row = menu.addAction("Копировать строку")
    action_copy_selection = menu.addAction("Копировать выделенное")
    chosen = menu.exec(table.viewport().mapToGlobal(pos))
    if chosen is None:
        return
    if chosen == action_copy_cell:
        _copy_current_cell(table)
    elif chosen == action_copy_row:
        _copy_current_row(table)
    elif chosen == action_copy_selection:
        _copy_selected_cells(table)


def _copy_current_cell(table: QTableWidget) -> None:
    item = table.currentItem()
    if item is None:
        return
    QApplication.clipboard().setText(item.text())


def _copy_current_row(table: QTableWidget) -> None:
    row = table.currentRow()
    if row < 0:
        return
    values: list[str] = []
    for col in range(table.columnCount()):
        widget = table.cellWidget(row, col)
        if isinstance(widget, QComboBox):
            values.append(widget.currentText())
            continue
        item = table.item(row, col)
        values.append(item.text() if item is not None else "")
    QApplication.clipboard().setText("\t".join(values))


def _copy_selected_cells(table: QTableWidget) -> None:
    indexes = table.selectedIndexes()
    if not indexes:
        _copy_current_cell(table)
        return

    min_row = min(idx.row() for idx in indexes)
    max_row = max(idx.row() for idx in indexes)
    min_col = min(idx.column() for idx in indexes)
    max_col = max(idx.column() for idx in indexes)
    selected = {(idx.row(), idx.column()) for idx in indexes}

    lines: list[str] = []
    for row in range(min_row, max_row + 1):
        vals: list[str] = []
        for col in range(min_col, max_col + 1):
            if (row, col) not in selected:
                vals.append("")
                continue
            widget = table.cellWidget(row, col)
            if isinstance(widget, QComboBox):
                vals.append(widget.currentText())
                continue
            item = table.item(row, col)
            vals.append(item.text() if item is not None else "")
        lines.append("\t".join(vals))
    QApplication.clipboard().setText("\n".join(lines))
