from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from .matcher import GoodsMatcher, normalize_code_alnum
from .models import MatchCandidate, OzonComponentLine, ParsedOzonCsv


OZON_REQUIRED_COLUMNS = {
    "Номер заказа",
    "Номер отправления",
    "Статус",
    "Название товара",
    "SKU",
    "Артикул",
    "Ваша цена",
    "Оплачено покупателем",
    "Количество",
}


class OzonParseError(RuntimeError):
    pass


def parse_ozon_csv(path: Path) -> ParsedOzonCsv:
    path = Path(path)
    if not path.exists():
        raise OzonParseError(f"CSV-файл не найден: {path}")

    rows = _read_csv_rows(path)
    if not rows:
        raise OzonParseError("CSV Ozon пустой.")

    headers = set(rows[0].keys())
    missing = sorted(OZON_REQUIRED_COLUMNS - headers)
    if missing:
        raise OzonParseError("CSV Ozon не похож на файл отправлений. Нет колонок: " + ", ".join(missing))

    lines: list[OzonComponentLine] = []
    orders: set[str] = set()
    postings: set[str] = set()

    for row_no, row in enumerate(rows, start=2):
        order_number = _cell(row, "Номер заказа")
        posting_number = _cell(row, "Номер отправления")
        status = _cell(row, "Статус")
        source_article = _cell(row, "Артикул")
        name = _cell(row, "Название товара")
        sku = _cell(row, "SKU")
        source_quantity = _parse_float(_cell(row, "Количество"), default=0.0)
        source_unit_price = _parse_float(_cell(row, "Ваша цена"), default=0.0)
        paid_unit_price = _parse_float(_cell(row, "Оплачено покупателем"), default=0.0)
        shipment_total = _parse_float(_cell(row, "Сумма отправления"), default=0.0)
        source_total = shipment_total if shipment_total > 0 else source_unit_price * source_quantity
        paid_total = paid_unit_price * source_quantity

        if order_number:
            orders.add(order_number)
        if posting_number:
            postings.add(posting_number)

        if not source_article and not name:
            continue

        cancelled = _is_cancelled_status(status)
        active = _is_active_order_status(status)
        article_components = _parse_article_components(source_article, source_quantity)
        if not article_components:
            article_components = [("", [], max(source_quantity, 0.0), "Не удалось разобрать артикул Ozon.")]

        for article, options, quantity, parse_warning in article_components:
            warning = parse_warning
            action = "import"
            if cancelled:
                action = "skip"
                warning = "Товар отменен"
            elif not active:
                action = "skip"
                warning = f"Статус Ozon: {status or 'не указан'}"
            elif quantity <= 0:
                action = "skip"
                warning = "Количество <= 0"

            lines.append(
                OzonComponentLine(
                    line_no=row_no,
                    order_number=order_number,
                    posting_number=posting_number,
                    status=status,
                    source_article=source_article,
                    article=article,
                    article_options=options or ([article] if article else []),
                    name=name,
                    quantity=quantity,
                    source_quantity=source_quantity,
                    source_unit_price=source_unit_price,
                    source_total=source_total,
                    paid_unit_price=paid_unit_price,
                    paid_total=paid_total,
                    sku=sku,
                    warning=warning,
                    action=action,
                )
            )

    if not lines:
        raise OzonParseError("В CSV Ozon не найдено строк товаров.")

    return ParsedOzonCsv(
        file_path=path,
        lines=lines,
        raw_rows=len(rows),
        order_count=len(orders),
        posting_count=len(postings),
    )


def match_ozon_lines(parsed: ParsedOzonCsv, matcher: GoodsMatcher) -> None:
    for line in parsed.lines:
        candidates = _find_line_candidates(line, matcher)
        line.candidates = candidates
        if len(candidates) == 1:
            cand = candidates[0]
            line.matched_good_id = cand.good_id
            line.matched_product_code = cand.product_code
            line.matched_name = cand.name
            line.matched_buy_price = cand.buy_price
            line.existing_sell_price = cand.sell_price
            line.remainder_source = cand.remainder
            line.match_method = cand.match_method
            line.match_status = "found"
            good = matcher.catalog.get(cand.good_id)
            line.matched_tax_mode = good.tax_mode if good else 0
            if line.action != "skip":
                line.action = "import"
                line.warning = ""
        elif len(candidates) > 1:
            line.match_status = "ambiguous"
            line.match_method = "exact_code_ambiguous"
            if line.action != "skip":
                line.action = "skip"
                line.warning = "Несколько товаров с таким артикулом."
        else:
            line.match_status = "not_found"
            if line.action != "skip":
                line.action = "skip"
                line.warning = "Товар не найден."

    _allocate_sale_prices(parsed.lines)


