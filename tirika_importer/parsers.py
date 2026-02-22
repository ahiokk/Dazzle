from __future__ import annotations

import re
import contextlib
import io
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from .models import InvoiceLine, ParsedInvoice

NOTE_COLUMN_NEEDLES = ["примеч", "прим.", "коммент", "note", "remark"]

try:
    import win32com.client  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    win32com = None  # type: ignore[assignment]


class InvoiceParseError(RuntimeError):
    pass


@dataclass(slots=True)
class ParsedTable:
    headers: list[str]
    rows: list[list[Any]]


def parse_invoice_file(path: Path) -> ParsedInvoice:
    if not path.exists():
        raise InvoiceParseError(f"Файл не найден: {path}")

    if _looks_like_html(path):
        return _parse_mikado_html(path)

    return _parse_akvilon_excel(path)


def _looks_like_html(path: Path) -> bool:
    head = path.read_bytes()[:4096].lower()
    return b"<html" in head or b"<table" in head


def _parse_mikado_html(path: Path) -> ParsedInvoice:
    text = path.read_text(encoding="cp1251", errors="ignore")
    try:
        tables = pd.read_html(StringIO(text))
    except ValueError as exc:
        raise InvoiceParseError(f"Не удалось разобрать HTML-накладную: {exc}") from exc

    if not tables:
        raise InvoiceParseError("В файле нет таблиц с данными.")

    df = tables[0]
    cols = [str(c).strip() for c in df.columns]

    code_col = _find_col(cols, ["код", "артикул"])
    qty_col = _find_col(cols, ["к-во", "кол"])
    price_col = _find_col(cols, ["цена"])
    sum_col = _find_col(cols, ["сумма"])
    name_col = _find_col(cols, ["название", "наименование"])
    note_cols = _find_cols(cols, NOTE_COLUMN_NEEDLES)

    if code_col is None or qty_col is None or price_col is None:
        raise InvoiceParseError(
            "Не удалось определить обязательные колонки для Микадо (код/кол-во/цена)."
        )

    invoice_number, invoice_date = _extract_invoice_header(text)

    lines: list[InvoiceLine] = []
    for idx, row in df.iterrows():
        article = _clean_article(row.iloc[code_col], source_type="mikado_html")
        name = _clean_text(row.iloc[name_col]) if name_col is not None else ""
        note = _extract_note_from_row(row.tolist(), note_cols)
        if not article or "итого" in article.lower():
            continue
        if not _looks_like_article(article):
            continue

        qty = _to_float(row.iloc[qty_col])
        price = _to_float(row.iloc[price_col])
        total = _to_float(row.iloc[sum_col]) if sum_col is not None else round(qty * price, 2)

        line = InvoiceLine(
            line_no=len(lines) + 1,
            article=article,
            name=name,
            note=note,
            quantity=qty,
            price=price,
            total=total,
            source_supplier="МИКАДО",
            raw_data={k: _clean_text(v) for k, v in row.to_dict().items()},
        )
        lines.append(line)

    if not lines:
        raise InvoiceParseError("Не найдено строк с товарами в накладной Микадо.")

    return ParsedInvoice(
        file_path=path,
        supplier_hint="МИКАДО",
        source_type="mikado_html",
        lines=lines,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
    )


def _parse_akvilon_excel(path: Path) -> ParsedInvoice:
    table = _read_excel_table(path)
    if not table.headers:
        raise InvoiceParseError("В файле нет заголовка таблицы.")

    headers = table.headers
    code_col = _find_col(headers, ["код детали", "код"])
    qty_col = _find_col(headers, ["кол-во", "кол"])
    price_col = _find_col(headers, ["цена"])
    sum_col = _find_col(headers, ["сумма"])
    name_col = _find_col(headers, ["описание", "наименование"])
    status_col = _find_col(headers, ["статус"])
    note_cols = _find_cols(headers, NOTE_COLUMN_NEEDLES)

    if code_col is None or qty_col is None or price_col is None:
        raise InvoiceParseError(
            "Не удалось определить обязательные колонки для Аквилон (код/кол-во/цена)."
        )

    lines: list[InvoiceLine] = []
    for row in table.rows:
        article = _clean_article(row[code_col], source_type="akvilon_excel") if code_col < len(row) else ""
        if not article:
            continue
        if not _looks_like_article(article):
            continue

        name = _clean_text(row[name_col]) if name_col is not None and name_col < len(row) else ""
        name = _fix_mojibake(name)
        note = _extract_note_from_row(row, note_cols)
        note = _fix_mojibake(note)

        qty = _to_float(row[qty_col]) if qty_col < len(row) else 0.0
        price = _to_float(row[price_col]) if price_col < len(row) else 0.0
        total = (
            _to_float(row[sum_col])
            if sum_col is not None and sum_col < len(row)
            else round(qty * price, 2)
        )
        status = (
            _clean_text(row[status_col])
            if status_col is not None and status_col < len(row)
            else ""
        )

        warning = ""
        if status and status.lower() not in {"выдано"}:
            warning = f"Статус строки: {status}"

        line = InvoiceLine(
            line_no=len(lines) + 1,
            article=article,
            name=name,
            note=note,
            quantity=qty,
            price=price,
            total=total,
            source_supplier="АКВИЛОН",
            warning=warning,
            raw_data={"status": status, "note": note},
        )
        lines.append(line)

    if not lines:
        raise InvoiceParseError("Не найдено строк с товарами в файле Аквилон.")

    return ParsedInvoice(
        file_path=path,
        supplier_hint="АКВИЛОН",
        source_type="akvilon_excel",
        lines=lines,
    )


