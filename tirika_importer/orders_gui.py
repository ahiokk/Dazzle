"""Экран «Заказы и напоминания» — airy-agenda по макету пользователя.

Слева повестка: текстовые фильтры со счётчиками и сгруппированный плоский
список («Заказы» из Tirika + «Заметки и задачи» — ручные). Справа — карточка
создания/редактирования. Поле «Покупатель» с автодополнением по клиентам базы.
Работает на PySide6 (Win10) и PySide2 (Win7).

Важно про обрезку текста в Qt: НЕ меняем font-weight у активных кнопок
(иначе ширина считается по обычному шрифту и жирный текст срезается) —
активность показываем цветом и подчёркиванием.
"""

from __future__ import annotations

from datetime import date, datetime

from .orders_store import (
    OrdersStore,
    Reminder,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_HIDDEN,
)
from .models import TirikaOrder
from .qt_compat import (
    QCompleter,
    QDate,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStringListModel,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
)


ORDERS_STYLESHEET = """
/* Orders & Reminders — Refined Blue, elevated cards */
#ordersRoot { background: #E9EEF6; }
#agendaPane { background: #EFF3F9; }
#composerPane { background: #FFFFFF; border-left: 1px solid #D8E1EF; }
#listScroll { background: transparent; border: none; }
#listContent { background: transparent; }
#ordersRoot QScrollArea { border: none; background: transparent; }

#ordersRoot QLabel#dateTitle { font-size: 18pt; font-weight: 800; color: #0F1B3D; }

/* Search — rounded field, consistent with the app */
#ordersRoot QLineEdit#searchEdit {
    border: 1px solid #CBD6E6; border-radius: 9px; background: #FFFFFF;
    padding: 7px 12px; font-size: 11pt; color: #1E293B; min-height: 20px;
}
#ordersRoot QLineEdit#searchEdit:focus { border: 2px solid #2563EB; padding: 6px 11px; }

/* Filter chips (segmented) */
#ordersRoot QPushButton#filter {
    border: 1px solid #D8E1EF; background: #FFFFFF; color: #5B6B86; font-size: 10.5pt;
    font-weight: 600; padding: 7px 14px; border-radius: 9px;
}
#ordersRoot QPushButton#filter:hover { background: #EAF1FA; color: #1E40AF; border-color: #C2D2EA; }
#ordersRoot QPushButton#filter:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color: #FFFFFF; border: 1px solid #1B3A98;
}

/* New note — real accent button */
#ordersRoot QPushButton#addLink {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color: #FFFFFF; border: 1px solid #1B3A98; border-radius: 9px;
    font-weight: 700; font-size: 10.5pt; padding: 7px 16px;
}
#ordersRoot QPushButton#addLink:hover { background: #1E40AF; }
#ordersRoot QPushButton#addLink:pressed { background: #18337F; }

/* Group headers */
#ordersRoot QLabel#groupTitle { font-size: 11pt; font-weight: 800; color: #34507F; }
#ordersRoot QFrame#groupRule { background: #DCE4F0; min-height: 1px; max-height: 1px; }

/* Note cards */
#ordersRoot QFrame#row { background: #FFFFFF; border: 1px solid #E1E8F2; border-radius: 12px; }
#ordersRoot QFrame#row:hover { background: #FBFCFE; border-color: #C2D2EA; }
#ordersRoot QFrame#row[selected="true"] { background: #F4F8FE; border: 2px solid #2563EB; }

#ordersRoot QLabel#dot { min-width: 10px; max-width: 10px; min-height: 10px; max-height: 10px; border-radius: 5px; }
#ordersRoot QLabel#dot[tone="red"]   { background: #DC2626; }
#ordersRoot QLabel#dot[tone="amber"] { background: #D97706; }
#ordersRoot QLabel#dot[tone="blue"]  { background: #2563EB; }
#ordersRoot QLabel#dot[tone="green"] { background: #16A34A; }
#ordersRoot QLabel#dot[tone="gray"]  { background: #94A3B8; }

#ordersRoot QLabel#rowName { font-size: 12.5pt; font-weight: 700; color: #0F1B3D; }
#ordersRoot QLabel#rowNameDone { font-size: 12.5pt; font-weight: 700; color: #9AA7BC; }
#ordersRoot QLabel#rowNote { font-size: 10.5pt; color: #64748B; }
#ordersRoot QLabel#rowNoteDone { font-size: 10.5pt; color: #AAB4C4; }
#ordersRoot QLabel#rowSub { font-size: 10pt; color: #9AA7BC; }
#ordersRoot QLabel#rowAmount { font-size: 10pt; color: #0F1B3D; font-weight: 700; }
#ordersRoot QLabel#rowPay { font-size: 10pt; font-weight: 700; }
#ordersRoot QLabel#rowPay[pay="full"] { color: #15803D; }
#ordersRoot QLabel#rowPay[pay="part"] { color: #92560A; }
#ordersRoot QLabel#rowPay[pay="none"] { color: #B42318; }
#ordersRoot QLabel#rowWhen { font-size: 10.5pt; font-weight: 700; }
#ordersRoot QLabel#rowWhen[tone="red"]   { color: #B42318; }
#ordersRoot QLabel#rowWhen[tone="amber"] { color: #92560A; }
#ordersRoot QLabel#rowWhen[tone="blue"]  { color: #2563EB; }
#ordersRoot QLabel#rowWhen[tone="green"] { color: #15803D; }
#ordersRoot QLabel#rowWhen[tone="gray"]  { color: #94A3B8; }

/* Complete check */
#ordersRoot QPushButton#doCheck {
    border: 1.5px solid #CBD6E6; background: #FFFFFF; color: transparent;
    border-radius: 13px; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
    font-size: 11pt; font-weight: 800;
}
#ordersRoot QPushButton#doCheck:hover { border: 1.5px solid #16A34A; color: #16A34A; background: #E7F6EE; }
#ordersRoot QPushButton#doCheck[done="true"] { border: 1.5px solid #15803D; background: #16A34A; color: #FFFFFF; }

#ordersRoot QLabel#emptyList { color: #94A3B8; font-size: 11pt; }

/* Composer / detail */
#ordersRoot QLabel#composerTitle { font-size: 16pt; font-weight: 800; color: #0F1B3D; }
#ordersRoot QLabel#fieldLab { color: #64748B; font-size: 9.5pt; font-weight: 700; }
#ordersRoot QLineEdit#lineIn {
    border: none; border-bottom: 1.5px solid #D8E1EF; background: transparent;
    padding: 6px 2px; font-size: 12.5pt; color: #0F1B3D; min-height: 28px;
}
#ordersRoot QLineEdit#lineIn:focus { border: none; border-bottom: 2px solid #2563EB; }
#ordersRoot QLineEdit#lineIn:read-only { color: #64748B; }
#ordersRoot QPushButton#dueOpt {
    border: 1px solid #D8E1EF; background: #FFFFFF; color: #5B6B86; font-size: 10pt; font-weight: 600;
    padding: 6px 12px; border-radius: 8px;
}
#ordersRoot QPushButton#dueOpt:hover { background: #EAF1FA; color: #1E40AF; border-color: #C2D2EA; }
#ordersRoot QPushButton#dueOpt:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color: #FFFFFF; border: 1px solid #1B3A98;
}
#ordersRoot QDateEdit#dateIn {
    border: 1px solid #CBD6E6; border-radius: 8px; background: #FFFFFF;
    padding: 5px 8px; font-size: 11pt; color: #1E293B; min-height: 26px;
}
#ordersRoot QDateEdit#dateIn:focus { border: 2px solid #2563EB; }
#ordersRoot QDateEdit#dateIn:disabled { color: #B6C0D0; background: #F2F4F8; }
#ordersRoot QDateEdit#dateIn::drop-down { border: none; width: 18px; }
#ordersRoot QPlainTextEdit#noteIn {
    border: 1px solid #CBD6E6; border-radius: 10px; background: #FFFFFF;
    padding: 12px 13px; font-size: 12pt; color: #1E293B;
}
#ordersRoot QPlainTextEdit#noteIn:focus { border: 2px solid #2563EB; }
#ordersRoot QLabel#compBox { background: #F1F5FB; border: 1px solid #E1E8F2; border-radius: 10px; padding: 13px 14px; color: #46506A; font-size: 11pt; }
#ordersRoot QLabel#compHead { color: #64748B; font-size: 9.5pt; font-weight: 700; }

/* Save = primary accent */
#ordersRoot QPushButton#saveBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E40AF);
    color: #FFFFFF; border: 1px solid #1B3A98; border-radius: 10px;
    padding: 0 24px; min-height: 44px; font-size: 12pt; font-weight: 700;
}
#ordersRoot QPushButton#saveBtn:hover { background: #1E40AF; }
#ordersRoot QPushButton#saveBtn:pressed { background: #18337F; }
#ordersRoot QPushButton#saveBtn:disabled { background: #9CB4E8; border-color: #9CB4E8; color: #EAF0FB; }
#ordersRoot QPushButton#txtAct { border: none; background: transparent; color: #64748B; font-size: 11pt; font-weight: 600; }
#ordersRoot QPushButton#txtAct:hover { color: #15803D; }
#ordersRoot QPushButton#txtDel { border: none; background: transparent; color: #64748B; font-size: 11pt; font-weight: 600; }
#ordersRoot QPushButton#txtDel:hover { color: #B42318; }
#ordersRoot QLabel#emptyTitle { color: #475569; font-size: 13pt; font-weight: 800; }
#ordersRoot QLabel#emptySub { color: #94A3B8; font-size: 10.5pt; }

/* Scrollbars (match app) */
#ordersRoot QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
#ordersRoot QScrollBar::handle:vertical { background: #C2CEE0; border-radius: 5px; min-height: 32px; }
#ordersRoot QScrollBar::handle:vertical:hover { background: #9FB2D0; }
#ordersRoot QScrollBar::add-line:vertical, #ordersRoot QScrollBar::sub-line:vertical { height: 0; }
#ordersRoot QScrollBar::add-page, #ordersRoot QScrollBar::sub-page { background: transparent; }
#ordersRoot QWidget#agendaSection { background: transparent; }
"""