def recalculate_ozon_prices(lines: list[OzonComponentLine]) -> None:
    _allocate_sale_prices(lines)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                sample = fh.read(4096)
                fh.seek(0)
                delimiter = _detect_delimiter(sample)
                reader = csv.DictReader(fh, delimiter=delimiter)
                if not reader.fieldnames:
                    continue
                fieldnames = [_clean_header(name) for name in reader.fieldnames]
                out: list[dict[str, str]] = []
                for raw in reader:
                    cleaned: dict[str, str] = {}
                    for old_key, new_key in zip(reader.fieldnames, fieldnames):
                        cleaned[new_key] = str(raw.get(old_key, "") or "").strip()
                    out.append(cleaned)
                return out
        except Exception as exc:
            last_error = exc
    raise OzonParseError(f"Не удалось прочитать CSV Ozon: {last_error}")


def _detect_delimiter(sample: str) -> str:
    if sample.count(";") >= sample.count(","):
        return ";"
    return ","


def _clean_header(value: str | None) -> str:
    text = str(value or "").strip().lstrip("\ufeff").strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    return text


def _cell(row: dict[str, str], key: str) -> str:
    return str(row.get(key, "") or "").strip()


def _parse_float(value: str, default: float = 0.0) -> float:
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]+", "", text)
    if text in {"", "-", ".", "-."}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _is_cancelled_status(status: str) -> bool:
    text = status.strip().lower()
    return "отмен" in text or "cancel" in text


def _is_active_order_status(status: str) -> bool:
    text = status.strip().lower()
    return "ожидает" in text or "await" in text


def _parse_article_components(
    article_raw: str,
    source_quantity: float,
) -> list[tuple[str, list[str], float, str]]:
    article = str(article_raw or "").strip()
    if not article:
        return []

    article = article.split("_", 1)[0].strip()
    if not article:
        return []

    if any(sep in article for sep in ("+", ";", "|", ",")):
        parts = [p.strip() for p in re.split(r"[+;|,]+", article) if p.strip()]
        out: list[tuple[str, list[str], float, str]] = []
        for part in parts:
            out.extend(_parse_article_components(part, source_quantity))
        return out

    slash_parts = [part.strip() for part in article.split("/") if part.strip()]
    if len(slash_parts) >= 2:
        pair_components = _parse_code_quantity_pairs(slash_parts, source_quantity)
        if pair_components:
            return pair_components

        if slash_parts[-1].isdigit():
            pack_qty = int(slash_parts[-1])
            codes = slash_parts[:-1]
            if len(codes) == 1:
                code = _clean_article_code(codes[0])
                return [(code, _article_code_options(code), source_quantity * pack_qty, "")]

            if pack_qty == 1:
                options = _merge_code_options(codes)
                options = [code for code in options if code]
                return [(options[0] if options else "", options, source_quantity, "")]

            if pack_qty >= len(codes) and pack_qty % len(codes) == 0:
                each_qty = pack_qty / len(codes)
                return [
                    (
                        _clean_article_code(code),
                        _article_code_options(_clean_article_code(code)),
                        source_quantity * each_qty,
                        "",
                    )
                    for code in codes
                    if _clean_article_code(code)
                ]

            return [
                (
                    _clean_article_code(code),
                    _article_code_options(_clean_article_code(code)),
                    source_quantity,
                    "Комплект разобран без точного распределения количества.",
                )
                for code in codes
                if _clean_article_code(code)
            ]

        options = _merge_code_options(slash_parts)
        options = [code for code in options if code]
        return [(options[0] if options else "", options, source_quantity, "")]

    code = _clean_article_code(article)
    return [(code, _article_code_options(code), source_quantity, "")]