def _read_excel_table(path: Path) -> ParsedTable:
    try:
        # xlrd can print corruption diagnostics to stdout/stderr; silence it
        # and fallback to COM parser when needed.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = pd.read_excel(path)
        headers = [str(c).strip() for c in df.columns]
        rows = [[v for v in row] for row in df.itertuples(index=False, name=None)]
        return ParsedTable(headers=headers, rows=rows)
    except Exception:
        pass

    return _read_excel_table_via_com(path)


def _read_excel_table_via_com(path: Path) -> ParsedTable:
    if win32com is None:
        raise InvoiceParseError(
            "Файл Excel не удалось прочитать через pandas/xlrd, а win32com недоступен."
        )

    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")  # type: ignore[union-attr]
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Open(str(path.resolve()), ReadOnly=True)
        sheet = workbook.Worksheets(1)
        used = sheet.UsedRange
        rows = used.Rows.Count
        cols = used.Columns.Count

        headers: list[str] = []
        raw_rows: list[list[Any]] = []

        for c in range(1, cols + 1):
            headers.append(_clean_text(sheet.Cells(1, c).Value))

        for r in range(2, rows + 1):
            row: list[Any] = []
            non_empty = False
            for c in range(1, cols + 1):
                val = sheet.Cells(r, c).Value
                row.append(val)
                if val not in (None, ""):
                    non_empty = True
            if non_empty:
                raw_rows.append(row)
        return ParsedTable(headers=headers, rows=raw_rows)
    except Exception as exc:
        raise InvoiceParseError(f"Не удалось прочитать Excel через COM: {exc}") from exc
    finally:
        if workbook is not None:
            workbook.Close(SaveChanges=False)
        if excel is not None:
            excel.Quit()


def _find_col(cols: list[str], needles: list[str]) -> int | None:
    normalized = [c.lower().strip() for c in cols]
    for needle in needles:
        for idx, col in enumerate(normalized):
            if needle in col:
                return idx
    return None


def _find_cols(cols: list[str], needles: list[str]) -> list[int]:
    normalized = [c.lower().strip() for c in cols]
    found: list[int] = []
    for idx, col in enumerate(normalized):
        if any(needle in col for needle in needles):
            found.append(idx)
    return found


def _extract_note_from_row(row: list[Any], note_cols: list[int]) -> str:
    if not note_cols:
        return ""
    notes: list[str] = []
    for col_idx in note_cols:
        if col_idx < 0 or col_idx >= len(row):
            continue
        val = _clean_text(row[col_idx])
        if not val:
            continue
        val_lower = val.lower()
        if val_lower in {"итого", "итого:", "итог", "итог:"}:
            continue
        notes.append(val)
    if not notes:
        return ""
    # Keep source column order, avoid duplicate repeated values.
    unique_notes = list(dict.fromkeys(notes))
    return " | ".join(unique_notes)


def _extract_invoice_header(text: str) -> tuple[str, datetime | None]:
    number = ""
    date_value: datetime | None = None

    m_number = re.search(r"накладн\w*\s*№\s*([0-9A-Za-z\-_/]+)", text, re.IGNORECASE)
    if m_number:
        number = m_number.group(1).strip()

    m_date = re.search(r"от\s*([0-3]?\d/[0-1]?\d/[12]\d{3})", text, re.IGNORECASE)
    if m_date:
        raw_date = m_date.group(1).strip()
        try:
            date_value = datetime.strptime(raw_date, "%d/%m/%Y")
        except ValueError:
            date_value = None
    return number, date_value


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if text.lower() == "nan":
        return ""
    return text


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value)
    if not text:
        return 0.0
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _looks_like_article(article: str) -> bool:
    clean = article.strip().lower()
    if not clean:
        return False
    if clean.startswith("итого"):
        return False
    if re.fullmatch(r"[0-9]+[.,][0-9]+", clean):
        return False
    return True


def _fix_mojibake(text: str) -> str:
    if not text:
        return text
    if "Р" not in text and "С" not in text:
        return text
    try:
        return text.encode("cp1251").decode("utf-8")
    except Exception:
        return text


def _clean_article(value: Any, *, source_type: str = "") -> str:
    if isinstance(value, float) and value.is_integer():
        return _normalize_article(str(int(value)), source_type=source_type)
    text = _clean_text(value)
    if re.fullmatch(r"[0-9]+\.0+", text):
        text = text.split(".", 1)[0]
    return _normalize_article(text, source_type=source_type)


def _normalize_article(value: str, *, source_type: str = "") -> str:
    text = value.strip()
    if not text:
        return ""
    if source_type == "mikado_html":
        # In Mikado invoices the first segment before '-' is a warehouse code.
        # Example: xqwe-GM-1104 -> GM-1104.
        if "-" in text:
            text = text.split("-", 1)[1]
    # Legacy known Mikado prefixes.
    text = re.sub(r"^(xmil|xzk)\s*[-_ ]*", "", text, flags=re.IGNORECASE)
    text = text.replace("\t", "")
    text = re.sub(r"[\s\-]+", "", text)
    return text.upper()
