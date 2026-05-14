from __future__ import annotations

import errno
import math
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import (
    ImportOptions,
    ImportResult,
    InvoiceLine,
    OzonComponentLine,
    OzonImportOptions,
    OzonImportResult,
    OzonSaleDocument,
    ParsedInvoice,
    ParsedOzonCsv,
)

PURCHASE_WAYBILL_RECORD_TYPE = 1
WAYBILL_OPERATION_OBJECT_TYPE = 3
WAYBILL_OPERATION_TYPE_CREATE = 1
WAYBILL_OPERATION_TYPE_UPDATE = 0
OZON_TRANSFER_RECORD_TYPE = 0
OZON_SALE_RECORD_TYPE = -1
TRANSFER_OPERATION_OBJECT_TYPE = 2
SALE_OPERATION_OBJECT_TYPE = 1


class TirikaDBError(RuntimeError):
    pass


class ImportValidationError(TirikaDBError):
    pass


@dataclass
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
        self._table_columns_cache: dict[str, set[str]] = {}
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

    def list_ozon_sales(
        self,
        *,
        shop_id: int = 1,
        ozon_contractor_id: int = 115,
        limit: int = 80,
    ) -> list[OzonSaleDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    wb.id,
                    wb.waybill_date,
                    wb.waybill_number,
                    wb.cost,
                    wb.paid,
                    wb.display_string,
                    COUNT(wi.id) AS item_count
                FROM waybills wb
                LEFT JOIN waybill_items wi
                  ON wi.waybill_id = wb.id AND COALESCE(wi.is_deleted, 0) = 0
                WHERE COALESCE(wb.is_deleted, 0) = 0
                  AND wb.record_type = ?
                  AND wb.shop_id = ?
                  AND wb.contractor_id = ?
                GROUP BY wb.id
                ORDER BY wb.waybill_date DESC, wb.id DESC
                LIMIT ?
                """,
                (OZON_SALE_RECORD_TYPE, shop_id, ozon_contractor_id, limit),
            ).fetchall()

        docs: list[OzonSaleDocument] = []
        for row in rows:
            docs.append(
                OzonSaleDocument(
                    waybill_id=int(row[0]),
                    waybill_date=datetime.fromtimestamp(int(row[1] or 0)),
                    number=decode_db_text(row[2]).strip(),
                    cost=float(row[3] or 0.0),
                    paid=float(row[4] or 0.0),
                    item_count=int(row[6] or 0),
                    display=decode_db_text(row[5]).strip(),
                )
            )
        return docs

    def load_goods_catalog(self, shop_id: int) -> dict[int, GoodRecord]:
        catalog: dict[int, GoodRecord] = {}
        with self._connect() as conn:
            cur = conn.cursor()
            goods_cols = self._table_columns(cur, "goods")

            product_code_expr = self._qi("product_code") if "product_code" in goods_cols else "''"
            barcode_expr = self._qi("barcode") if "barcode" in goods_cols else "''"
            name_expr = self._qi("name") if "name" in goods_cols else "''"
            manufacturer_expr = self._qi("manufacturer") if "manufacturer" in goods_cols else "''"
            buy_price_expr = self._qi("buy_price") if "buy_price" in goods_cols else "0"
            sell_price_expr = self._qi("price") if "price" in goods_cols else "0"
            tax_mode_expr = self._qi("tax_mode") if "tax_mode" in goods_cols else "0"
            supplier_expr = self._qi("supplier_id") if "supplier_id" in goods_cols else "0"
            where_expr = (
                f"COALESCE({self._qi('is_deleted')}, 0) = 0"
                if "is_deleted" in goods_cols
                else "1 = 1"
            )

            good_rows = conn.execute(
                f"""
                SELECT
                    {self._qi("id")},
                    {product_code_expr},
                    {barcode_expr},
                    {name_expr},
                    {manufacturer_expr},
                    {buy_price_expr},
                    {sell_price_expr},
                    {tax_mode_expr},
                    {supplier_expr}
                FROM {self._qi("goods")}
                WHERE {where_expr}
                """
            ).fetchall()
            for row in good_rows:
                gid = int(row[0])
                catalog[gid] = GoodRecord(
                    good_id=gid,
                    product_code=decode_db_text(row[1]),
                    name=decode_db_text(row[3]),
                    manufacturer=decode_db_text(row[4]),
                    buy_price=float(row[5] or 0.0),
                    sell_price=float(row[6] or 0.0),
                    tax_mode=int(row[7] or 0),
                    supplier_id=int(row[8] or 0),
                )
                barcode = decode_db_text(row[2]).strip()
                if barcode:
                    catalog[gid].barcodes.append(barcode)

            remainder_cols = self._table_columns(cur, "remainders")
            if {"good_id", "shop_id"} <= remainder_cols:
                remainder_col = "remainder" if "remainder" in remainder_cols else "0"
                remainder_rows = conn.execute(
                    f"""
                    SELECT {self._qi("good_id")}, {self._qi(remainder_col) if remainder_col != "0" else "0"}
                    FROM {self._qi("remainders")}
                    WHERE {self._qi("shop_id")} = ?
                    """,
                    (shop_id,),
                ).fetchall()
                for row in remainder_rows:
                    gid = int(row[0])
                    if gid in catalog:
                        catalog[gid].remainder = float(row[1] or 0.0)

            cross_cols = self._table_columns(cur, "cross_codes")
            if {"good_id", "cross_code"} <= cross_cols:
                cross_rows = conn.execute(
                    f"SELECT {self._qi('good_id')}, {self._qi('cross_code')} FROM {self._qi('cross_codes')}"
                ).fetchall()
                for row in cross_rows:
                    gid = int(row[0])
                    if gid in catalog:
                        val = decode_db_text(row[1]).strip()
                        if val:
                            catalog[gid].cross_codes.append(val)

            barcode_cols = self._table_columns(cur, "barcodes")
            if {"good_id", "barcode"} <= barcode_cols:
                barcode_rows = conn.execute(
                    f"SELECT {self._qi('good_id')}, {self._qi('barcode')} FROM {self._qi('barcodes')}"
                ).fetchall()
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
            # Safety rule: Dazzle must not write purchase payments directly.
            # Tirika keeps cash/paydesk state separately; direct payment rows can make
            # later payment-type changes or document deletion desynchronize cash totals.
            safe_auto_pay = False
            paid = 0.0
            purchase_payment_type = -1
            display_string = self._build_display_string(item_rows)
            waybill_number = invoice.invoice_number.strip()[:20]

            self._insert_row(
                cur,
                "waybills",
                {
                    "id": waybill_id,
                    "is_deleted": 0,
                    "is_replicated": 0,
                    "shop_id": options.shop_id,
                    "waybill_date": waybill_ts,
                    "record_type": PURCHASE_WAYBILL_RECORD_TYPE,
                    "payment_type": purchase_payment_type,
                    "is_reserve": 0,
                    "reserve_until": 0,
                    "contractor_id": options.supplier_id,
                    "user_id": options.user_id,
                    "waybill_number": encode_db_text(waybill_number),
                    "cost": total_cost,
                    "paid": paid,
                    "display_string": encode_db_text(display_string),
                    "comment": encode_db_text(""),
                    "customer_balls": 0,
                    "referer_balls": 0,
                    "currency_id": 0,
                    "is_archived": 0,
                    "discount_id": -1,
                    "discount": 0,
                    "is_published": 0,
                    "foreign_id": -1,
                    "flags": 0,
                    "repair_status": -1,
                    "customer_balls_spent": 0,
                    "referer_balls_spent": 0,
                },
            )

            for item_id, line, good_id, tax_mode in item_rows:
                qty = round(line.quantity, 6)
                price = round(line.price, 2)
                note = normalize_text_field(line.note or "", max_len=250)
                self._insert_row(
                    cur,
                    "waybill_items",
                    {
                        "id": item_id,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "waybill_id": waybill_id,
                        "goods_id": good_id,
                        "size_id": -1,
                        "quantity": qty,
                        "price": price,
                        "buy_price": price,
                        "vat": 0,
                        "discount": 0,
                        "set_id": -1,
                        "bonus": 0,
                        "sold": 0,
                        "buy_cost": None,
                        "buy_currency_id": 0,
                        "comment": encode_db_text(note),
                        "certificate_id": -1,
                        "foreign_id": -1,
                        "unit_id": -1,
                        "tax_mode": tax_mode,
                    },
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
                set_values: dict[str, object] = {}

                if options.update_existing_buy_price:
                    set_values["buy_price"] = price
                    set_values["buy_currency_id"] = 0

                if options.update_existing_supplier:
                    set_values["supplier_id"] = options.supplier_id

                if options.update_existing_sell_price or force_sell_update:
                    set_values["price"] = sell_price
                    set_values["currency_id"] = 0

                if options.update_existing_name:
                    name = normalize_text_field(line.matched_name or line.name, max_len=120)
                    set_values["name"] = encode_db_text(name)

                if options.update_existing_manufacturer:
                    manufacturer_raw = str(line.raw_data.get("manufacturer", "") or "").strip()
                    manufacturer = normalize_text_field(manufacturer_raw, max_len=60)
                    if manufacturer:
                        set_values["manufacturer"] = encode_db_text(manufacturer)

                if set_values:
                    self._update_row(
                        cur,
                        "goods",
                        set_values,
                        {"id": good_id},
                    )

            if safe_auto_pay:
                self._insert_row(
                    cur,
                    "payments",
                    {
                        "id": payment_id,
                        "waybill_id": waybill_id,
                        "payment_date": waybill_ts,
                        "payment_type": options.payment_type,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "cost": total_cost,
                        "comment": encode_db_text(""),
                        "certificate_id": -1,
                        "register_session": 0,
                        "register_cheque": 0,
                        "register_serial": encode_db_text(""),
                        "payment_order": 0,
                    },
                )

            self._insert_row(
                cur,
                "operations",
                {
                    "id": operation_id,
                    "is_replicated": 0,
                    "user_id": options.user_id,
                    "object_type": WAYBILL_OPERATION_OBJECT_TYPE,
                    "operation_type": WAYBILL_OPERATION_TYPE_CREATE,
                    "operation_date": waybill_ts,
                    "object_id": waybill_id,
                    "object_description": encode_db_text(
                        self._build_operation_description(waybill_date, total_cost)
                    ),
                    "operation_description": encode_db_text(
                        f"Импорт накладной без оплаты: {invoice.file_path.name}"
                    ),
                },
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
                auto_pay=safe_auto_pay,
            )

            if options.auto_pay:
                warnings.append(
                    "Оплата закупки не записана автоматически: "
                    "для защиты кассы оплату нужно оформить в Tirika."
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

    def import_ozon_orders(self, parsed: ParsedOzonCsv, options: OzonImportOptions) -> OzonImportResult:
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

        import_lines: list[OzonComponentLine] = []
        skipped_lines = 0
        seen_postings: set[str] = set()
        seen_orders: set[str] = set()

        for line in parsed.lines:
            if line.order_number:
                seen_orders.add(line.order_number)
            if line.posting_number:
                seen_postings.add(line.posting_number)
            if line.warning:
                warnings.append(f"{line.source_article or line.article}: {line.warning}")
            if line.action != "import":
                skipped_lines += 1
                continue
            if line.matched_good_id is None:
                skipped_lines += 1
                warnings.append(f"{line.source_article or line.article}: товар не сопоставлен.")
                continue
            if line.quantity <= 0:
                skipped_lines += 1
                warnings.append(f"{line.source_article or line.article}: количество <= 0.")
                continue
            if (line.sale_total or 0.0) <= 0 or (line.sale_price or 0.0) <= 0:
                skipped_lines += 1
                warnings.append(f"{line.source_article or line.article}: цена продажи <= 0.")
                continue
            import_lines.append(line)

        if not import_lines:
            raise ImportValidationError("Нет строк Ozon для записи.")

        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            max_waybill_before = self._max_id(cur, "waybills")
            max_waybill_item_before = self._max_id(cur, "waybill_items")
            max_payment_before = self._max_id(cur, "payments")
            max_operation_before = self._max_id(cur, "operations")
            existing_sale_waybill_id = int(options.existing_sale_waybill_id or 0) or None
            existing_sale_row = None
            if existing_sale_waybill_id is not None:
                existing_sale_row = cur.execute(
                    """
                    SELECT id, record_type, shop_id, contractor_id, user_id, waybill_number, cost, paid
                    FROM waybills
                    WHERE id = ? AND COALESCE(is_deleted, 0) = 0
                    """,
                    (existing_sale_waybill_id,),
                ).fetchone()
                if existing_sale_row is None:
                    raise ImportValidationError("Выбранная продажа Ozon не найдена в базе.")
                if int(existing_sale_row[1] or 0) != OZON_SALE_RECORD_TYPE:
                    raise ImportValidationError("Выбранный документ не является продажей Ozon.")
                if int(existing_sale_row[2] or 0) != options.target_shop_id:
                    raise ImportValidationError("Выбранная продажа находится не на складе ОЗОН.")
                if int(existing_sale_row[3] or 0) != options.ozon_contractor_id:
                    raise ImportValidationError("Выбранная продажа не привязана к контрагенту ОЗОН.")

            for line in import_lines:
                current_remainder = self._get_remainder(
                    cur,
                    shop_id=options.source_shop_id,
                    good_id=int(line.matched_good_id or 0),
                )
                line.remainder_source = current_remainder
                if current_remainder + 1e-6 < line.quantity:
                    raise ImportValidationError(
                        f"Недостаточно остатка на складе Авто-255 для {line.matched_product_code or line.article}: "
                        f"нужно {line.quantity:g}, есть {current_remainder:g}."
                    )

            waybill_date = options.waybill_date or datetime.now()
            waybill_ts = int(waybill_date.timestamp())
            transfer_waybill_id = self._next_id(cur, "waybills")
            new_sale_document = existing_sale_waybill_id is None
            sale_waybill_id = transfer_waybill_id + 1 if new_sale_document else int(existing_sale_waybill_id)
            transfer_item_id = self._next_id(cur, "waybill_items")
            sale_item_id = transfer_item_id + len(import_lines)
            payment_id = self._next_id(cur, "payments")
            operation_id = self._next_id(cur, "operations")

            transfer_item_rows: list[tuple[int, OzonComponentLine, float]] = []
            sale_item_rows: list[tuple[int, OzonComponentLine, float]] = []
            transfer_item_by_line: dict[int, int] = {}

            for idx, line in enumerate(import_lines):
                buy_price = round(float(line.matched_buy_price or 0.0), 2)
                if buy_price <= 0:
                    buy_price = round(self._get_good_buy_price(cur, int(line.matched_good_id or 0)), 2)
                if buy_price <= 0:
                    buy_price = 0.01
                    warnings.append(
                        f"{line.matched_product_code or line.article}: закупочная цена в БД пустая, записано 0.01."
                    )
                transfer_id = transfer_item_id + idx
                sale_id = sale_item_id + idx
                transfer_item_rows.append((transfer_id, line, buy_price))
                sale_item_rows.append((sale_id, line, buy_price))
                transfer_item_by_line[id(line)] = transfer_id

            transfer_cost = round(sum(line.quantity * buy_price for _, line, buy_price in transfer_item_rows), 2)
            sale_cost = round(sum(float(line.sale_total or 0.0) for _, line, _ in sale_item_rows), 2)
            card_count = self._ozon_source_card_count(import_lines)
            if new_sale_document:
                sale_number = (options.sale_number.strip() or str(card_count))[:20]
            else:
                old_number = decode_db_text(existing_sale_row[5]).strip() if existing_sale_row else ""
                sale_number = (options.sale_number.strip() or self._bump_numeric_text(old_number, card_count) or old_number)[:20]
            transfer_display = self._build_ozon_display_string(transfer_item_rows)
            sale_display = self._build_ozon_display_string(sale_item_rows)
            comment = f"Dazzle Ozon CSV: {parsed.file_path.name}"

            self._insert_row(
                cur,
                "waybills",
                {
                    "id": transfer_waybill_id,
                    "is_deleted": 0,
                    "is_replicated": 0,
                    "shop_id": options.source_shop_id,
                    "waybill_date": waybill_ts,
                    "record_type": OZON_TRANSFER_RECORD_TYPE,
                    "payment_type": -1,
                    "is_reserve": 0,
                    "reserve_until": 0,
                    "contractor_id": options.target_shop_id,
                    "user_id": options.user_id,
                    "waybill_number": encode_db_text(""),
                    "cost": transfer_cost,
                    "paid": 0,
                    "display_string": encode_db_text(transfer_display),
                    "comment": encode_db_text(comment),
                    "customer_balls": 0,
                    "referer_balls": 0,
                    "currency_id": 0,
                    "is_archived": 0,
                    "discount_id": -1,
                    "discount": 0,
                    "is_published": 0,
                    "foreign_id": -1,
                    "flags": 0,
                    "repair_status": -1,
                    "customer_balls_spent": 0,
                    "referer_balls_spent": 0,
                },
            )

            if new_sale_document:
                self._insert_row(
                    cur,
                    "waybills",
                    {
                        "id": sale_waybill_id,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "shop_id": options.target_shop_id,
                        "waybill_date": waybill_ts,
                        "record_type": OZON_SALE_RECORD_TYPE,
                        "payment_type": options.payment_type,
                        "is_reserve": 0,
                        "reserve_until": 0,
                        "contractor_id": options.ozon_contractor_id,
                        "user_id": options.user_id,
                        "waybill_number": encode_db_text(sale_number),
                        "cost": sale_cost,
                        "paid": sale_cost,
                        "display_string": encode_db_text(sale_display),
                        "comment": encode_db_text(comment),
                        "customer_balls": round(sale_cost * 0.05, 2),
                        "referer_balls": 0,
                        "currency_id": 0,
                        "is_archived": 0,
                        "discount_id": -1,
                        "discount": 0,
                        "is_published": 0,
                        "foreign_id": -1,
                        "flags": 0,
                        "repair_status": -1,
                        "customer_balls_spent": 0,
                        "referer_balls_spent": 0,
                    },
                )

            for item_id, line, buy_price in transfer_item_rows:
                good_id = int(line.matched_good_id or 0)
                qty = round(line.quantity, 6)
                tax_mode = self._get_good_tax_mode(cur, good_id, default=line.matched_tax_mode)
                self._insert_row(
                    cur,
                    "waybill_items",
                    {
                        "id": item_id,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "waybill_id": transfer_waybill_id,
                        "goods_id": good_id,
                        "size_id": -1,
                        "quantity": qty,
                        "price": buy_price,
                        "buy_price": buy_price,
                        "vat": 0,
                        "discount": 0,
                        "set_id": -1,
                        "bonus": 0,
                        "sold": 0,
                        "buy_cost": None,
                        "buy_currency_id": 0,
                        "comment": encode_db_text(line.posting_number),
                        "certificate_id": -1,
                        "foreign_id": -1,
                        "unit_id": -1,
                        "tax_mode": tax_mode,
                    },
                )
                missing = self._link_source_stock_to_item(
                    cur,
                    good_id=good_id,
                    source_shop_id=options.source_shop_id,
                    sell_item_id=item_id,
                    quantity=qty,
                )
                if missing > 0:
                    warnings.append(
                        f"{line.matched_product_code or line.article}: не хватило партий для связи на {missing:g} шт."
                    )
                self._upsert_remainders(cur, shop_id=options.source_shop_id, good_id=good_id, quantity=-qty)
                self._upsert_remainders(cur, shop_id=options.target_shop_id, good_id=good_id, quantity=qty)

            for item_id, line, buy_price in sale_item_rows:
                good_id = int(line.matched_good_id or 0)
                qty = round(line.quantity, 6)
                sale_price = round(float(line.sale_price or 0.0), 2)
                tax_mode = self._get_good_tax_mode(cur, good_id, default=line.matched_tax_mode)
                transfer_id = transfer_item_by_line[id(line)]
                self._insert_row(
                    cur,
                    "waybill_items",
                    {
                        "id": item_id,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "waybill_id": sale_waybill_id,
                        "goods_id": good_id,
                        "size_id": -1,
                        "quantity": qty,
                        "price": sale_price,
                        "buy_price": buy_price,
                        "vat": 0,
                        "discount": 0,
                        "set_id": -1,
                        "bonus": 0,
                        "sold": 0,
                        "buy_cost": None,
                        "buy_currency_id": 0,
                        "comment": encode_db_text(line.posting_number),
                        "certificate_id": -1,
                        "foreign_id": -1,
                        "unit_id": -1,
                        "tax_mode": tax_mode,
                    },
                )
                self._insert_shipment_sale(
                    cur,
                    buy_item_id=transfer_id,
                    sell_item_id=item_id,
                    buy_price=buy_price,
                    quantity=qty,
                )
                self._increment_item_sold(cur, item_id=transfer_id, quantity=qty)
                self._upsert_remainders(cur, shop_id=options.target_shop_id, good_id=good_id, quantity=-qty)

            expected_new_payments = 1
            if new_sale_document:
                self._insert_row(
                    cur,
                    "payments",
                    {
                        "id": payment_id,
                        "waybill_id": sale_waybill_id,
                        "payment_date": waybill_ts,
                        "payment_type": options.payment_type,
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "cost": sale_cost,
                        "comment": encode_db_text(""),
                        "certificate_id": -1,
                        "register_session": 0,
                        "register_cheque": 0,
                        "register_serial": encode_db_text(""),
                        "payment_order": 0,
                    },
                )
            else:
                old_cost = float(existing_sale_row[6] or 0.0) if existing_sale_row else 0.0
                old_paid = float(existing_sale_row[7] or 0.0) if existing_sale_row else 0.0
                new_cost = round(old_cost + sale_cost, 2)
                new_paid = round(old_paid + sale_cost, 2)
                sale_display = self._build_waybill_display_from_db(cur, sale_waybill_id)
                self._update_row(
                    cur,
                    "waybills",
                    {
                        "payment_type": options.payment_type,
                        "waybill_number": encode_db_text(sale_number),
                        "cost": new_cost,
                        "paid": new_paid,
                        "display_string": encode_db_text(sale_display),
                        "comment": encode_db_text(comment),
                        "customer_balls": round(new_cost * 0.05, 2),
                        "is_replicated": 0,
                    },
                    {"id": sale_waybill_id},
                )
                inserted_payment = self._add_to_ozon_sale_payment(
                    cur,
                    sale_waybill_id=sale_waybill_id,
                    payment_id=payment_id,
                    payment_type=options.payment_type,
                    payment_date_ts=waybill_ts,
                    add_cost=sale_cost,
                )
                expected_new_payments = 1 if inserted_payment else 0

            self._insert_row(
                cur,
                "operations",
                {
                    "id": operation_id,
                    "is_replicated": 0,
                    "user_id": options.user_id,
                    "object_type": TRANSFER_OPERATION_OBJECT_TYPE,
                    "operation_type": WAYBILL_OPERATION_TYPE_CREATE,
                    "operation_date": waybill_ts,
                    "object_id": transfer_waybill_id,
                    "object_description": encode_db_text(f"от {waybill_date.strftime('%d.%m.%y')}"),
                    "operation_description": encode_db_text(
                        f"Dazzle Ozon: перемещение Авто-255 -> ОЗОН, {len(import_lines)} строк."
                    ),
                },
            )
            self._insert_row(
                cur,
                "operations",
                {
                    "id": operation_id + 1,
                    "is_replicated": 0,
                    "user_id": options.user_id,
                    "object_type": SALE_OPERATION_OBJECT_TYPE,
                    "operation_type": WAYBILL_OPERATION_TYPE_CREATE
                    if new_sale_document
                    else WAYBILL_OPERATION_TYPE_UPDATE,
                    "operation_date": waybill_ts,
                    "object_id": sale_waybill_id,
                    "object_description": encode_db_text(
                        f"{sale_number} от {waybill_date.strftime('%d.%m.%Y')} на {_format_amount_ru(sale_cost)}"
                    ),
                    "operation_description": encode_db_text(
                        (
                            f"Dazzle Ozon: продажа по CSV {parsed.file_path.name}, отправлений: {len(seen_postings)}."
                            if new_sale_document
                            else f"Dazzle Ozon: добавлены товары в продажу #{sale_waybill_id}, CSV {parsed.file_path.name}."
                        )
                    ),
                },
            )

            self._assert_ozon_invariants(
                cur=cur,
                max_waybill_before=max_waybill_before,
                max_waybill_item_before=max_waybill_item_before,
                max_payment_before=max_payment_before,
                max_operation_before=max_operation_before,
                transfer_waybill_id=transfer_waybill_id,
                sale_waybill_id=sale_waybill_id,
                expected_items=len(import_lines) * 2,
                expected_new_waybills=2 if new_sale_document else 1,
                expected_new_payments=expected_new_payments,
                source_shop_id=options.source_shop_id,
                target_shop_id=options.target_shop_id,
                ozon_contractor_id=options.ozon_contractor_id,
                user_id=options.user_id,
                existing_sale=not new_sale_document,
            )

            if options.dry_run:
                conn.rollback()
                transfer_out: int | None = None
                sale_out: int | None = None
            else:
                conn.commit()
                transfer_out = transfer_waybill_id
                sale_out = sale_waybill_id

            return OzonImportResult(
                success=True,
                dry_run=options.dry_run,
                backup_path=backup_path,
                transfer_waybill_id=transfer_out,
                sale_waybill_id=sale_out,
                imported_lines=len(import_lines),
                skipped_lines=skipped_lines,
                order_count=len(seen_orders),
                posting_count=len(seen_postings),
                transfer_cost=transfer_cost,
                sale_cost=sale_cost,
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

        self._insert_row(
            cur,
            "goods",
            {
                "id": new_good_id,
                "group_id": target_group_id,
                "is_deleted": 0,
                "is_replicated": 0,
                "is_sized": 0,
                "is_discounted": 1,
                "is_set": 0,
                "name": encode_db_text(name),
                "unit_name": encode_db_text("шт."),
                "manufacturer": encode_db_text(manufacturer),
                "product_code": encode_db_text(article),
                "barcode": encode_db_text(""),
                "price": sell_price,
                "price1": 0,
                "price2": 0,
                "price3": 0,
                "buy_price": buy_price,
                "seller_bonus": 0,
                "vat": 0,
                "photo": None,
                "photo_extention": encode_db_text(""),
                "description": encode_db_text(""),
                "comment": encode_db_text(""),
                "decimal_places": 0,
                "good_type": 0,
                "alco_type": 0,
                "alco_amount": 0,
                "currency_id": 0,
                "currency_id1": 0,
                "currency_id2": 0,
                "currency_id3": 0,
                "buy_currency_id": 0,
                "price_change_date": 0,
                "is_alco_marked": 0,
                "is_tap_trade": 0,
                "alco_strength": 0,
                "is_serial_required": 0,
                "tax_mode": 0,
                "tax_percent": 0,
                "price_advance": 0,
                "price_advance1": 0,
                "price_advance2": 0,
                "price_advance3": 0,
                "register_type": 0,
                "is_published": 0,
                "foreign_id": -1,
                "is_publish": 0,
                "is_estore_delivery": 0,
                "estore_short_description": None,
                "estore_long_description": None,
                "estore_meta_title": None,
                "estore_meta_description": None,
                "estore_meta_keywords": None,
                "estore_friendly_url": None,
                "estore_tags": None,
                "estore_sort_order": 0,
                "hotkey": 0,
                "price_round": 0,
                "unit_code": 0,
                "old_currency_id": 0,
                "old_price": 0,
                "supplier_id": supplier_id,
                "flags": 0,
                "is_archived": 0,
                "length": 0,
                "width": 0,
                "height": 0,
                "weight": 0,
                "is_ozon_published": 0,
                "marketplaces_id": 0,
            },
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
                self._update_row(
                    cur,
                    "good_groups",
                    {
                        "is_deleted": 0,
                        "is_replicated": 0,
                        "name": encode_db_text("Dazzle"),
                        "full_name": encode_db_text("Dazzle"),
                        "parent_id": -1,
                    },
                    {"id": group_id},
                )
            return group_id

        new_group_id = self._next_id(cur, "good_groups")
        self._insert_row(
            cur,
            "good_groups",
            {
                "id": new_group_id,
                "is_deleted": 0,
                "is_replicated": 0,
                "name": encode_db_text("Dazzle"),
                "comment": encode_db_text(""),
                "parent_id": -1,
                "full_name": encode_db_text("Dazzle"),
                "section": 0,
                "is_published": 0,
                "foreign_id": -1,
                "estore_meta_title": None,
                "estore_meta_description": None,
                "estore_meta_keywords": None,
                "estore_friendly_url": None,
                "estore_sort_order": 0,
                "description": encode_db_text(""),
            },
        )
        return new_group_id

    def _insert_auto_cross_code(self, cur: sqlite3.Cursor, good_id: int, supplier_name: str) -> None:
        if not {"good_id", "cross_code"} <= self._table_columns(cur, "cross_codes"):
            return
        supplier = normalize_text_field(supplier_name, max_len=80)
        supplier = "-".join(supplier.split()) if supplier else "unknown"
        cross_code = f"Dazzle-auto-made-from-{supplier}"
        self._insert_row(
            cur,
            "cross_codes",
            {
                "good_id": good_id,
                "cross_code": encode_db_text(cross_code),
            },
        )

    def _upsert_remainders(self, cur: sqlite3.Cursor, shop_id: int, good_id: int, quantity: float) -> None:
        rem_cols = self._table_columns(cur, "remainders")
        if not {"shop_id", "good_id"} <= rem_cols:
            return
        if "remainder" not in rem_cols:
            return

        row = cur.execute(
            f"""
            SELECT {self._qi('remainder')}
            FROM {self._qi('remainders')}
            WHERE {self._qi('shop_id')} = ? AND {self._qi('good_id')} = ?
            """,
            (shop_id, good_id),
        ).fetchone()

        if row is None:
            self._insert_row(
                cur,
                "remainders",
                {
                    "shop_id": shop_id,
                    "good_id": good_id,
                    "is_deleted": 0,
                    "is_replicated": 0,
                    "remainder": quantity,
                    "reserved": 0,
                    "min_amount": 0,
                    "expected": 0,
                    "is_published": 0,
                    "is_ozon_published": 0,
                },
            )
            return

        current_remainder = float(row[0] or 0.0)
        self._update_row(
            cur,
            "remainders",
            {
                "remainder": current_remainder + quantity,
                "is_deleted": 0,
                "is_replicated": 0,
            },
            {
                "shop_id": shop_id,
                "good_id": good_id,
            },
        )

    def _get_good_tax_mode(self, cur: sqlite3.Cursor, good_id: int, default: int = 0) -> int:
        if not self._table_has_column(cur, "goods", "tax_mode"):
            return default
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

    def _build_ozon_display_string(self, item_rows: list[tuple[int, OzonComponentLine, float]]) -> str:
        parts: list[str] = []
        for _, line, _ in item_rows[:8]:
            code = line.matched_product_code.strip() or line.article.strip()
            name = line.matched_name.strip() or line.name.strip()
            qty = int(line.quantity) if float(line.quantity).is_integer() else line.quantity
            parts.append(f"[{code}] {name} ({qty})")
        return ", ".join(parts)[:120]

    def _build_waybill_display_from_db(self, cur: sqlite3.Cursor, waybill_id: int) -> str:
        rows = cur.execute(
            """
            SELECT g.product_code, g.name, wi.quantity
            FROM waybill_items wi
            LEFT JOIN goods g ON g.id = wi.goods_id
            WHERE wi.waybill_id = ? AND COALESCE(wi.is_deleted, 0) = 0
            ORDER BY wi.id
            LIMIT 8
            """,
            (waybill_id,),
        ).fetchall()
        parts: list[str] = []
        for code_raw, name_raw, quantity in rows:
            code = decode_db_text(code_raw).strip()
            name = decode_db_text(name_raw).strip()
            qty = float(quantity or 0.0)
            qty_text = str(int(qty)) if qty.is_integer() else f"{qty:g}"
            parts.append(f"[{code}] {name} ({qty_text})")
        return ", ".join(parts)[:120]

    @staticmethod
    def _ozon_source_card_count(lines: list[OzonComponentLine]) -> int:
        keys = {
            (line.line_no, line.order_number, line.posting_number, line.source_article)
            for line in lines
        }
        return len(keys) if keys else len(lines)

    @staticmethod
    def _bump_numeric_text(value: str, add_count: int) -> str:
        text = str(value or "").strip()
        if text.isdigit():
            return str(int(text) + max(0, int(add_count)))
        return text

    def _build_operation_description(self, waybill_date: datetime, cost: float) -> str:
        return f" от {waybill_date.strftime('%d.%m.%y')} на {_format_amount_ru(cost)}"

    def _next_id(self, cur: sqlite3.Cursor, table: str) -> int:
        row = cur.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}").fetchone()
        return int(row[0])

    def _max_id(self, cur: sqlite3.Cursor, table: str) -> int:
        row = cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()
        return int(row[0] or 0)

    def _get_remainder(self, cur: sqlite3.Cursor, shop_id: int, good_id: int) -> float:
        if not {"shop_id", "good_id", "remainder"} <= self._table_columns(cur, "remainders"):
            return 0.0
        row = cur.execute(
            """
            SELECT remainder
            FROM remainders
            WHERE shop_id = ? AND good_id = ?
            """,
            (shop_id, good_id),
        ).fetchone()
        if row is None:
            return 0.0
        return float(row[0] or 0.0)

    def _get_good_buy_price(self, cur: sqlite3.Cursor, good_id: int) -> float:
        if not self._table_has_column(cur, "goods", "buy_price"):
            return 0.0
        row = cur.execute("SELECT buy_price FROM goods WHERE id = ?", (good_id,)).fetchone()
        if row is None:
            return 0.0
        return float(row[0] or 0.0)

    def _link_source_stock_to_item(
        self,
        cur: sqlite3.Cursor,
        *,
        good_id: int,
        source_shop_id: int,
        sell_item_id: int,
        quantity: float,
    ) -> float:
        remaining = round(float(quantity), 6)
        if remaining <= 0:
            return 0.0

        rows = cur.execute(
            """
            SELECT wi.id, wi.quantity, COALESCE(wi.sold, 0), wi.price, wi.buy_price
            FROM waybill_items wi
            JOIN waybills wb ON wb.id = wi.waybill_id
            WHERE wi.goods_id = ?
              AND COALESCE(wi.is_deleted, 0) = 0
              AND COALESCE(wb.is_deleted, 0) = 0
              AND wb.shop_id = ?
              AND wb.record_type IN (1, 2)
              AND COALESCE(wi.quantity, 0) > COALESCE(wi.sold, 0)
            ORDER BY wb.waybill_date, wi.id
            """,
            (good_id, source_shop_id),
        ).fetchall()

        for item_id, qty, sold, price, buy_price in rows:
            available = round(float(qty or 0.0) - float(sold or 0.0), 6)
            if available <= 0:
                continue
            take = min(available, remaining)
            stock_price = float(buy_price if buy_price is not None else price or 0.0)
            self._insert_shipment_sale(
                cur,
                buy_item_id=int(item_id),
                sell_item_id=sell_item_id,
                buy_price=round(stock_price, 2),
                quantity=take,
            )
            self._increment_item_sold(cur, item_id=int(item_id), quantity=take)
            remaining = round(remaining - take, 6)
            if remaining <= 1e-6:
                return 0.0

        return max(0.0, remaining)

    def _insert_shipment_sale(
        self,
        cur: sqlite3.Cursor,
        *,
        buy_item_id: int,
        sell_item_id: int,
        buy_price: float,
        quantity: float,
    ) -> None:
        if not {"buy_item_id", "sell_item_id"} <= self._table_columns(cur, "shipment_sales"):
            return
        self._insert_row(
            cur,
            "shipment_sales",
            {
                "buy_item_id": buy_item_id,
                "sell_item_id": sell_item_id,
                "is_production_buy": 0,
                "is_production_sell": 0,
                "buy_price": round(float(buy_price), 2),
                "quantity": round(float(quantity), 6),
                "currency_id": 0,
            },
        )

    def _increment_item_sold(self, cur: sqlite3.Cursor, *, item_id: int, quantity: float) -> None:
        if not self._table_has_column(cur, "waybill_items", "sold"):
            return
        row = cur.execute("SELECT COALESCE(sold, 0) FROM waybill_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return
        current = float(row[0] or 0.0)
        self._update_row(
            cur,
            "waybill_items",
            {"sold": current + float(quantity)},
            {"id": item_id},
        )

    def _add_to_ozon_sale_payment(
        self,
        cur: sqlite3.Cursor,
        *,
        sale_waybill_id: int,
        payment_id: int,
        payment_type: int,
        payment_date_ts: int,
        add_cost: float,
    ) -> bool:
        rows = cur.execute(
            """
            SELECT id, cost
            FROM payments
            WHERE waybill_id = ? AND COALESCE(is_deleted, 0) = 0
            ORDER BY id
            """,
            (sale_waybill_id,),
        ).fetchall()
        if rows:
            row_id = int(rows[0][0])
            current_cost = float(rows[0][1] or 0.0)
            self._update_row(
                cur,
                "payments",
                {
                    "payment_type": payment_type,
                    "cost": round(current_cost + add_cost, 2),
                    "is_replicated": 0,
                },
                {"id": row_id},
            )
            return False

        self._insert_row(
            cur,
            "payments",
            {
                "id": payment_id,
                "waybill_id": sale_waybill_id,
                "payment_date": payment_date_ts,
                "payment_type": payment_type,
                "is_deleted": 0,
                "is_replicated": 0,
                "cost": add_cost,
                "comment": encode_db_text(""),
                "certificate_id": -1,
                "register_session": 0,
                "register_cheque": 0,
                "register_serial": encode_db_text(""),
                "payment_order": 0,
            },
        )
        return True

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

    def _assert_ozon_invariants(
        self,
        *,
        cur: sqlite3.Cursor,
        max_waybill_before: int,
        max_waybill_item_before: int,
        max_payment_before: int,
        max_operation_before: int,
        transfer_waybill_id: int,
        sale_waybill_id: int,
        expected_items: int,
        expected_new_waybills: int,
        expected_new_payments: int,
        source_shop_id: int,
        target_shop_id: int,
        ozon_contractor_id: int,
        user_id: int,
        existing_sale: bool,
    ) -> None:
        waybills = cur.execute(
            """
            SELECT id, record_type, shop_id, contractor_id, user_id
            FROM waybills
            WHERE id > ?
            ORDER BY id
            """,
            (max_waybill_before,),
        ).fetchall()
        if len(waybills) != expected_new_waybills:
            raise ImportValidationError(
                "Контроль Ozon: создано неожиданное число документов waybill."
            )

        transfer = waybills[0]
        if int(transfer[0]) != transfer_waybill_id:
            raise ImportValidationError("Контроль Ozon: создан не тот документ waybill.")
        if int(transfer[1] or 0) != OZON_TRANSFER_RECORD_TYPE:
            raise ImportValidationError("Контроль Ozon: первый документ не является перемещением.")
        if int(transfer[2] or 0) != source_shop_id or int(transfer[3] or 0) != target_shop_id:
            raise ImportValidationError("Контроль Ozon: перемещение записано не из Авто-255 в ОЗОН.")
        if int(transfer[4] or 0) != user_id:
            raise ImportValidationError("Контроль Ozon: записан неверный пользователь.")

        if existing_sale:
            sale = cur.execute(
                """
                SELECT id, record_type, shop_id, contractor_id, user_id
                FROM waybills
                WHERE id = ? AND COALESCE(is_deleted, 0) = 0
                """,
                (sale_waybill_id,),
            ).fetchone()
            if sale is None:
                raise ImportValidationError("Контроль Ozon: выбранная продажа исчезла.")
        else:
            if len(waybills) != 2:
                raise ImportValidationError("Контроль Ozon: новая продажа не создана.")
            sale = waybills[1]
            if int(sale[0]) != sale_waybill_id:
                raise ImportValidationError("Контроль Ozon: создана не та продажа.")

        if int(sale[1] or 0) != OZON_SALE_RECORD_TYPE:
            raise ImportValidationError("Контроль Ozon: документ продажи имеет неверный тип.")
        if int(sale[2] or 0) != target_shop_id or int(sale[3] or 0) != ozon_contractor_id:
            raise ImportValidationError("Контроль Ozon: продажа записана не на склад/контрагента ОЗОН.")
        if int(sale[4] or 0) != user_id and not existing_sale:
            raise ImportValidationError("Контроль Ozon: записан неверный пользователь продажи.")

        forbidden = cur.execute(
            """
            SELECT COUNT(*)
            FROM waybills
            WHERE id > ? AND record_type NOT IN (?, ?)
            """,
            (max_waybill_before, OZON_TRANSFER_RECORD_TYPE, OZON_SALE_RECORD_TYPE),
        ).fetchone()
        if int(forbidden[0] or 0) != 0:
            raise ImportValidationError("Контроль Ozon: создан документ недопустимого типа.")

        item_stats = cur.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT waybill_id)
            FROM waybill_items
            WHERE id > ?
            """,
            (max_waybill_item_before,),
        ).fetchone()
        item_count = int(item_stats[0] or 0)
        distinct_wb = int(item_stats[1] or 0)
        if item_count != expected_items or distinct_wb != 2:
            raise ImportValidationError("Контроль Ozon: количество строк товаров не совпало.")
        wrong_items = cur.execute(
            """
            SELECT COUNT(*)
            FROM waybill_items
            WHERE id > ? AND waybill_id NOT IN (?, ?)
            """,
            (max_waybill_item_before, transfer_waybill_id, sale_waybill_id),
        ).fetchone()
        if int(wrong_items[0] or 0) != 0:
            raise ImportValidationError("Контроль Ozon: строки товаров привязаны к другому документу.")

        payments = cur.execute(
            """
            SELECT id, waybill_id
            FROM payments
            WHERE id > ?
            ORDER BY id
            """,
            (max_payment_before,),
        ).fetchall()
        if len(payments) != expected_new_payments:
            raise ImportValidationError("Контроль Ozon: платеж должен быть только у продажи Ozon.")
        if payments and int(payments[0][1] or 0) != sale_waybill_id:
            raise ImportValidationError("Контроль Ozon: платеж привязан не к продаже Ozon.")

        operations = cur.execute(
            """
            SELECT id, object_type, operation_type, object_id
            FROM operations
            WHERE id > ?
            ORDER BY id
            """,
            (max_operation_before,),
        ).fetchall()
        if len(operations) != 2:
            raise ImportValidationError("Контроль Ozon: создано неожиданное число operations.")
        expected = {
            (TRANSFER_OPERATION_OBJECT_TYPE, WAYBILL_OPERATION_TYPE_CREATE, transfer_waybill_id),
            (
                SALE_OPERATION_OBJECT_TYPE,
                WAYBILL_OPERATION_TYPE_UPDATE if existing_sale else WAYBILL_OPERATION_TYPE_CREATE,
                sale_waybill_id,
            ),
        }
        actual = {
            (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0))
            for row in operations
        }
        if actual != expected:
            raise ImportValidationError("Контроль Ozon: operations записаны не в те типы документов.")

    @staticmethod
    def _qi(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _table_columns(self, cur: sqlite3.Cursor, table: str) -> set[str]:
        key = table.lower()
        cached = self._table_columns_cache.get(key)
        if cached is not None:
            return cached
        rows = cur.execute(f"PRAGMA table_info({self._qi(table)})").fetchall()
        cols = {decode_db_text(row[1]).strip() for row in rows if len(row) > 1}
        self._table_columns_cache[key] = cols
        return cols

    def _table_has_column(self, cur: sqlite3.Cursor, table: str, column: str) -> bool:
        return column in self._table_columns(cur, table)

    def _insert_row(self, cur: sqlite3.Cursor, table: str, values: dict[str, object]) -> None:
        cols_available = self._table_columns(cur, table)
        payload = {k: v for k, v in values.items() if k in cols_available}
        if not payload:
            raise ImportValidationError(
                f"В таблице '{table}' нет совместимых колонок для вставки."
            )

        columns_sql = ", ".join(self._qi(col) for col in payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        params = tuple(payload.values())
        cur.execute(
            f"INSERT INTO {self._qi(table)} ({columns_sql}) VALUES ({placeholders})",
            params,
        )

    def _update_row(
        self,
        cur: sqlite3.Cursor,
        table: str,
        set_values: dict[str, object],
        where_values: dict[str, object],
    ) -> bool:
        cols_available = self._table_columns(cur, table)
        set_payload = {k: v for k, v in set_values.items() if k in cols_available}
        where_payload = {k: v for k, v in where_values.items() if k in cols_available}

        if not set_payload or not where_payload:
            return False

        set_sql = ", ".join(f"{self._qi(col)} = ?" for col in set_payload.keys())
        where_sql = " AND ".join(f"{self._qi(col)} = ?" for col in where_payload.keys())
        params = tuple(set_payload.values()) + tuple(where_payload.values())
        cur.execute(
            f"UPDATE {self._qi(table)} SET {set_sql} WHERE {where_sql}",
            params,
        )
        return True

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

