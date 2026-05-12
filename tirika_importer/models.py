from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MatchCandidate:
    good_id: int
    product_code: str
    name: str
    manufacturer: str
    buy_price: float
    sell_price: float
    remainder: float
    match_method: str
    score: float


@dataclass
class InvoiceLine:
    line_no: int
    article: str
    name: str
    note: str
    quantity: float
    price: float
    total: float
    source_supplier: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    match_status: str = "not_found"
    match_method: str = ""
    warning: str = ""
    action: str = "import"

    matched_good_id: int | None = None
    matched_product_code: str = ""
    matched_name: str = ""
    matched_buy_price: float | None = None
    existing_sell_price: float | None = None
    sell_price: float | None = None
    suggested_sell_price: float | None = None
    sell_price_diff_percent: float | None = None
    price_alert: bool = False
    similar_articles: str = ""
    matched_tax_mode: int = 0
    candidates: list[MatchCandidate] = field(default_factory=list)


@dataclass
class ParsedInvoice:
    file_path: Path
    supplier_hint: str
    source_type: str
    lines: list[InvoiceLine]
    invoice_number: str = ""
    invoice_date: datetime | None = None
    currency: str = "RUB"


@dataclass
class ImportOptions:
    supplier_id: int
    user_id: int
    shop_id: int
    payment_type: int
    dry_run: bool
    create_missing_goods: bool
    update_existing_goods_fields: bool
    update_goods_buy_price: bool
    backup_before_import: bool
    auto_pay: bool
    update_existing_buy_price: bool = True
    update_existing_supplier: bool = True
    update_existing_name: bool = False
    update_existing_manufacturer: bool = False
    update_existing_sell_price: bool = False
    prefix_new_goods_with_order: bool = True
    waybill_date: datetime | None = None


@dataclass
class ImportResult:
    success: bool
    dry_run: bool
    backup_path: Path | None
    waybill_id: int | None
    imported_lines: int
    skipped_lines: int
    created_goods: int
    total_cost: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class OzonComponentLine:
    line_no: int
    order_number: str
    posting_number: str
    status: str
    source_article: str
    article: str
    article_options: list[str]
    name: str
    quantity: float
    source_quantity: float
    source_unit_price: float
    source_total: float
    paid_unit_price: float
    paid_total: float
    sku: str = ""

    match_status: str = "not_found"
    match_method: str = ""
    warning: str = ""
    action: str = "import"

    matched_good_id: int | None = None
    matched_product_code: str = ""
    matched_name: str = ""
    matched_buy_price: float | None = None
    existing_sell_price: float | None = None
    sale_price: float | None = None
    sale_total: float | None = None
    remainder_source: float | None = None
    matched_tax_mode: int = 0
    candidates: list[MatchCandidate] = field(default_factory=list)


@dataclass
class ParsedOzonCsv:
    file_path: Path
    lines: list[OzonComponentLine]
    raw_rows: int
    order_count: int
    posting_count: int

    @property
    def import_lines(self) -> list[OzonComponentLine]:
        return [line for line in self.lines if line.action == "import"]


@dataclass
class OzonImportOptions:
    user_id: int
    source_shop_id: int
    target_shop_id: int
    ozon_contractor_id: int
    payment_type: int
    dry_run: bool
    backup_before_import: bool
    waybill_date: datetime | None = None
    sale_number: str = ""
    existing_sale_waybill_id: int | None = None


@dataclass
class OzonImportResult:
    success: bool
    dry_run: bool
    backup_path: Path | None
    transfer_waybill_id: int | None
    sale_waybill_id: int | None
    imported_lines: int
    skipped_lines: int
    order_count: int
    posting_count: int
    transfer_cost: float
    sale_cost: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class OzonSaleDocument:
    waybill_id: int
    waybill_date: datetime
    number: str
    cost: float
    paid: float
    item_count: int
    display: str

