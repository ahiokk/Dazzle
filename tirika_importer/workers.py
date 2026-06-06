"""Фоновые воркеры (QThread) Dazzle.

Вынесено из gui.py. Каждый воркер — QObject с сигналами finished/failed,
который перемещается в QThread; UI-ссылок не имеет.
"""
from __future__ import annotations

from pathlib import Path

from .db import TirikaDB
from .matcher import GoodsMatcher
from .models import (
    ImportOptions,
    InvoiceLine,
    OzonImportOptions,
    ParsedInvoice,
    ParsedOzonCsv,
)
from .parsers import parse_invoice_file
from .qt_compat import QObject, Signal
from .updater import UpdateError, UpdateInfo, download_installer


class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, update: UpdateInfo, target_dir: Path) -> None:
        super().__init__()
        self._update = update
        self._target_dir = target_dir

    def run(self) -> None:
        try:
            installer_path = download_installer(
                self._update,
                self._target_dir,
                progress_cb=lambda done, total: self.progress.emit(int(done), int(total)),
            )
            self.finished.emit(str(installer_path))
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))


class DbOpenWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path: Path, shop_id: int) -> None:
        super().__init__()
        self._db_path = Path(db_path)
        self._shop_id = int(shop_id)

    def run(self) -> None:
        try:
            db = TirikaDB(self._db_path)
            suppliers = db.list_suppliers()
            users = db.list_users()
            shops = db.list_shops()
            shop_ids = {int(sid) for sid, _ in shops}
            if self._shop_id in shop_ids:
                effective_shop_id = self._shop_id
            elif shops:
                effective_shop_id = int(shops[0][0])
            else:
                effective_shop_id = 0
            catalog = db.load_goods_catalog(shop_id=effective_shop_id)
            self.finished.emit(
                {
                    "db_path": str(self._db_path),
                    "suppliers": suppliers,
                    "users": users,
                    "shops": shops,
                    "shop_id": effective_shop_id,
                    "catalog": catalog,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class CatalogLoadWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path: Path, shop_id: int, run_matching_after: bool) -> None:
        super().__init__()
        self._db_path = Path(db_path)
        self._shop_id = int(shop_id)
        self._run_matching_after = bool(run_matching_after)

    def run(self) -> None:
        try:
            db = TirikaDB(self._db_path)
            catalog = db.load_goods_catalog(shop_id=self._shop_id)
            self.finished.emit(
                {
                    "shop_id": self._shop_id,
                    "catalog": catalog,
                    "run_matching_after": self._run_matching_after,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class InvoiceLoadWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, invoice_path: Path) -> None:
        super().__init__()
        self._invoice_path = Path(invoice_path)

    def run(self) -> None:
        try:
            invoice = parse_invoice_file(self._invoice_path)
            self.finished.emit(invoice)
        except Exception as exc:
            self.failed.emit(str(exc))


class MatchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, matcher: GoodsMatcher, lines: list[InvoiceLine], record_history: bool) -> None:
        super().__init__()
        self._matcher = matcher
        self._lines = lines
        self._record_history = bool(record_history)

    def run(self) -> None:
        try:
            self._matcher.match_lines(self._lines)
            self.finished.emit(
                {
                    "record_history": self._record_history,
                    "line_count": len(self._lines),
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class ImportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        db: TirikaDB,
        invoice: ParsedInvoice,
        options: ImportOptions,
        supplier_name: str,
        payment_name: str,
    ) -> None:
        super().__init__()
        self._db = db
        self._invoice = invoice
        self._options = options
        self._supplier_name = supplier_name
        self._payment_name = payment_name

    def run(self) -> None:
        try:
            result = self._db.import_invoice(self._invoice, self._options)
            self.finished.emit(
                {
                    "result": result,
                    "dry_run": self._options.dry_run,
                    "supplier_name": self._supplier_name,
                    "payment_name": self._payment_name,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class OzonImportWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, db: TirikaDB, parsed: ParsedOzonCsv, options: OzonImportOptions) -> None:
        super().__init__()
        self._db = db
        self._parsed = parsed
        self._options = options

    def run(self) -> None:
        try:
            result = self._db.import_ozon_orders(self._parsed, self._options)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
