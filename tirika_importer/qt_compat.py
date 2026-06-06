from __future__ import annotations

QT_BINDING = "PySide6"

try:
    from PySide6.QtCore import (
        QByteArray,
        QDate,
        QEvent,
        QObject,
        QSize,
        QStringListModel,
        QThread,
        QTimer,
        Qt,
        Signal,
    )
    from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
    from PySide6.QtSvgWidgets import QSvgWidget
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QCompleter,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGraphicsDropShadowEffect,
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
        QScrollArea,
        QSizePolicy,
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
    from PySide2.QtCore import (
        QByteArray,
        QDate,
        QEvent,
        QObject,
        QSize,
        QStringListModel,
        QThread,
        QTimer,
        Qt,
        Signal,
    )
    from PySide2.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
    from PySide2.QtSvg import QSvgWidget
    from PySide2.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QCompleter,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGraphicsDropShadowEffect,
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
        QScrollArea,
        QSizePolicy,
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


def qt_exec(obj, *args, **kwargs):
    method = getattr(obj, "exec", None)
    if callable(method):
        return method(*args, **kwargs)
    legacy_method = getattr(obj, "exec_", None)
    if callable(legacy_method):
        return legacy_method(*args, **kwargs)
    raise AttributeError(f"{type(obj).__name__} has no exec/exec_ method")
