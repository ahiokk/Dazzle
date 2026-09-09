"""Общее для окон Dazzle: выбор товара и копирование ячеек таблицы.

Вынесено из gui.py, чтобы вкладкой Ozon (ozon_gui.py) можно было
пользоваться, не таща за собой всё главное окно.
"""
from __future__ import annotations

from .matcher import GoodsMatcher
from .models import MatchCandidate
from .qt_compat import (
    QApplication,
    QComboBox,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    qt_exec,
)
from .theme import APP_STYLESHEET


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


def _fmt_number(value: float, digits: int) -> str:
    fmt = f"{{:.{digits}f}}"
    out = fmt.format(value)
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out


def _show_table_copy_menu(table: QTableWidget, pos, parent: QWidget) -> None:
    menu = QMenu(parent)
    action_copy_cell = menu.addAction("Копировать ячейку")
    action_copy_row = menu.addAction("Копировать строку")
    action_copy_selection = menu.addAction("Копировать выделенное")
    chosen = qt_exec(menu, table.viewport().mapToGlobal(pos))
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