_RU_MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_RU_WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def _parse_iso(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _fmt_when(d: date | None, done: bool) -> str:
    if done:
        return "готово"
    if d is None:
        return "без срока"
    today = date.today()
    delta = (d - today).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == -1:
        return "вчера"
    if delta < 0:
        return f"просрочен {-delta} дн"
    if delta <= 14:
        return f"{_RU_WD[d.weekday()]}, {d.day:02d}.{d.month:02d}"
    return d.strftime("%d.%m.%Y")


def _fmt_amount(value: float) -> str:
    if not value:
        return ""
    out = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    if out.endswith(",00"):
        out = out[:-3]
    return out + " ₽"


class _Entry:
    __slots__ = ("kind", "id", "customer", "note", "due", "status", "amount", "paid", "obj")

    def __init__(self, kind, eid, customer, note, due, status, amount, paid, obj):
        self.kind = kind
        self.id = eid
        self.customer = customer
        self.note = note
        self.due: date | None = due
        self.status = status
        self.amount = amount
        self.paid = paid
        self.obj = obj

    @property
    def is_overdue(self) -> bool:
        return self.status == STATUS_ACTIVE and self.due is not None and self.due < date.today()

    @property
    def is_today(self) -> bool:
        return self.status == STATUS_ACTIVE and self.due == date.today()

    def tone(self) -> str:
        if self.status == STATUS_DONE:
            return "gray"
        if self.is_overdue:
            return "red"
        if self.is_today:
            return "amber"
        if self.kind == "tirika":
            return "blue"
        return "green"

    def rank(self) -> int:
        if self.status == STATUS_DONE:
            return 4
        if self.is_overdue:
            return 0
        if self.is_today:
            return 1
        if self.kind == "tirika":
            return 2
        return 3

    def pay_state(self) -> tuple[str, str]:
        if self.kind != "tirika" or not self.amount:
            return "", ""
        if self.paid + 1e-6 >= self.amount:
            return "оплачено", "full"
        if self.paid > 0:
            return "предоплата", "part"
        return "не оплачено", "none"


class _Row(QFrame):
    clicked = Signal(object)

    def __init__(self, entry: _Entry, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.entry)
        super().mousePressEvent(event)


class OrdersWidget(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main = main_window
        self.setObjectName("ordersRoot")
        try:
            self.store: OrdersStore | None = OrdersStore()
        except Exception:
            self.store = None
        self.order_customer: tuple[int, str] | None = None
        self._tirika_orders: list[TirikaOrder] = []
        self._entries: list[_Entry] = []
        self._current: _Entry | None = None
        self._mode = "empty"
        self._filter_value = "active"
        self._due_mode = "today"
        self._customer_to_id: dict[str, int] = {}
        self._ref_built_for: tuple = ()
        self._customer_model = QStringListModel(self)
        self._row_widgets: list[_Row] = []

        self.setStyleSheet(ORDERS_STYLESHEET)
        self._build_ui()
        self._show_empty_detail()

    # --- интерфейс ----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        agenda = QWidget(self)
        agenda.setObjectName("agendaPane")
        agenda.setMinimumWidth(560)
        a = QVBoxLayout(agenda)
        a.setContentsMargins(30, 26, 30, 24)
        a.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(14)
        d = date.today()
        title = QLabel(f"Сегодня · {d.day} {_RU_MONTHS[d.month - 1]}, {_RU_WD[d.weekday()]}", self)
        title.setObjectName("dateTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("searchEdit")
        self.search_edit.setPlaceholderText("Поиск")
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(lambda _=None: self._rebuild_list())
        head.addWidget(self.search_edit)
        a.addLayout(head)
        a.addSpacing(22)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._filter_buttons = {}
        for key, label in (
            ("active", "Активные"),
            ("today", "Сегодня"),
            ("overdue", "Просрочено"),
            ("all", "Все"),
            ("done", "Готово"),
        ):
            b = QPushButton(label, self)
            b.setObjectName("filter")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == "active")
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._filter_buttons[key] = b
            filters.addWidget(b)
        filters.addStretch(1)
        self.add_btn = QPushButton("＋  Новая заметка", self)
        self.add_btn.setObjectName("addLink")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._start_new_order)
        filters.addWidget(self.add_btn)
        a.addLayout(filters)
        a.addSpacing(8)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("listScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_content = QWidget()
        self.list_content.setObjectName("listContent")
        self.list_layout = QVBoxLayout(self.list_content)
        self.list_layout.setContentsMargins(2, 6, 8, 6)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_content)
        a.addWidget(self.scroll, 1)

        root.addWidget(agenda, 1)

        self.composer = self._build_composer()
        root.addWidget(self.composer, 0)

    def _build_composer(self) -> QWidget:
        pane = QWidget(self)
        pane.setObjectName("composerPane")
        outer = QVBoxLayout(pane)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(pane)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("composerInner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(30, 26, 30, 26)
        lay.setSpacing(0)

        self.composer_title = QLabel("Новая заметка", self)
        self.composer_title.setObjectName("composerTitle")
        lay.addWidget(self.composer_title)
        lay.addSpacing(22)

        # пустое состояние
        self.empty_box = QWidget(self)
        eb = QVBoxLayout(self.empty_box)
        eb.setContentsMargins(0, 60, 0, 0)
        eb.setSpacing(8)
        et = QLabel("Ничего не открыто", self)
        et.setObjectName("emptyTitle")
        et.setAlignment(Qt.AlignCenter)
        es = QLabel("Выберите запись слева или начните новую заметку", self)
        es.setObjectName("emptySub")
        es.setAlignment(Qt.AlignCenter)
        es.setWordWrap(True)
        eb.addWidget(et)
        eb.addWidget(es)
        lay.addWidget(self.empty_box)

        # форма
        self.form_box = QWidget(self)
        f = QVBoxLayout(self.form_box)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(0)

        f.addWidget(self._lab("Покупатель"))
        f.addSpacing(7)
        self.customer_edit = QLineEdit(self)
        self.customer_edit.setObjectName("lineIn")
        self.customer_edit.setPlaceholderText("Имя покупателя")
        self._customer_completer = QCompleter(self)
        self._customer_completer.setModel(self._customer_model)
        self._customer_completer.setCaseSensitivity(Qt.CaseInsensitive)
        try:
            self._customer_completer.setFilterMode(Qt.MatchContains)
        except Exception:
            pass
        self._customer_completer.setCompletionMode(QCompleter.PopupCompletion)
        self._customer_completer.setMaxVisibleItems(12)
        self.customer_edit.setCompleter(self._customer_completer)
        f.addWidget(self.customer_edit)
        f.addSpacing(22)

        f.addWidget(self._lab("Когда напомнить"))
        f.addSpacing(7)
        due = QHBoxLayout()
        due.setSpacing(18)
        self._due_buttons = {}
        for key, label in (("today", "Сегодня"), ("tomorrow", "Завтра"), ("after", "Послезавтра"), ("none", "Без срока")):
            b = QPushButton(label, self)
            b.setObjectName("dueOpt")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_due_mode(k))
            self._due_buttons[key] = b
            due.addWidget(b)
        due.addStretch(1)
        due_w = QWidget(self)
        due_w.setLayout(due)
        f.addWidget(due_w)
        f.addSpacing(10)
        d2 = QHBoxLayout()
        d2.setSpacing(10)
        dl = QLabel("или дата:", self)
        dl.setObjectName("fieldLab")
        d2.addWidget(dl)
        self.date_edit = QDateEdit(self)
        self.date_edit.setObjectName("dateIn")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setFixedWidth(130)
        self.date_edit.dateChanged.connect(self._on_date_changed)
        d2.addWidget(self.date_edit)
        d2.addStretch(1)
        d2_w = QWidget(self)
        d2_w.setLayout(d2)
        f.addWidget(d2_w)
        f.addSpacing(22)

        self.comp_head = QLabel("Состав заказа · Tirika, только чтение", self)
        self.comp_head.setObjectName("compHead")
        f.addWidget(self.comp_head)
        f.addSpacing(7)
        self.comp_box = QLabel("", self)
        self.comp_box.setObjectName("compBox")
        self.comp_box.setWordWrap(True)
        self.comp_box.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addWidget(self.comp_box)
        self.comp_gap = QWidget(self)
        self.comp_gap.setFixedHeight(22)
        f.addWidget(self.comp_gap)

        f.addWidget(self._lab("Заметка"))
        f.addSpacing(7)
        self.note_edit = QPlainTextEdit(self)
        self.note_edit.setObjectName("noteIn")
        self.note_edit.setPlaceholderText("Например: клиент заберёт после обеда, оплата при выдаче")
        self.note_edit.setMinimumHeight(130)
        f.addWidget(self.note_edit)
        f.addSpacing(20)

        foot = QHBoxLayout()
        foot.setSpacing(20)
        self.save_btn = QPushButton("Сохранить", self)
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_current)
        foot.addWidget(self.save_btn)
        self.done_btn = QPushButton("✓ Отметить готово", self)
        self.done_btn.setObjectName("txtAct")
        self.done_btn.setCursor(Qt.PointingHandCursor)
        self.done_btn.clicked.connect(self._toggle_done_current)
        foot.addWidget(self.done_btn)
        foot.addStretch(1)
        self.delete_btn = QPushButton("Удалить", self)
        self.delete_btn.setObjectName("txtDel")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._delete_current)
        foot.addWidget(self.delete_btn)
        f.addLayout(foot)

        lay.addWidget(self.form_box)
        lay.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        pane.setFixedWidth(460)
        return pane

    def _lab(self, text: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setObjectName("fieldLab")
        return lbl

    # --- данные -------------------------------------------------------------

    def on_db_ready(self) -> None:
        self._ensure_reference_data(force=True)
        self.refresh()

    def refresh(self) -> None:
        if self.store is None:
            try:
                self.store = OrdersStore()
            except Exception as exc:
                self._warn(f"Не удалось открыть базу заказов: {exc}")
                return
        self._ensure_reference_data()
        self._load_tirika_orders()
        self._rebuild_entries()
        self._rebuild_list()
        self.main.update_orders_badge()

    def _ensure_reference_data(self, force: bool = False) -> None:
        db = getattr(self.main, "db", None)
        key = (id(db),)
        if not force and key == self._ref_built_for:
            return
        names: list[str] = []
        self._customer_to_id = {}
        if db is not None:
            try:
                for cid, name in db.list_customers():
                    names.append(name)
                    self._customer_to_id.setdefault(name.lower(), cid)
            except Exception:
                pass
        self._customer_model.setStringList(sorted(set(names), key=lambda s: s.lower()))
        self._ref_built_for = key

    def _load_tirika_orders(self) -> None:
        self._tirika_orders = []
        self.order_customer = None
        db = getattr(self.main, "db", None)
        if db is None:
            return
        try:
            configured = getattr(self.main.app_settings, "order_customer_name", "") or ""
            self.order_customer = db.find_order_customer(configured)
            if self.order_customer is not None:
                cid, _ = self.order_customer
                self._tirika_orders = db.list_customer_orders(cid, only_open=True, limit=300)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Заказы Tirika: не удалось прочитать ({exc}).")

    def _rebuild_entries(self) -> None:
        entries: list[_Entry] = []
        for rem in self.store.list_reminders(include_done=True):
            entries.append(
                _Entry("manual", rem.id, rem.customer or "Без имени", rem.note,
                       _parse_iso(rem.due_date), rem.status, rem.amount, 0.0, rem)
            )
        meta_map = self.store.get_meta_map()
        for order in self._tirika_orders:
            meta = meta_map.get(order.waybill_id)
            status = meta.status if meta else STATUS_ACTIVE
            if status == STATUS_HIDDEN:
                continue
            due = _parse_iso(meta.reminder_date) if meta and meta.reminder_date else None
            if due is None:
                due = order.reserve_until.date() if order.reserve_until else None
            customer = order.comment.strip() or order.number.strip() or "Заказ покупателя"
            note = (meta.note if meta else "") or (
                order.display or ", ".join((it.product_code or it.name) for it in order.items[:3])
            )
            entries.append(
                _Entry("tirika", order.waybill_id, customer, note, due,
                       status if status in (STATUS_ACTIVE, STATUS_DONE) else STATUS_ACTIVE,
                       order.cost, order.paid, order)
            )
        self._entries = entries

    # --- фильтры/счётчики ---------------------------------------------------

    def _counts(self) -> dict:
        return {
            "active": sum(1 for e in self._entries if e.status == STATUS_ACTIVE and not e.is_overdue),
            "today": sum(1 for e in self._entries if e.is_today),
            "overdue": sum(1 for e in self._entries if e.is_overdue),
            "all": len(self._entries),
            "done": sum(1 for e in self._entries if e.status == STATUS_DONE),
        }

    def _entry_matches_filter(self, e: _Entry) -> bool:
        f = self._filter_value
        if f == "all":
            return True
        if f == "done":
            return e.status == STATUS_DONE
        if f == "today":
            return e.is_today
        if f == "overdue":
            return e.is_overdue
        return e.status == STATUS_ACTIVE

    def _passes_search(self, e: _Entry) -> bool:
        q = self.search_edit.text().strip().lower()
        if not q:
            return True
        return q in " ".join([e.customer, e.note]).lower()

    def _set_filter(self, value: str) -> None:
        self._filter_value = value
        for k, b in self._filter_buttons.items():
            b.setChecked(k == value)
        self._rebuild_list()

    # --- список -------------------------------------------------------------

    def _clear_list(self) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._row_widgets = []

    def _rebuild_list(self) -> None:
        prev = (self._current.kind, self._current.id) if self._current else None
        counts = self._counts()
        labels = {"active": "Активные", "today": "Сегодня", "overdue": "Просрочено", "all": "Все", "done": "Готово"}
        for k, b in self._filter_buttons.items():
            b.setText(f"{labels[k]}  {counts.get(k, 0)}")
            # фиксируем ширину по тексту, чтобы счётчик/буквы не срезались
            try:
                b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + 14)
            except Exception:
                pass

        self._clear_list()
        visible = [e for e in self._entries if self._entry_matches_filter(e) and self._passes_search(e)]
        orders = sorted([e for e in visible if e.kind == "tirika"], key=lambda e: (e.rank(), e.due or date.max))
        notes = sorted([e for e in visible if e.kind == "manual"], key=lambda e: (e.rank(), e.due or date.max))

        at = 0
        if not visible:
            empty = QLabel("Ничего не найдено", self)
            empty.setObjectName("emptyList")
            empty.setAlignment(Qt.AlignCenter)
            empty.setContentsMargins(0, 48, 0, 48)
            self.list_layout.insertWidget(at, empty)
            at += 1
        for gtitle, items in (("Заказы", orders), ("Заметки и задачи", notes)):
            if not items:
                continue
            self.list_layout.insertWidget(at, self._group_header(gtitle, len(items)))
            at += 1
            for e in items:
                row = self._make_row(e)
                self.list_layout.insertWidget(at, row)
                at += 1
                self._row_widgets.append(row)

        if prev is not None:
            for r in self._row_widgets:
                if (r.entry.kind, r.entry.id) == prev:
                    self._apply_row_selection(r.entry)
                    break

    def _group_header(self, title: str, count: int) -> QWidget:
        w = QWidget(self)
        w.setObjectName("agendaSection")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 22, 2, 4)
        v.setSpacing(9)
        line = QHBoxLayout()
        line.setSpacing(9)
        t = QLabel(title, self)
        t.setObjectName("groupTitle")
        n = QLabel(str(count), self)
        n.setObjectName("emptySub")
        line.addWidget(t)
        line.addWidget(n)
        line.addStretch(1)
        v.addLayout(line)
        rule = QFrame(self)
        rule.setObjectName("groupRule")
        v.addWidget(rule)
        return w

    def _make_row(self, e: _Entry) -> _Row:
        tone = e.tone()
        done = e.status == STATUS_DONE
        row = _Row(e, self)
        row.setObjectName("row")
        row.setProperty("selected", "false")
        row.setCursor(Qt.PointingHandCursor)
        row.clicked.connect(self._on_row_clicked)
        h = QHBoxLayout(row)
        h.setContentsMargins(14, 12, 12, 12)
        h.setSpacing(13)

        dot = QLabel("", self)
        dot.setObjectName("dot")
        dot.setProperty("tone", tone)
        dwrap = QVBoxLayout()
        dwrap.setContentsMargins(0, 6, 0, 0)
        dwrap.addWidget(dot)
        dwrap.addStretch(1)
        h.addLayout(dwrap)

        body = QVBoxLayout()
        body.setSpacing(4)
        name = QLabel(self._elide(e.customer, 44), self)
        name.setObjectName("rowNameDone" if done else "rowName")
        body.addWidget(name)
        note = QLabel(self._elide(e.note or "—", 76), self)
        note.setObjectName("rowNoteDone" if done else "rowNote")
        note.setToolTip(e.note)
        body.addWidget(note)
        if e.kind == "tirika" and e.amount:
            sub = QHBoxLayout()
            sub.setSpacing(12)
            am = QLabel(_fmt_amount(e.amount), self)
            am.setObjectName("rowAmount")
            sub.addWidget(am)
            ptext, pkind = e.pay_state()
            if ptext:
                pay = QLabel("● " + ptext, self)
                pay.setObjectName("rowPay")
                pay.setProperty("pay", pkind)
                sub.addWidget(pay)
            sub.addStretch(1)
            sw = QWidget(self)
            sw.setLayout(sub)
            body.addWidget(sw)
        h.addLayout(body, 1)

        when = QLabel(_fmt_when(e.due, done), self)
        when.setObjectName("rowWhen")
        when.setProperty("tone", tone)
        when.setAlignment(Qt.AlignRight | Qt.AlignTop)
        wwrap = QVBoxLayout()
        wwrap.setContentsMargins(0, 2, 0, 0)
        wwrap.addWidget(when)
        wwrap.addStretch(1)
        h.addLayout(wwrap)

        check = QPushButton("✓", self)
        check.setObjectName("doCheck")
        check.setProperty("done", "true" if done else "false")
        check.setCursor(Qt.PointingHandCursor)
        check.setToolTip("Отметить готово")
        check.clicked.connect(lambda _=False, en=e: self._toggle_done_entry(en))
        cwrap = QVBoxLayout()
        cwrap.addStretch(1)
        cwrap.addWidget(check)
        cwrap.addStretch(1)
        h.addLayout(cwrap)
        return row

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        text = (text or "").replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _apply_row_selection(self, entry: _Entry | None) -> None:
        for r in self._row_widgets:
            sel = entry is not None and r.entry.kind == entry.kind and r.entry.id == entry.id
            r.setProperty("selected", "true" if sel else "false")
            r.style().unpolish(r)
            r.style().polish(r)

    # --- выбор и режимы -----------------------------------------------------

    def _on_row_clicked(self, entry: _Entry) -> None:
        self._current = entry
        self._apply_row_selection(entry)
        if entry.kind == "manual":
            self._show_manual_detail(entry.obj)
        else:
            self._show_tirika_detail(entry.obj, entry)

    def _set_form_visible(self, show_form: bool) -> None:
        self.empty_box.setVisible(not show_form)
        self.form_box.setVisible(show_form)

    def _start_new_order(self) -> None:
        self._mode = "new"
        self._current = None
        self._apply_row_selection(None)
        self._set_form_visible(True)
        self.composer_title.setText("Новая заметка")
        self.customer_edit.setReadOnly(False)
        self.customer_edit.clear()
        self.note_edit.setReadOnly(False)
        self.note_edit.clear()
        self._set_comp_visible(False)
        self._set_due_mode("today")
        self.save_btn.setEnabled(True)
        self.save_btn.setText("Сохранить")
        self.done_btn.setVisible(False)
        self.delete_btn.setVisible(False)
        self.customer_edit.setFocus()

    def _show_empty_detail(self) -> None:
        self._mode = "empty"
        self.composer_title.setText("Заказы и напоминания")
        self._set_form_visible(False)

    def _show_manual_detail(self, rem: Reminder) -> None:
        self._mode = "manual"
        self._set_form_visible(True)
        self.composer_title.setText(rem.customer or "Заметка")
        self.customer_edit.setReadOnly(False)
        self.customer_edit.setText(rem.customer)
        self.note_edit.setReadOnly(False)
        self.note_edit.setPlainText(rem.note)
        self._set_comp_visible(False)
        self._apply_due_to_widget(_parse_iso(rem.due_date))
        self.save_btn.setEnabled(True)
        self.save_btn.setText("Сохранить")
        self.done_btn.setVisible(True)
        self.done_btn.setText("Вернуть в работу" if rem.status == STATUS_DONE else "✓ Отметить готово")
        self.delete_btn.setVisible(True)
        self.delete_btn.setText("Удалить")

    def _show_tirika_detail(self, order: TirikaOrder, entry: _Entry) -> None:
        self._mode = "tirika"
        self._set_form_visible(True)
        self.composer_title.setText(f"Заказ · {entry.customer}")
        self.customer_edit.setReadOnly(True)
        self.customer_edit.setText(order.comment or order.number or "Заказ покупателя")
        self._set_comp_visible(True)
        self.comp_box.setText(self._format_comp(order))
        self.note_edit.setReadOnly(False)
        self.note_edit.setPlainText(entry.note if (order.display != entry.note) else "")
        self._apply_due_to_widget(entry.due)
        self.save_btn.setEnabled(True)
        self.save_btn.setText("Сохранить")
        self.done_btn.setVisible(True)
        self.done_btn.setText("Вернуть в работу" if entry.status == STATUS_DONE else "✓ Отметить готово")
        self.delete_btn.setVisible(True)
        self.delete_btn.setText("Скрыть")

    def _format_comp(self, order: TirikaOrder) -> str:
        lines = []
        for it in order.items:
            qty = int(it.quantity) if float(it.quantity).is_integer() else it.quantity
            code = f"[{it.product_code}] " if it.product_code else ""
            lines.append(f"{code}{it.name}   ×{qty}   {_fmt_amount(it.price)}")
        lines.append("")
        total = _fmt_amount(order.cost)
        paid = _fmt_amount(order.paid) or "0 ₽"
        state = "оплачено полностью" if order.is_paid else ("предоплата" if order.paid > 0 else "не оплачено")
        lines.append(f"Итого: {total}")
        lines.append(f"Оплачено: {paid}  ·  {state}")
        return "\n".join(lines)

    def _set_comp_visible(self, visible: bool) -> None:
        self.comp_head.setVisible(visible)
        self.comp_box.setVisible(visible)
        self.comp_gap.setVisible(visible)

    # --- срок ---------------------------------------------------------------

    def _set_due_mode(self, mode: str) -> None:
        self._due_mode = mode
        for k, b in self._due_buttons.items():
            b.setChecked(k == mode)
        if mode == "today":
            self._set_date_silent(QDate.currentDate())
        elif mode == "tomorrow":
            self._set_date_silent(QDate.currentDate().addDays(1))
        elif mode == "after":
            self._set_date_silent(QDate.currentDate().addDays(2))
        self.date_edit.setEnabled(mode != "none")

    def _set_date_silent(self, qd) -> None:
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(qd)
        self.date_edit.blockSignals(False)

    def _on_date_changed(self, _=None) -> None:
        self._due_mode = "custom"
        for b in self._due_buttons.values():
            b.setChecked(False)

    def _apply_due_to_widget(self, d: date | None) -> None:
        if d is None:
            self._set_due_mode("none")
            return
        today = date.today()
        delta = (d - today).days
        self.date_edit.setEnabled(True)
        self._set_date_silent(QDate(d.year, d.month, d.day))
        mode = {0: "today", 1: "tomorrow", 2: "after"}.get(delta, "custom")
        self._due_mode = mode
        for k, b in self._due_buttons.items():
            b.setChecked(k == mode)

    def _current_due_iso(self) -> str:
        if self._due_mode == "none":
            return ""
        qd = self.date_edit.date()
        return f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"

    # --- сохранение/действия ------------------------------------------------

    def _save_current(self) -> None:
        if self.store is None:
            return
        if self._mode in ("new", "manual"):
            self._save_manual()
        elif self._mode == "tirika":
            self._save_tirika_meta()

    def _resolve_customer_id(self, customer: str) -> int | None:
        return self._customer_to_id.get(customer.strip().lower())

    def _save_manual(self) -> None:
        customer = self.customer_edit.text().strip()
        note = self.note_edit.toPlainText().strip()
        if not customer and not note:
            self._warn("Заполните покупателя или заметку.")
            return
        due_iso = self._current_due_iso()
        cid = self._resolve_customer_id(customer)
        if self._mode == "new":
            new_id = self.store.add_reminder(customer=customer, note=note, due_date=due_iso, customer_id=cid)
            self._log(f"Создан заказ #{new_id}: {customer or '—'}")
            self.refresh()
            self._select_entry("manual", new_id)
        else:
            rid = self._current.id
            self.store.update_reminder(rid, customer=customer, note=note, due_date=due_iso,
                                       customer_id=cid, set_customer_id=True)
            self._log(f"Заказ #{rid} сохранён.")
            self.refresh()
            self._select_entry("manual", rid)

    def _save_tirika_meta(self) -> None:
        if self._current is None:
            return
        wb = self._current.id
        self.store.upsert_meta(wb, note=self.note_edit.toPlainText().strip(), reminder_date=self._current_due_iso())
        self._log(f"Заметка к заказу Tirika #{wb} сохранена.")
        self.refresh()
        self._select_entry("tirika", wb)

    def _toggle_done_current(self) -> None:
        if self._current is not None:
            self._toggle_done_entry(self._current)

    def _toggle_done_entry(self, e: _Entry) -> None:
        if self.store is None:
            return
        new_status = STATUS_ACTIVE if e.status == STATUS_DONE else STATUS_DONE
        if e.kind == "manual":
            self.store.set_reminder_status(e.id, new_status)
        else:
            self.store.upsert_meta(e.id, status=new_status)
        self.refresh()
        if self._current is not None and self._current.kind == e.kind and self._current.id == e.id:
            self._select_entry(e.kind, e.id)

    def _delete_current(self) -> None:
        if self._current is None or self.store is None:
            return
        e = self._current
        if e.kind == "manual":
            if QMessageBox.question(self, "Удалить заказ",
                                    f"Удалить заметку «{e.customer}»? Действие необратимо.") != QMessageBox.Yes:
                return
            self.store.delete_reminder(e.id)
            self._log(f"Заказ #{e.id} удалён.")
        else:
            self.store.upsert_meta(e.id, status=STATUS_HIDDEN)
            self._log(f"Заказ Tirika #{e.id} скрыт.")
        self._current = None
        self.refresh()
        self._show_empty_detail()

    def _select_entry(self, kind: str, eid: int) -> None:
        for e in self._entries:
            if e.kind == kind and e.id == eid:
                self._on_row_clicked(e)
                return

    # --- сводка --------------------------------------------------------------

    def compute_summary(self) -> dict:
        return {
            "today": sum(1 for e in self._entries if e.is_today),
            "overdue": sum(1 for e in self._entries if e.is_overdue),
            "tirika_open": sum(1 for e in self._entries if e.kind == "tirika" and e.status == STATUS_ACTIVE),
            "active": sum(1 for e in self._entries if e.status == STATUS_ACTIVE),
        }

    def badge_count(self) -> int:
        s = self.compute_summary()
        return s["today"] + s["overdue"]

    # --- лог ----------------------------------------------------------------

    def _log(self, text: str) -> None:
        try:
            self.main._log(text)
        except Exception:
            pass

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "Заказы", text)
