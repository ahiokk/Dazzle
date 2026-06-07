"""Тесты вспомогательных функций парсера накладных."""
from tirika_importer.parsers import _find_col, _find_cols, _looks_like_html


def test_find_col():
    cols = ["Код товара", "Наименование", "Кол-во", "Цена"]
    assert _find_col(cols, ["код"]) == 0
    assert _find_col(cols, ["артикул", "код"]) == 0   # первый подходящий needle
    assert _find_col(cols, ["цена"]) == 3
    assert _find_col(cols, ["такого нет"]) is None


def test_find_cols():
    cols = ["Примечание", "Комментарий", "Цена"]
    assert _find_cols(cols, ["примеч", "коммент"]) == [0, 1]


def test_ozon_special_set_recipe_gm5197_gm5198():
    """«GM5197/GM5198/6»: 6 — общее кол-во; раскладка GM5197×2 + GM5198×4
    (только для этого товара), масштабируется числом проданных комплектов."""
    from tirika_importer.ozon import _parse_article_components

    qty = {c: q for c, _opts, q, _w in _parse_article_components("GM5197/GM5198/6", 1.0)}
    assert qty == {"GM5197": 2.0, "GM5198": 4.0}

    qty3 = {c: q for c, _opts, q, _w in _parse_article_components("GM5197/GM5198/6", 3.0)}
    assert qty3 == {"GM5197": 6.0, "GM5198": 12.0}


def test_looks_like_html(tmp_path):
    p = tmp_path / "invoice.xls"
    p.write_bytes(b"<html><table><tr><td>1</td></tr></table></html>")
    assert _looks_like_html(p)

    p2 = tmp_path / "binary.xls"
    p2.write_bytes(b"PK\x03\x04 binary xlsx zip header, not html")
    assert not _looks_like_html(p2)
