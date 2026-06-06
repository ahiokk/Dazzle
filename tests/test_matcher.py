"""Тесты сопоставления товаров (matcher.py)."""
import pytest

from tirika_importer.db import GoodRecord
from tirika_importer.matcher import GoodsMatcher, build_article_variants, normalize_name
from tirika_importer.models import InvoiceLine


def good(gid, code, name, **kw):
    return GoodRecord(
        good_id=gid,
        product_code=code,
        name=name,
        manufacturer=kw.get("manufacturer", ""),
        buy_price=kw.get("buy_price", 0.0),
        sell_price=kw.get("sell_price", 0.0),
        tax_mode=kw.get("tax_mode", 0),
        supplier_id=kw.get("supplier_id", 0),
        remainder=kw.get("remainder", 0.0),
        cross_codes=kw.get("cross_codes", []),
        barcodes=kw.get("barcodes", []),
    )


def line(article="", name="", price=100.0):
    return InvoiceLine(
        line_no=1, article=article, name=name, note="",
        quantity=1.0, price=price, total=price, source_supplier="test",
    )


def make_clean():
    catalog = {
        1: good(1, "90915-YZZD4", "Фильтр масляный Toyota",
                sell_price=470, cross_codes=["W7015"], barcodes=["4607000000017"]),
        2: good(2, "BOSCH0986", "Свеча зажигания Bosch", sell_price=310),
    }
    return GoodsMatcher(catalog)


def test_exact_code_match():
    m = make_clean()
    ln = line(article="90915-YZZD4", name="что угодно")
    m.match_line(ln)
    assert ln.match_status == "exact"
    assert ln.matched_good_id == 1
    assert ln.action == "import"


def test_cross_code_match():
    m = make_clean()
    ln = line(article="W7015")
    m.match_line(ln)
    assert ln.matched_good_id == 1


def test_barcode_match():
    m = make_clean()
    ln = line(article="4607000000017")
    m.match_line(ln)
    assert ln.matched_good_id == 1


def test_not_found_creates():
    m = make_clean()
    ln = line(article="ZZZ999", name="неведомая хрумбель детальная")
    m.match_line(ln)
    assert ln.match_status == "not_found"
    assert ln.action == "create"
    assert ln.matched_good_id is None


def test_ambiguous_code():
    catalog = {1: good(1, "DUP1", "Первый"), 2: good(2, "DUP1", "Второй")}
    m = GoodsMatcher(catalog)
    ln = line(article="DUP1")
    m.match_line(ln)
    assert ln.match_status == "ambiguous"
    assert ln.action == "skip"
    assert ln.matched_good_id is None


def test_name_fallback():
    m = make_clean()
    ln = line(article="", name="Свеча зажигания Bosch")
    m.match_line(ln)
    assert ln.matched_good_id == 2
    assert ln.match_status == "fuzzy"


def test_apply_manual_good():
    m = make_clean()
    ln = line(article="NOPE", name="x")
    m.match_line(ln)
    m.apply_manual_good(ln, 2)
    assert ln.matched_good_id == 2
    assert ln.match_status == "manual"
    assert ln.action == "import"


def test_apply_manual_good_invalid():
    m = make_clean()
    with pytest.raises(ValueError):
        m.apply_manual_good(line(), 999)


def test_normalize_name():
    assert normalize_name("  Фильтр,  МАСЛЯНЫЙ! ") == "фильтр масляный"


def test_build_article_variants_strips_prefix():
    variants = build_article_variants("XMIL-90915")
    assert "90915" in variants