def _parse_code_quantity_pairs(
    parts: list[str],
    source_quantity: float,
) -> list[tuple[str, list[str], float, str]]:
    out: list[tuple[str, list[str], float, str]] = []
    matched = 0
    for part in parts:
        match = re.match(r"^(.+)-(\d+(?:[.,]\d+)?)$", part.strip())
        if not match:
            continue
        code = _clean_article_code(match.group(1))
        qty = _parse_float(match.group(2), default=0.0)
        if code and qty > 0:
            matched += 1
            out.append((code, _article_code_options(code), source_quantity * qty, ""))
    if matched == len(parts):
        return out
    return []


def _clean_article_code(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _article_code_options(code: str) -> list[str]:
    raw = _clean_article_code(code)
    if not raw:
        return []

    variants = [raw]
    base = raw.split("_", 1)[0].strip()
    if base and base != raw:
        variants.append(base)

    # Ozon card articles often carry a catalogue prefix, e.g. FO-SS1568,
    # RE-GM5157, CI-3250011. Tirika usually stores the real article after it.
    if "-" in base:
        left, right = base.split("-", 1)
        if 1 <= len(left) <= 4 and any(ch.isdigit() for ch in right):
            variants.append(right)

    alnum = normalize_code_alnum(base).upper()
    if alnum and alnum != base.upper():
        variants.append(alnum)

    out: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        item = _clean_article_code(variant)
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _merge_code_options(codes: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for code in codes:
        for option in _article_code_options(code):
            key = option.lower()
            if key not in seen:
                seen.add(key)
                out.append(option)
    return out


def _find_line_candidates(line: OzonComponentLine, matcher: GoodsMatcher) -> list[MatchCandidate]:
    bucket: dict[int, MatchCandidate] = {}
    options = line.article_options or ([line.article] if line.article else [])
    for option in options:
        option = option.strip()
        if not option:
            continue
        for candidate in matcher.find_exact_code_candidates(option, limit=20):
            current = bucket.get(candidate.good_id)
            if current is None or candidate.score > current.score:
                bucket[candidate.good_id] = candidate

        # Some Ozon kits use visual separators that are absent in Tirika codes.
        collapsed = normalize_code_alnum(option)
        if collapsed and collapsed != option.strip().lower():
            for candidate in matcher.find_exact_code_candidates(collapsed, limit=20):
                current = bucket.get(candidate.good_id)
                if current is None or candidate.score > current.score:
                    bucket[candidate.good_id] = candidate

    return sorted(bucket.values(), key=lambda cand: cand.score, reverse=True)


def _allocate_sale_prices(lines: list[OzonComponentLine]) -> None:
    grouped: dict[tuple[int, str, str, str], list[OzonComponentLine]] = defaultdict(list)
    for line in lines:
        key = (line.line_no, line.order_number, line.posting_number, line.source_article)
        grouped[key].append(line)

    for group_lines in grouped.values():
        if not group_lines:
            continue
        row_total = round(float(group_lines[0].source_total or 0.0), 2)
        if row_total <= 0:
            row_total = round(
                float(group_lines[0].source_unit_price or 0.0) * float(group_lines[0].source_quantity or 0.0),
                2,
            )

        weights: list[float] = []
        for line in group_lines:
            price_weight = float(line.existing_sell_price or 0.0)
            if price_weight <= 0:
                price_weight = 1.0
            weights.append(max(0.0, line.quantity) * price_weight)
        total_weight = sum(weights)
        if total_weight <= 0:
            weights = [1.0 for _ in group_lines]
            total_weight = float(len(group_lines))

        allocated = 0.0
        for idx, line in enumerate(group_lines):
            if idx == len(group_lines) - 1:
                line_total = round(row_total - allocated, 2)
            else:
                line_total = round(row_total * (weights[idx] / total_weight), 2)
                allocated += line_total
            line.sale_total = line_total
            if line.quantity > 0:
                line.sale_price = round(line_total / line.quantity, 2)
            else:
                line.sale_price = 0.0
