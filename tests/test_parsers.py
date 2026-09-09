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


def _write_ozon_csv(path, price_header):
    """Мини-выгрузка отправлений Ozon с одной товарной строкой."""
    headers = [
        "Номер заказа", "Номер отправления", "Статус", "Сумма отправления",
        "Название товара", "SKU", "Артикул", price_header,
        "Оплачено покупателем", "Количество",
    ]
    values = [
        "75756470-0645", "75756470-0645-1", "Ожидает сборки", "1058.00",
        "Комплект тормозных колодок", "842425235", "BR14961", "1058.00",
        "531.43", "1",
    ]
    text = ";".join('"%s"' % h for h in headers) + "\n" + ";".join('"%s"' % v for v in values) + "\n"
    path.write_text(text, encoding="utf-8-sig")
    return path


def test_ozon_accepts_both_price_column_names(tmp_path):
    """Ozon переименовал «Ваша цена» в «Предельная цена» — грузим оба варианта."""
    from tirika_importer.ozon import parse_ozon_csv

    for header in ("Ваша цена", "Предельная цена"):
        parsed = parse_ozon_csv(_write_ozon_csv(tmp_path / "postings.csv", header))
        assert len(parsed.lines) == 1, header
        line = parsed.lines[0]
        assert line.article == "BR14961"
        assert line.source_unit_price == 1058.0
        assert line.paid_unit_price == 531.43
        assert line.action == "import"


def test_ozon_without_any_price_column_reports_both_names(tmp_path):
    from tirika_importer.ozon import OzonParseError, parse_ozon_csv

    path = _write_ozon_csv(tmp_path / "postings.csv", "Какая-то чужая колонка")
    try:
        parse_ozon_csv(path)
    except OzonParseError as exc:
        assert "Ваша цена / Предельная цена" in str(exc)
    else:
        raise AssertionError("ожидали OzonParseError")


def _write_mikado_html(path, headers, row):
    """Накладная Микадо — это HTML с расширением .xls."""
    head = "".join("<TH>%s</TH>" % h for h in headers)
    body = "".join("<TD>%s</TD>" % c for c in row)
    path.write_text(
        "<html><head></head><body><TABLE border=1>"
        "<H3>Накладная №<b>6062203</b> от <b>07/09/2026г.</b></h3>"
        "<TABLE border=1><TR>%s</TR><TR>%s</TR></TABLE></body></html>" % (head, body),
        encoding="cp1251",
    )
    return path


MIKADO_FULL = ["Nпп", "Примеч", "*", "Код", "К-во", "Цена", "Сумма", "Название", "Прим."]
MIKADO_ROW_FULL = ["1", "&nbsp;", "*", "xzk-bs-1600", "1", "826.44", "826.44", "Колодки", "&nbsp;"]

# Так Микадо выгрузил накладную 08.09.2026: колонки с названием нет вовсе.
MIKADO_NO_NAME = ["Nпп", "Примеч", "*", "Код", "К-во", "Цена", "Сумма", "Прим."]
MIKADO_ROW_NO_NAME = ["1", "&nbsp;", "*", "xzk-bs-1600", "1", "826.44", "826.44", "&nbsp;"]


def test_mikado_invoice_without_name_column_warns(tmp_path):
    from tirika_importer.parsers import parse_invoice_file

    path = _write_mikado_html(tmp_path / "Invoice.xls", MIKADO_NO_NAME, MIKADO_ROW_NO_NAME)
    invoice = parse_invoice_file(path)

    assert len(invoice.lines) == 1
    assert invoice.lines[0].article == "BS1600"      # строка всё равно читается
    assert invoice.lines[0].name == ""
    assert len(invoice.parse_warnings) == 1
    assert "нет колонки с названием" in invoice.parse_warnings[0]


def test_mikado_normal_invoice_has_no_parse_warnings(tmp_path):
    from tirika_importer.parsers import parse_invoice_file

    path = _write_mikado_html(tmp_path / "Invoice.xls", MIKADO_FULL, MIKADO_ROW_FULL)
    invoice = parse_invoice_file(path)

    assert invoice.lines[0].name == "Колодки"
    assert invoice.parse_warnings == []
