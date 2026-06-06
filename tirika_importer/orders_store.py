"""Локальное хранилище заказов и напоминаний продавца.

Отдельная база SQLite (per-PC), не связана с базой Tirika и ничего в ней
не меняет. Хранит:
  * ручные заказы/напоминания (покупатель, дата, заметка, артикул, товар);
  * пользовательские метаданные для заказов, прочитанных из Tirika
    (заметка, дата напоминания, статус: активен/выполнен/скрыт).

Файл по умолчанию: %APPDATA%/Dazzle/orders.db (рядом с settings.json).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


STATUS_ACTIVE = "active"
STATUS_DONE = "done"
STATUS_HIDDEN = "hidden"

SOURCE_MANUAL = "manual"
SOURCE_TIRIKA = "tirika"


def orders_db_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Dazzle" / "orders.db"
    return Path.home() / ".dazzle" / "orders.db"


@dataclass
class Reminder:
    id: int
    customer: str
    note: str
    article: str
    good_id: int | None
    good_name: str
    due_date: str  # ISO yyyy-mm-dd или ""
    status: str  # active | done
    created_at: str
    done_at: str
    amount: float
    customer_id: int | None = None


@dataclass
class TirikaOrderMeta:
    waybill_id: int
    note: str
    reminder_date: str  # ISO yyyy-mm-dd или ""
    status: str  # active | done | hidden
    updated_at: str


class OrdersStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else orders_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    article TEXT NOT NULL DEFAULT '',
                    good_id INTEGER,
                    customer_id INTEGER,
                    good_name TEXT NOT NULL DEFAULT '',
                    due_date TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT '',
                    done_at TEXT NOT NULL DEFAULT '',
                    amount REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tirika_order_meta (
                    waybill_id INTEGER PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    reminder_date TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            cols = {row[1] for row in conn.execute("PRAGMA table_info(reminders)").fetchall()}
            if "customer_id" not in cols:
                conn.execute("ALTER TABLE reminders ADD COLUMN customer_id INTEGER")
            conn.commit()

    # --- Ручные напоминания -------------------------------------------------

    def list_reminders(self, *, include_done: bool = True) -> list[Reminder]:
        sql = "SELECT * FROM reminders"
        if not include_done:
            sql += " WHERE status != 'done'"
        sql += " ORDER BY (due_date = '') ASC, due_date ASC, id DESC"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def get_reminder(self, reminder_id: int) -> Reminder | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (int(reminder_id),)
            ).fetchone()
        return self._row_to_reminder(row) if row else None

    def add_reminder(
        self,
        *,
        customer: str,
        note: str,
        article: str = "",
        good_id: int | None = None,
        good_name: str = "",
        due_date: str = "",
        amount: float = 0.0,
        customer_id: int | None = None,
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reminders
                    (customer, customer_id, note, article, good_id, good_name, due_date,
                     status, created_at, done_at, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
                """,
                (
                    customer.strip(),
                    int(customer_id) if customer_id else None,
                    note.strip(),
                    article.strip(),
                    int(good_id) if good_id else None,
                    good_name.strip(),
                    due_date.strip(),
                    STATUS_ACTIVE,
                    now,
                    float(amount or 0.0),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_reminder(
        self,
        reminder_id: int,
        *,
        customer: str | None = None,
        note: str | None = None,
        article: str | None = None,
        good_id: int | None = None,
        good_name: str | None = None,
        due_date: str | None = None,
        amount: float | None = None,
        clear_good: bool = False,
        customer_id: int | None = None,
        set_customer_id: bool = False,
    ) -> None:
        fields: dict[str, object] = {}
        if customer is not None:
            fields["customer"] = customer.strip()
        if note is not None:
            fields["note"] = note.strip()
        if article is not None:
            fields["article"] = article.strip()
        if good_name is not None:
            fields["good_name"] = good_name.strip()
        if due_date is not None:
            fields["due_date"] = due_date.strip()
        if amount is not None:
            fields["amount"] = float(amount or 0.0)
        if clear_good:
            fields["good_id"] = None
        elif good_id is not None:
            fields["good_id"] = int(good_id)
        if set_customer_id:
            fields["customer_id"] = int(customer_id) if customer_id else None
        if not fields:
            return
        set_sql = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [int(reminder_id)]
        with self._connect() as conn:
            conn.execute(f"UPDATE reminders SET {set_sql} WHERE id = ?", params)
            conn.commit()

    def set_reminder_status(self, reminder_id: int, status: str) -> None:
        done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == STATUS_DONE else ""
        with self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET status = ?, done_at = ? WHERE id = ?",
                (status, done_at, int(reminder_id)),
            )
            conn.commit()

    def delete_reminder(self, reminder_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reminders WHERE id = ?", (int(reminder_id),))
            conn.commit()

    # --- Метаданные заказов из Tirika --------------------------------------

    def get_meta_map(self) -> dict[int, TirikaOrderMeta]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tirika_order_meta").fetchall()
        out: dict[int, TirikaOrderMeta] = {}
        for r in rows:
            out[int(r["waybill_id"])] = TirikaOrderMeta(
                waybill_id=int(r["waybill_id"]),
                note=r["note"] or "",
                reminder_date=r["reminder_date"] or "",
                status=r["status"] or STATUS_ACTIVE,
                updated_at=r["updated_at"] or "",
            )
        return out

    def upsert_meta(
        self,
        waybill_id: int,
        *,
        note: str | None = None,
        reminder_date: str | None = None,
        status: str | None = None,
    ) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT note, reminder_date, status FROM tirika_order_meta WHERE waybill_id = ?",
                (int(waybill_id),),
            ).fetchone()
            new_note = note if note is not None else (row["note"] if row else "")
            new_date = (
                reminder_date if reminder_date is not None else (row["reminder_date"] if row else "")
            )
            new_status = status if status is not None else (row["status"] if row else STATUS_ACTIVE)
            params = (
                (new_note or "").strip(),
                (new_date or "").strip(),
                new_status,
                now,
                int(waybill_id),
            )
            if row is None:
                conn.execute(
                    """
                    INSERT INTO tirika_order_meta
                        (note, reminder_date, status, updated_at, waybill_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    params,
                )
            else:
                conn.execute(
                    """
                    UPDATE tirika_order_meta
                    SET note = ?, reminder_date = ?, status = ?, updated_at = ?
                    WHERE waybill_id = ?
                    """,
                    params,
                )
            conn.commit()

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> Reminder:
        good_id = row["good_id"]
        try:
            cust_id = row["customer_id"]
        except (IndexError, KeyError):
            cust_id = None
        return Reminder(
            id=int(row["id"]),
            customer_id=int(cust_id) if cust_id is not None else None,
            customer=row["customer"] or "",
            note=row["note"] or "",
            article=row["article"] or "",
            good_id=int(good_id) if good_id is not None else None,
            good_name=row["good_name"] or "",
            due_date=row["due_date"] or "",
            status=row["status"] or STATUS_ACTIVE,
            created_at=row["created_at"] or "",
            done_at=row["done_at"] or "",
            amount=float(row["amount"] or 0.0),
        )
