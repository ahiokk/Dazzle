"""Тема оформления Dazzle — светлая «Refined Blue».

Вынесено из gui.py. Путь к ассетам резолвится так же: parent.parent == корень
проекта (theme.py лежит в tirika_importer/, рядом с gui.py).
"""
from __future__ import annotations

from pathlib import Path


APP_STYLESHEET = """
/* Dazzle — Refined Blue (light), density-tuned for the 16-column invoice table */

QWidget { background:#E9EEF6; color:#1E293B; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#E9EEF6; }
QLabel { background:transparent; }

/* Cards */
QFrame#topCard, QFrame#logCard {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #FBFCFE);
    border:1px solid #D8E1EF; border-radius:12px;
}

/* Header */
QLabel#titleLabel { font-size:17pt; font-weight:800; color:#0F1B3D; }
QLabel#subtitleLabel { color:#64748B; font-size:9.5pt; }

/* Totals chip */
QLabel#totalsPill {
    color:#1E40AF; font-weight:700;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #EEF3FE, stop:1 #E3ECFC);
    border:1px solid #CBD9F6; border-radius:9px; padding:6px 12px;
}

/* Footer status pills */
QLabel[pill="true"] { font-size:9.5pt; font-weight:700; border-radius:8px; padding:5px 12px; }
QLabel[pill="true"][tone="found"]     { color:#15803D; background:#E7F6EE; border:1px solid #BFE6CD; }
QLabel[pill="true"][tone="ambiguous"] { color:#1E40AF; background:#E9EFFC; border:1px solid #C6D6F5; }
QLabel[pill="true"][tone="missing"]   { color:#B42318; background:#FCECEC; border:1px solid #F3C9C5; }
QLabel[pill="true"][tone="warning"]   { color:#92560A; background:#FDF4E2; border:1px solid #EFD9A6; }

/* Inputs */
QLineEdit, QComboBox, QPlainTextEdit {
    background:#FFFFFF; border:1px solid #CBD6E6; border-radius:8px; padding:5px 10px;
    selection-background-color:#1E40AF; selection-color:#FFFFFF;
}
QLineEdit, QComboBox { min-height:32px; }
QLineEdit:hover, QComboBox:hover { border-color:#A9BEDE; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border:2px solid #2563EB; padding:4px 9px; }
QComboBox::drop-down { border:none; width:22px; subcontrol-position:center right; }
QComboBox::down-arrow { image:url(__ASSET_DIR__/chevron-down.svg); width:11px; height:11px; }

/* Buttons */
QPushButton {
    background:#FFFFFF; color:#1E293B; border:1px solid #CBD6E6; border-radius:8px;
    padding:6px 14px; min-height:32px; font-weight:600;
}
QPushButton:hover { background:#F2F6FC; border-color:#A9BEDE; }
QPushButton:pressed { background:#E8EFF8; }
QPushButton:disabled { background:#F2F4F8; color:#9AA7BC; border-color:#DDE4EF; }
QPushButton#primaryBtn {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color:#FFFFFF; border:1px solid #1B3A98;
}
QPushButton#primaryBtn:hover { background:#1E40AF; }
QPushButton#primaryBtn:pressed { background:#18337F; }
QPushButton#primaryBtn:disabled { background:#9CB4E8; border-color:#9CB4E8; color:#EAF0FB; }
QPushButton#successBtn {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #16A34A, stop:1 #128041);
    color:#FFFFFF; border:1px solid #0F7037;
}
QPushButton#successBtn:hover { background:#128041; }
QPushButton#successBtn:pressed { background:#0E6334; }
QPushButton#subtleBtn { background:#F4F7FC; color:#334155; border:1px solid #D8E1EF; }
QPushButton#subtleBtn:hover { background:#EAF1FA; border-color:#C2D2EA; }

/* Tabs */
QTabWidget::pane { border:1px solid #D8E1EF; border-radius:12px; background:#FFFFFF; top:-1px; }
QTabBar::tab {
    background:#E7EDF7; color:#43546E; border:1px solid #D2DDEC; border-bottom:none;
    padding:8px 18px; margin-right:6px;
    border-top-left-radius:9px; border-top-right-radius:9px; font-weight:600;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color:#FFFFFF; border:1px solid #1B3A98;
}
QTabBar::tab:hover:!selected { background:#DCE6F6; color:#1E40AF; }

/* Table — dense */
QTableWidget {
    background:#FFFFFF; border:1px solid #D8E1EF; border-radius:10px;
    gridline-color:#EDF1F8;
    alternate-background-color:#F7FAFD;
    selection-background-color:#DCE8FF; selection-color:#0F1B3D;
    font-size:9pt;
}
QTableWidget::item { padding:0px 5px; }
QHeaderView::section {
    background:#EAF0FA; color:#34507F;
    border:0; border-right:1px solid #DEE6F2; border-bottom:2px solid #CBD9F0;
    padding:6px 6px; font-weight:700; font-size:8.5pt;
}
QHeaderView::section:last { border-right:0; }
QTableCornerButton::section { background:#EAF0FA; border:0; }

/* In-table action combos */
QTableWidget QComboBox {
    min-height:24px; max-height:24px; padding:1px 6px; border-radius:6px; font-weight:600; font-size:8.5pt;
}
QTableWidget QComboBox::drop-down { width:16px; }
QTableWidget QComboBox[actionKind="import"] { background:#E7F6EE; color:#15803D; border:1px solid #BFE6CD; }
QTableWidget QComboBox[actionKind="create"] { background:#E9EFFC; color:#1E40AF; border:1px solid #C6D6F5; }
QTableWidget QComboBox[actionKind="skip"]   { background:#F1F4F9; color:#64748B; border:1px solid #D6DEEA; }

/* Checkbox */
QCheckBox { spacing:8px; color:#334155; background:transparent; }
QCheckBox::indicator { width:18px; height:18px; }
QCheckBox::indicator:unchecked { border:1px solid #A9BAD2; border-radius:5px; background:#FFFFFF; }
QCheckBox::indicator:hover { border-color:#2563EB; }
QCheckBox::indicator:checked {
    border:1px solid #1E40AF; border-radius:5px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2563EB, stop:1 #1E40AF);
}

/* Tool buttons */
QToolButton#helpBtn { background:#EAF0FB; color:#1E40AF; border:1px solid #C6D6F5; border-radius:14px; font-weight:800; }
QToolButton#helpBtn:hover { background:#DCE6F8; }
QToolButton#debugToggleBtn {
    background:#EFF3F9; border:1px solid #CBD6E6; border-radius:8px; color:#1E40AF;
    font-size:9pt; font-weight:700; padding:0 10px;
}
QToolButton#debugToggleBtn:checked { background:#1E40AF; border:1px solid #1B3A98; color:#FFFFFF; }

/* Result / metrics / ozon (used in dialogs and other tabs) */
QFrame#resultHeader { background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FBFCFE, stop:1 #F3F7FE); border:1px solid #D8E1EF; border-radius:12px; }
QLabel#resultStateOk { background:#E7F6EE; color:#15803D; border:1px solid #BFE6CD; border-radius:9px; padding:8px 14px; font-weight:800; }
QLabel#resultStateDry { background:#E9EFFC; color:#1E40AF; border:1px solid #C6D6F5; border-radius:9px; padding:8px 14px; font-weight:800; }
QFrame#metricCard { background:#FFFFFF; border:1px solid #DCE5F1; border-top:2px solid #2563EB; border-radius:10px; }
QLabel#metricTitle { color:#64748B; font-size:8.5pt; font-weight:600; background:transparent; }
QLabel#metricValue { color:#0F1B3D; font-size:18pt; font-weight:800; background:transparent; }
QLabel#resultTagImport { background:#E7F6EE; color:#15803D; border:1px solid #BFE6CD; border-radius:8px; padding:6px 12px; font-weight:700; }
QLabel#resultTagCreate { background:#E9EFFC; color:#1E40AF; border:1px solid #C6D6F5; border-radius:8px; padding:6px 12px; font-weight:700; }
QLabel#resultTagSkip   { background:#F1F4F9; color:#64748B; border:1px solid #D6DEEA; border-radius:8px; padding:6px 12px; font-weight:700; }
QListWidget#warningsList { background:#FFFFFF; border:1px solid #D8E1EF; border-radius:10px; padding:6px; }
QListWidget#warningsList::item { padding:7px 8px; border-radius:6px; color:#334155; }
QListWidget#warningsList::item:hover { background:#F2F6FC; }
QListWidget#warningsList::item:selected { background:#DCE8FF; color:#0F1B3D; }
QGroupBox { border:1px solid #DCE5F1; border-radius:10px; margin-top:10px; padding-top:10px; background:#FAFCFE; font-weight:700; color:#34507F; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 6px; color:#34507F; }
QFrame#ozonSteps { background:#F4F8FE; border:1px solid #D8E4F6; border-radius:10px; }
QLabel#ozonStep { color:#334155; }

/* Scrollbars */
QScrollBar:vertical { background:transparent; width:12px; margin:2px; }
QScrollBar::handle:vertical { background:#C2CEE0; border-radius:5px; min-height:32px; }
QScrollBar::handle:vertical:hover { background:#9FB2D0; }
QScrollBar:horizontal { background:transparent; height:12px; margin:2px; }
QScrollBar::handle:horizontal { background:#C2CEE0; border-radius:5px; min-width:32px; }
QScrollBar::handle:horizontal:hover { background:#9FB2D0; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; background:none; border:none; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
""".replace("__ASSET_DIR__", Path(__file__).resolve().parent.parent.as_posix())
