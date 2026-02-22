from __future__ import annotations

import errno
import math
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import ImportOptions, ImportResult, InvoiceLine, ParsedInvoice

PURCHASE_WAYBILL_RECORD_TYPE = 1
WAYBILL_OPERATION_OBJECT_TYPE = 3
WAYBILL_OPERATION_TYPE_CREATE = 1


class TirikaDBError(RuntimeError):
    pass


class ImportValidationError(TirikaDBError):
    pass


@dataclass(slots=True)
class GoodRecord:
    good_id: int
    product_code: str
    name: str
    manufacturer: str
    buy_price: float
    sell_price: float
    tax_mode: int
    supplier_id: int
    remainder: float = 0.0
    cross_codes: list[str] = field(default_factory=list)
    barcodes: list[str] = field(default_factory=list)


class TirikaDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if not self.db_path.exists():
            raise TirikaDBError(f"Файл базы не найден: {self.db_path}")

    def create_backup(self, target_dir: Path | None = None) -> Path:
        backup_dir = target_dir or (self.db_path.parent / "import_backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{self.db_path.stem}_{ts}.db.bak"
        shutil.copy2(self.db_path, backup_path)
        return backup_path

    def list_suppliers(self) -> list[tuple[int, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name
                FROM suppliers
                WHERE is_deleted = 0
                ORDER BY name, id
                """
            ).fetchall()
        return [(int(row[0]), decode_db_text(row[1])) for row in rows]

    def list_users(self) -> list[tuple[int, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name
                FROM users
                WHERE is_deleted = 0
                ORDER BY id
                """
            ).fetchall()
        return [(int(row[0]), decode_db_text(row[1])) for row in rows]

    def list_shops(self) -> list[tuple[int, str]]:
        shops: list[tuple[int, str]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT settings_name, settings_value
                FROM settings
                WHERE settings_name LIKE 'SHOP %'
                ORDER BY settings_name
                """
            ).fetchall()
        for row in rows:
            key = decode_db_text(row[0]).strip()
            value = decode_db_text(row[1]).strip()
            if key.upper() == "SHOP COUNT":
                continue
            if "," in value:
                id_part, name_part = value.split(",", 1)
            else:
                id_part, name_part = value, value
            try:
                shop_id = int(id_part.strip())
            except ValueError:
                continue
            name = name_part.strip() or f"shop_{shop_id}"
            shops.append((shop_id, name))

        if not shops:
            shops.append((0, "Основной склад"))
        return shops

    def load_goods_catalog(self, shop_id: int) -> dict[int, GoodRecord]:
        catalog: dict[int, GoodRecord] = {}
        with self._connect() as conn:
            good_rows = conn.execute(
                """
                SELECT id, product_code, name, manufacturer, buy_price, price, tax_mode, supplier_id
                FROM goods
                WHERE is_deleted = 0
                """
            ).fetchall()
            for row in good_rows:
                gid = int(row[0])
                catalog[gid] = GoodRecord(
                    good_id=gid,
                    product_code=decode_db_text(row[1]),
                    name=decode_db_text(row[2]),
                    manufacturer=decode_db_text(row[3]),
                    buy_price=float(row[4] or 0.0),
                    sell_price=float(row[5] or 0.0),
                    tax_mode=int(row[6] or 0),
                    supplier_id=int(row[7] or 0),
                )

            remainder_rows = conn.execute(
                """
                SELECT good_id, remainder
                FROM remainders
                WHERE shop_id = ?
                """,
                (shop_id,),
            ).fetchall()
            for row in remainder_rows:
                gid = int(row[0])
                if gid in catalog:
                    catalog[gid].remainder = float(row[1] or 0.0)

            cross_rows = conn.execute("SELECT good_id, cross_code FROM cross_codes").fetchall()
            for row in cross_rows:
                gid = int(row[0])
                if gid in catalog:
                    val = decode_db_text(row[1]).strip()
                    if val:
                        catalog[gid].cross_codes.append(val)

            barcode_rows = conn.execute("SELECT good_id, barcode FROM barcodes").fetchall()
            for row in barcode_rows:
                gid = int(row[0])
                if gid in catalog:
                    val = decode_db_text(row[1]).strip()
                    if val:
                        catalog[gid].barcodes.append(val)

        return catalog

    def import_invoice(self, invoice: ParsedInvoice, options: ImportOptions) -> ImportResult:
        warnings: list[str] = []
        backup_path: Path | None = None
        if options.backup_before_import:
            try:
                backup_path = self.create_backup()
            except OSError as exc:
                if not self._is_access_denied_error(exc):
                    raise TirikaDBError(f"Не удалось создать backup: {exc}") from exc

                fallback_dir = self._fallback_backup_dir()
                try:
                    backup_path = self.create_backup(fallback_dir)
                    warnings.append(
                        "Нет доступа к папке базы для backup. "
                        f"Backup сохранен в: {backup_path.parent}"
                    )
                except OSError as fallback_exc:
                    raise TirikaDBError(
                        "Не удалось создать backup ни рядом с базой, ни в пользовательской папке. "
                        "Снимите галочку backup перед импортом или запустите программу с правами администратора."
                    ) from fallback_exc

        lines_to_import: list[InvoiceLine] = []
        skipped_lines = 0
        created_goods = 0

        for line in invoice.lines:
            if line.warning:
                warnings.append(f"Строка {line.line_no}: {line.warning}")
            if line.action == "skip":
                skipped_lines += 1
                continue
            line.article = normalize_article(line.article)
            line.matched_product_code = normalize_article(line.matched_product_code or line.article)
            line.matched_name = normalize_text_field(line.matched_name or line.name, max_len=120)
            if line.sell_price is None:
                line.sell_price = calculate_suggested_sell_price(line.price)
            if line.quantity <= 0:
                warnings.append(f"Строка {line.line_no}: количество <= 0, пропущено.")
                skipped_lines += 1
                continue
            if line.price < 0:
                warnings.append(f"Строка {line.line_no}: цена < 0, пропущено.")
                skipped_lines += 1
                continue
            if (line.sell_price or 0.0) < 0:
                warnings.append(f"Строка {line.line_no}: продажная цена < 0, пропущено.")
                skipped_lines += 1
                continue
            if line.matched_good_id is None and not (
                options.create_missing_goods and line.action == "create"
            ):
                warnings.append(
                    f"Строка {line.line_no}: товар не сопоставлен и не отмечен к созданию."
                )
                skipped_lines += 1
                continue
            lines_to_import.append(line)

        if not lines_to_import:
            raise ImportValidationError("Нет валидных строк для импорта.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            max_waybill_before = self._max_id(cur, "waybills")
            max_waybill_item_before = self._max_id(cur, "waybill_items")
            max_payment_before = self._max_id(cur, "payments")
            max_operation_before = self._max_id(cur, "operations")

            waybill_date = options.waybill_date or invoice.invoice_date or datetime.now()
            waybill_ts = int(waybill_date.timestamp())
            waybill_id = self._next_id(cur, "waybills")
            waybill_item_id = self._next_id(cur, "waybill_items")
            payment_id = self._next_id(cur, "payments")
            operation_id = self._next_id(cur, "operations")
            good_id_seq = self._next_id(cur, "goods")
            dazzle_group_id: int | None = None

            item_rows: list[tuple[int, InvoiceLine, int, int]] = []
            created_good_ids: set[int] = set()
            for line in lines_to_import:
                good_id = line.matched_good_id
                if good_id is None and line.action == "create":
                    if dazzle_group_id is None:
                        dazzle_group_id = self._ensure_dazzle_group(cur)
                    good_id = good_id_seq
                    self._insert_new_good(
                        cur=cur,
                        new_good_id=good_id,
                        group_id=dazzle_group_id,
                        supplier_id=options.supplier_id,
                        line=line,
                        prefix_with_order=options.prefix_new_goods_with_order,
                    )
                    created_good_ids.add(good_id)
                    good_id_seq += 1
                    created_goods += 1
                    line.matched_good_id = good_id

                if good_id is None:
                    skipped_lines += 1
                    warnings.append(f"Строка {line.line_no}: не удалось определить good_id, пропущено.")
                    continue

                tax_mode = self._get_good_tax_mode(cur, good_id, default=line.matched_tax_mode)
                item_rows.append((waybill_item_id, line, good_id, tax_mode))
                waybill_item_id += 1

            if not item_rows:
                raise ImportValidationError("После проверки не осталось строк для записи.")

            total_cost = round(
                sum(line.total if line.total > 0 else line.quantity * line.price for _, line, _, _ in item_rows),
                2,
            )
            paid = total_cost if options.auto_pay else 0.0
            display_string = self._build_display_string(item_rows)
            waybill_number = invoice.invoice_number.strip()[:20]

            cur.execute(
                """
                INSERT INTO waybills (
                    id, is_deleted, is_replicated, shop_id, waybill_date, record_type, payment_type,
                    is_reserve, reserve_until, contractor_id, user_id, waybill_number,
                    cost, paid, display_string, comment, customer_balls, referer_balls,
                    currency_id, is_archived, discount_id, discount, is_published,
                    foreign_id, flags, repair_status, customer_balls_spent, referer_balls_spent
                )
                VALUES (
                    ?, 0, 0, ?, ?, ?, ?, 0, 0, ?, ?, CAST(? AS TEXT),
                    ?, ?, CAST(? AS TEXT), CAST(? AS TEXT), 0, 0,
                    0, 0, -1, 0, 0, -1, 0, -1, 0, 0
                )
                """,
                (
                    waybill_id,
                    options.shop_id,
                    waybill_ts,
                    PURCHASE_WAYBILL_RECORD_TYPE,
                    options.payment_type,
                    options.supplier_id,
                    options.user_id,
                    encode_db_text(waybill_number),
                    total_cost,
                    paid,
                    encode_db_text(display_string),
                    encode_db_text(""),
                ),
            )

            for item_id, line, good_id, tax_mode in item_rows:
                qty = round(line.quantity, 6)
                price = round(line.price, 2)
                note = normalize_text_field(line.note or "", max_len=250)
                cur.execute(
                    """
                    INSERT INTO waybill_items (
                        id, is_deleted, is_replicated, waybill_id, goods_id, size_id,
                        quantity, price, buy_price, vat, discount, set_id, bonus, sold,
                        buy_cost, buy_currency_id, comment, certificate_id, foreign_id, unit_id, tax_mode
                    )
                    VALUES (
                        ?, 0, 0, ?, ?, -1,
                        ?, ?, ?, 0, 0, -1, 0, 0,
                        NULL, 0, CAST(? AS TEXT), -1, -1, -1, ?
                    )
                    """,
                    (
                        item_id,
                        waybill_id,
                        good_id,
                        qty,
                        price,
                        price,
                        encode_db_text(note),
                        tax_mode,
                    ),
                )

                self._upsert_remainders(cur, shop_id=options.shop_id, good_id=good_id, quantity=qty)

                if good_id in created_good_ids:
                    continue

                sell_price = round(
                    line.sell_price
                    if line.sell_price is not None
                    else calculate_suggested_sell_price(line.price),
                    2,
                )
                force_sell_update = bool(line.raw_data.get("_force_update_sell_price", False))
                set_clauses: list[str] = []
                params: list[object] = []

                if options.update_existing_buy_price:
                    set_clauses.append("buy_price = ?")
                    params.append(price)
                    set_clauses.append("buy_currency_id = 0")

                if options.update_existing_supplier:
                    set_clauses.append("supplier_id = ?")
                    params.append(options.supplier_id)

                if options.update_existing_sell_price or force_sell_update:
                    set_clauses.append("price = ?")
                    params.append(sell_price)
                    set_clauses.append("currency_id = 0")

                if options.update_existing_name:
                    name = normalize_text_field(line.matched_name or line.name, max_len=120)
                    set_clauses.append("name = CAST(? AS TEXT)")
                    params.append(encode_db_text(name))

                if options.update_existing_manufacturer:
                    manufacturer_raw = str(line.raw_data.get("manufacturer", "") or "").strip()
                    manufacturer = normalize_text_field(manufacturer_raw, max_len=60)
                    if manufacturer:
                        set_clauses.append("manufacturer = CAST(? AS TEXT)")
                        params.append(encode_db_text(manufacturer))

                if set_clauses:
                    params.append(good_id)
                    cur.execute(
                        f"""
                        UPDATE goods
                        SET {", ".join(set_clauses)}
                        WHERE id = ?
                        """,
                        tuple(params),
                    )

            if options.auto_pay:
                cur.execute(
                    """
                    INSERT INTO payments (
                        id, waybill_id, payment_date, payment_type, is_deleted, is_replicated,
                        cost, comment, certificate_id, register_session, register_cheque,
                        register_serial, payment_order
                    )
                    VALUES (
                        ?, ?, ?, ?, 0, 0,
                        ?, CAST(? AS TEXT), -1, 0, 0,
                        CAST(? AS TEXT), 0
                    )
                    """,
                    (
                        payment_id,
                        waybill_id,
                        waybill_ts,
                        options.payment_type,
                        total_cost,
                        encode_db_text(""),
                        encode_db_text(""),
                    ),
                )

            cur.execute(
                """
                INSERT INTO operations (
                    id, is_replicated, user_id, object_type, operation_type, operation_date,
                    object_id, object_description, operation_description
                )
                VALUES (?, 0, ?, ?, ?, ?, ?, CAST(? AS TEXT), CAST(? AS TEXT))
                """,
                (
                    operation_id,
                    options.user_id,
                    WAYBILL_OPERATION_OBJECT_TYPE,
                    WAYBILL_OPERATION_TYPE_CREATE,
                    waybill_ts,
                    waybill_id,
                    encode_db_text(self._build_operation_description(waybill_date, total_cost)),
                    encode_db_text(f"Импорт накладной: {invoice.file_path.name}"),
                ),
            )

            self._assert_purchase_only_invariants(
                cur=cur,
                max_waybill_before=max_waybill_before,
                max_waybill_item_before=max_waybill_item_before,
                max_payment_before=max_payment_before,
                max_operation_before=max_operation_before,
                waybill_id=waybill_id,
                expected_items=len(item_rows),
                supplier_id=options.supplier_id,
                user_id=options.user_id,
                auto_pay=options.auto_pay,
            )

            if options.dry_run:
                conn.rollback()
                waybill_out: int | None = None
            else:
                conn.commit()
                waybill_out = waybill_id

            return ImportResult(
                success=True,
                dry_run=options.dry_run,
                backup_path=backup_path,
                waybill_id=waybill_out,
                imported_lines=len(item_rows),
                skipped_lines=skipped_lines,
                created_goods=created_goods,
                total_cost=total_cost,
                warnings=warnings,
            )
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if "readonly" in str(exc).lower():
                raise TirikaDBError(
                    "База открыта только для чтения. Запустите программу с правами администратора "
                    "или перенесите базу в папку с правом записи."
                ) from exc
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _insert_new_good(
        self,
        cur: sqlite3.Cursor,
        new_good_id: int,
        group_id: int | None,
        supplier_id: int,
        line: InvoiceLine,
        prefix_with_order: bool,
    ) -> None:
        article = normalize_article(line.matched_product_code or line.article)
        if not article:
            article = f"AUTO{new_good_id}"
        name = normalize_text_field(line.matched_name or line.name or line.article, max_len=120)
        if not name:
            name = f"Товар {new_good_id}"
        if prefix_with_order and not name.upper().startswith("ЗАКАЗ--"):
            name = f"ЗАКАЗ--{name}"
        if len(name) > 120:
            name = name[:120]

        manufacturer = normalize_text_field(str(line.raw_data.get("manufacturer", "") or ""), max_len=60)
        target_group_id = int(group_id) if group_id is not None else -1
        buy_price = round(line.price, 2)
        sell_price = round(
            line.sell_price
            if line.sell_price is not None
            else calculate_suggested_sell_price(line.price),
            2,
        )

        cur.execute(
            """
            INSERT INTO goods (
                id, group_id, is_deleted, is_replicated, is_sized, is_discounted, is_set,
                name, unit_name, manufacturer, product_code, barcode,
                price, price1, price2, price3, buy_price, seller_bonus, vat,
                photo, photo_extention, description, comment, decimal_places,
                good_type, alco_type, alco_amount, currency_id, currency_id1, currency_id2, currency_id3,
                buy_currency_id, price_change_date, is_alco_marked, is_tap_trade, alco_strength,
                is_serial_required, tax_mode, tax_percent, price_advance, price_advance1, price_advance2,
                price_advance3, register_type, is_published, foreign_id, is_publish, is_estore_delivery,
                estore_short_description, estore_long_description, estore_meta_title, estore_meta_description,
                estore_meta_keywords, estore_friendly_url, estore_tags, estore_sort_order, hotkey,
                price_round, unit_code, old_currency_id, old_price, supplier_id, flags, is_archived,
                length, width, height, weight, is_ozon_published, marketplaces_id
            )
            VALUES (
                ?, ?, 0, 0, 0, 1, 0,
                CAST(? AS TEXT), CAST(? AS TEXT), CAST(? AS TEXT), CAST(? AS TEXT), CAST(? AS TEXT),
                ?, 0, 0, 0, ?, 0, 0,
                NULL, CAST(? AS TEXT), CAST(? AS TEXT), CAST(? AS TEXT), 0,
                0, 0, 0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0, 0,
                0, 0, 0, -1, 0, 0,
                NULL, NULL, NULL, NULL,
                NULL, NULL, NULL, 0, 0,
                0, 0, 0, 0, ?, 0, 0,
                0, 0, 0, 0, 0, 0
            )
            """,
            (
                new_good_id,
                target_group_id,
                encode_db_text(name),
                encode_db_text("шт."),
                encode_db_text(manufacturer),
                encode_db_text(article),
                encode_db_text(""),
                sell_price,
                buy_price,
                encode_db_text(""),
                encode_db_text(""),
                encode_db_text(""),
                supplier_id,
            ),
        )
        self._insert_auto_cross_code(
            cur=cur,
            good_id=new_good_id,
            supplier_name=line.source_supplier,
        )

        line.matched_product_code = article
        line.matched_name = name
        line.matched_buy_price = buy_price
        line.sell_price = sell_price
        line.matched_tax_mode = 0

    def _ensure_dazzle_group(self, cur: sqlite3.Cursor) -> int:
        rows = cur.execute(
            """
            SELECT id, name, is_deleted
            FROM good_groups
            """
        ).fetchall()

        for row in rows:
            group_id = int(row[0])
            group_name = decode_db_text(row[1]).strip()
            if group_name.lower() != "dazzle":
                continue

            if int(row[2] or 0) != 0:
                cur.execute(
                    """
                    UPDATE good_groups
                    SET is_deleted = 0,
                        is_replicated = 0,
                        name = CAST(? AS TEXT),
                        full_name = CAST(? AS TEXT),
                        parent_id = -1
                    WHERE id = ?
                    """,
                    (encode_db_text("Dazzle"), encode_db_text("Dazzle"), group_id),
                )
            return group_id

        new_group_id = self._next_id(cur, "good_groups")
        cur.execute(
            """
            INSERT INTO good_groups (
                id, is_deleted, is_replicated, name, comment, parent_id, full_name, section,
                is_published, foreign_id, estore_meta_title, estore_meta_description,
                estore_meta_keywords, estore_friendly_url, estore_sort_order, description
            )
            VALUES (
                ?, 0, 0, CAST(? AS TEXT), CAST(? AS TEXT), -1, CAST(? AS TEXT), 0,
                0, -1, NULL, NULL,
                NULL, NULL, 0, CAST(? AS TEXT)
            )
            """,
            (
                new_group_id,
                encode_db_text("Dazzle"),
                encode_db_text(""),
                encode_db_text("Dazzle"),
                encode_db_text(""),
            ),
        )
        return new_group_id

    def _insert_auto_cross_code(self, cur: sqlite3.Cursor, good_id: int, supplier_name: str) -> None:
        supplier = normalize_text_field(supplier_name, max_len=80)
        supplier = "-".join(supplier.split()) if supplier else "unknown"
        cross_code = f"Dazzle-auto-made-from-{supplier}"
        cur.execute(
            """
            INSERT INTO cross_codes (good_id, cross_code)
            VALUES (?, CAST(? AS TEXT))
            """,
            (good_id, encode_db_text(cross_code)),
        )

    def _upsert_remainders(self, cur: sqlite3.Cursor, shop_id: int, good_id: int, quantity: float) -> None:
        row = cur.execute(
            """
            SELECT remainder
            FROM remainders
            WHERE shop_id = ? AND good_id = ?
            """,
            (shop_id, good_id),
        ).fetchone()

        if row is None:
            cur.execute(
                """
                INSERT INTO remainders (
                    shop_id, good_id, is_deleted, is_replicated, remainder,
                    reserved, min_amount, expected, is_published, is_ozon_published
                )
                VALUES (?, ?, 0, 0, ?, 0, 0, 0, 0, 0)
                """,
                (shop_id, good_id, quantity),
            )
            return

        cur.execute(
            """
            UPDATE remainders
            SET remainder = COALESCE(remainder, 0) + ?,
                is_deleted = 0,
                is_replicated = 0
            WHERE shop_id = ? AND good_id = ?
            """,
            (quantity, shop_id, good_id),
        )

    def _get_good_tax_mode(self, cur: sqlite3.Cursor, good_id: int, default: int = 0) -> int:
        row = cur.execute("SELECT tax_mode FROM goods WHERE id = ?", (good_id,)).fetchone()
        if row is None:
            return default
        return int(row[0] or default)

    def _build_display_string(self, item_rows: list[tuple[int, InvoiceLine, int, int]]) -> str:
        parts: list[str] = []
        for _, line, _, _ in item_rows[:6]:
            code = line.matched_product_code.strip() or line.article.strip()
            name = line.matched_name.strip() or line.name.strip()
            qty = int(line.quantity) if float(line.quantity).is_integer() else line.quantity
            part = f"[{code}] {name} ({qty})"
            parts.append(part)
        out = ", ".join(parts)
        return out[:120]

    def _build_operation_description(self, waybill_date: datetime, cost: float) -> str:
        return f" от {waybill_date.strftime('%d.%m.%y')} на {_format_amount_ru(cost)}"

    def _next_id(self, cur: sqlite3.Cursor, table: str) -> int:
        row = cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}").fetchone()
        return int(row[0])

    def _max_id(self, cur: sqlite3.Cursor, table: str) -> int:
        row = cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()
        return int(row[0] or 0)

    def _assert_purchase_only_invariants(
        self,
        *,
        cur: sqlite3.Cursor,
        max_waybill_before: int,
        max_waybill_item_before: int,
        max_payment_before: int,
        max_operation_before: int,
        waybill_id: int,
        expected_items: int,
        supplier_id: int,
        user_id: int,
        auto_pay: bool,
    ) -> None:
        waybills = cur.execute(
            """
            SELECT id, record_type, contractor_id, user_id
            FROM waybills
            WHERE id > ?
            ORDER BY id
            """,
            (max_waybill_before,),
        ).fetchall()
        if len(waybills) != 1:
            raise ImportValidationError(
                "Контроль безопасности импорта: создано неожиданное число документов waybill."
            )
        wb_id, wb_record_type, wb_contractor_id, wb_user_id = waybills[0]
        if int(wb_id) != waybill_id:
            raise ImportValidationError(
                "Контроль безопасности импорта: создан не тот документ waybill."
            )
        if int(wb_record_type or 0) != PURCHASE_WAYBILL_RECORD_TYPE:
            raise ImportValidationError(
                "Контроль безопасности импорта: документ имеет недопустимый тип (не закупка)."
            )
        if int(wb_contractor_id or 0) != supplier_id:
            raise ImportValidationError(
                "Контроль безопасности импорта: в документ записан неверный поставщик."
            )
        if int(wb_user_id or 0) != user_id:
            raise ImportValidationError(
                "Контроль безопасности импорта: в документ записан неверный пользователь."
            )

        item_stats = cur.execute(
            """
            SELECT COUNT(*), MIN(waybill_id), MAX(waybill_id)
            FROM waybill_items
            WHERE id > ?
            """,
            (max_waybill_item_before,),
        ).fetchone()
        item_count = int(item_stats[0] or 0)
        item_wb_min = int(item_stats[1] or 0) if item_stats[1] is not None else 0
        item_wb_max = int(item_stats[2] or 0) if item_stats[2] is not None else 0
        if item_count != expected_items:
            raise ImportValidationError(
                "Контроль безопасности импорта: количество строк waybill_items не совпало."
            )
        if item_count > 0 and (item_wb_min != waybill_id or item_wb_max != waybill_id):
            raise ImportValidationError(
                "Контроль безопасности импорта: строки waybill_items привязаны к другому документу."
            )

        payments = cur.execute(
            """
            SELECT id, waybill_id
            FROM payments
            WHERE id > ?
            ORDER BY id
            """,
            (max_payment_before,),
        ).fetchall()
        expected_payment_count = 1 if auto_pay else 0
        if len(payments) != expected_payment_count:
            raise ImportValidationError(
                "Контроль безопасности импорта: создано неожиданное число платежей."
            )
        if payments and int(payments[0][1] or 0) != waybill_id:
            raise ImportValidationError(
                "Контроль безопасности импорта: платеж привязан к другому документу."
            )

        operations = cur.execute(
            """
            SELECT id, object_type, operation_type, object_id
            FROM operations
            WHERE id > ?
            ORDER BY id
            """,
            (max_operation_before,),
        ).fetchall()
        if len(operations) != 1:
            raise ImportValidationError(
                "Контроль безопасности импорта: создано неожиданное число записей operations."
            )
        _, op_object_type, op_type, op_object_id = operations[0]
        if int(op_object_type or 0) != WAYBILL_OPERATION_OBJECT_TYPE:
            raise ImportValidationError(
                "Контроль безопасности импорта: operation записан не в тип waybill."
            )
        if int(op_type or 0) != WAYBILL_OPERATION_TYPE_CREATE:
            raise ImportValidationError(
                "Контроль безопасности импорта: operation_type недопустим для импорта закупки."
            )
        if int(op_object_id or 0) != waybill_id:
            raise ImportValidationError(
                "Контроль безопасности импорта: operation привязан к другому документу."
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.text_factory = bytes
        return conn

    @staticmethod
    def _is_access_denied_error(exc: OSError) -> bool:
        if getattr(exc, "winerror", None) == 5:
            return True
        return exc.errno in {errno.EACCES, errno.EPERM}

    @staticmethod
    def _fallback_backup_dir() -> Path:
        for env_var in ("LOCALAPPDATA", "APPDATA"):
            raw = os.environ.get(env_var)
            if raw:
                return Path(raw) / "Dazzle" / "import_backups"
        return Path.home() / "Dazzle" / "import_backups"


def decode_db_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not isinstance(value, (bytes, bytearray)):
        return str(value)

    data = bytes(value)
    for encoding in ("utf-8", "cp1251", "latin1"):
        try:
            return data.decode(encoding)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def encode_db_text(value: str) -> bytes:
    return value.encode("cp1251", errors="replace")


def _format_amount_ru(value: float) -> str:
    normalized = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    if normalized.endswith(",00"):
        normalized = normalized[:-3]
    return normalized


def normalize_article(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    clean = clean.replace("\t", "")
    clean = clean.upper()
    clean = clean.replace(" ", "").replace("-", "")
    clean = clean.replace("_", "")
    for prefix in ("XMIL", "XZK"):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]
            break
    return clean[:20]


def normalize_text_field(value: str, max_len: int) -> str:
    text = " ".join(value.strip().split())
    if len(text) > max_len:
        return text[:max_len]
    return text


def round_up_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return float(math.ceil(value / step) * step)


def calculate_suggested_sell_price(
    buy_price: float,
    *,
    markup_percent: float = 50.0,
    round_step: float = 50.0,
) -> float:
    base = max(0.0, float(buy_price))
    marked = base * (1.0 + (markup_percent / 100.0))
    return round_up_to_step(marked, round_step)
