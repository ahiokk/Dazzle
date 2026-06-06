"""Тесты ценообразования и нормализации (чистые функции из db.py)."""
from tirika_importer.db import (
    calculate_suggested_sell_price,
    normalize_article,
    normalize_text_field,
    round_up_to_step,
)


def test_round_up_to_step():
    assert round_up_to_step(120, 50) == 150
    assert round_up_to_step(150, 50) == 150
    assert round_up_to_step(151, 50) == 200
    assert round_up_to_step(0, 50) == 0
    assert round_up_to_step(100, 0) == 100  # шаг<=0 → без округления


def test_calculate_suggested_sell_price():
    assert calculate_suggested_sell_price(100, markup_percent=50, round_step=50) == 150
    assert calculate_suggested_sell_price(100, markup_percent=75, round_step=50) == 200
    assert calculate_suggested_sell_price(-10, markup_percent=50, round_step=50) == 0
    assert calculate_suggested_sell_price(100, markup_percent=30, round_step=0) == 130.0


def test_normalize_article():
    assert normalize_article(" ab-cd_12 ") == "ABCD12"
    assert normalize_article("xmil-90915") == "90915"   # снимается префикс XMIL
    assert normalize_article("") == ""
    assert len(normalize_article("A" * 40)) == 20        # обрезка до 20


def test_normalize_text_field():
    assert normalize_text_field("  a   b  ", 100) == "a b"
    assert normalize_text_field("abcdef", 3) == "abc"
