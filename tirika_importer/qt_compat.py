from __future__ import annotations

QT_BINDING = "PySide6"

try:
    from PySide6.QtCore import QByteArray, QEvent, QObject, QThread, QTimer, Qt, Signal
    from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
    from PySide6.QtSvgWidgets import QSvgWidget
    from PySide6.QtWidgets import (
        QAbstractItemView,
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
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    QT_BINDING = "PySide2"
    from PySide2.QtCore import QByteArray, QEvent, QObject, QThread, QTimer, Qt, Signal
    from PySide2.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
    from PySide2.QtSvg import QSvgWidget
    from PySide2.QtWidgets import (
        QAbstractItemView,
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
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

