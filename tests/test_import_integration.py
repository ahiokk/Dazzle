"""Интеграционный тест ЗАПИСИ в базу Tirika: работает на КОПИИ базы.

Самый рискованный модуль — db.py: он пишет в боевую shop.db магазина.
Раньше его покрывало только чтение каталога, поэтому реальный импорт
(документ, остатки, цены, кросс-коды) не проверялся ничем.

База берётся из db_examples/ (копии для опытов, в .gitignore), а если их нет —
из установленной Tirika. Если недоступно ни то, ни другое, тест пропускается.
Оригинал не мутируется: всё делается на копии в tmp_path.
"""
import shutil
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_DBS = [
    PROJECT_ROOT / "db_examples" / "win 10.db",
    PROJECT_ROOT / "db_examples" / "win 7.db",
    Path(r"C:\Program Files (x86)\Tirika Shop\shop.db"),
]


def _source_db() -> Path | None:
    for path in CANDIDATE_DBS:
        if path.exists():
            return path
    return None


pytestmark = pytest.mark.skipif(
    _source_db() is None, reason="нет базы Tirika для интеграционного теста"
)


@pytest.fixture
def db(tmp_path):
    from tirika_importer.db import TirikaDB

    source = _source_db()
    copy = tmp_path / "shop_copy.db"
    shutil.copy2(source, copy)
    return TirikaDB(copy)


def _shop_id(db) -> int:
    shops = db.list_shops()
    return shops[0][0] if shops else 0


def _options(shop_id: int, *, dry_run: bool):
    from tirika_importer.models import ImportOptions

    return ImportOptions(
        supplier_id=1,
        user_id=1,
        shop_id=shop_id,
        payment_type=-1,
        dry_run=dry_run,
        create_missing_goods=True,
        update_existing_goods_fields=False,
        update_goods_buy_price=True,
        backup_before_import=False,  # копию уже сделал fixture
        auto_pay=False,
    )


def _invoice(tmp_path, lines):
    from tirika_importer.models import ParsedInvoice

    return ParsedInvoice(
        file_path=tmp_path / "Invoice.xls",
        supplier_hint="МИКАДО",
        source_type="mikado_html",
        lines=lines,
        invoice_number="TEST-1",
    )


def _line(line_no, article, name, *, quantity, price, sell_price, good=None, action="import"):
    from tirika_importer.models import InvoiceLine

    line = InvoiceLine(
        line_no=line_no,
        article=article,
        name=name,
        note="",
        quantity=quantity,
        price=price,
        total=round(quantity * price, 2),
        source_supplier="МИКАДО",
    )
    line.action = action
    line.sell_price = sell_price
    if good is not None:
        line.match_status = "exact"
        line.matched_good_id = good.good_id
        line.matched_product_code = good.product_code
        line.matched_name = good.name
        line.matched_buy_price = good.buy_price
        line.existing_sell_price = good.sell_price
    return line


def test_import_creates_good_with_cross_codes_and_moves_remainder(db, tmp_path):
    """Полный проход импорта: документ, остаток, новый товар и его кроссы."""
    shop_id = _shop_id(db)
    catalog = db.load_goods_catalog(shop_id)
    assert catalog, "каталог пустой — тест бессмыслен"

    existing = next(iter(catalog.values()))
    before_remainder = existing.remainder

    new_article = f"DZLTEST{uuid.uuid4().hex[:8].upper()}"
    invoice = _invoice(
        tmp_path,
        [
            _line(1, existing.product_code, existing.name, quantity=2, price=100.0,
                  sell_price=250.0, good=existing),
            _line(2, new_article, "Тестовый товар Dazzle", quantity=3, price=200.0,
                  sell_price=500.0, action="create"),
        ],
    )

    result = db.import_invoice(invoice, _options(shop_id, dry_run=False))

    assert result.success
    assert result.dry_run is False
    assert result.waybill_id is not None
    assert result.imported_lines == 2
    assert result.created_goods == 1
    assert result.total_cost == pytest.approx(2 * 100.0 + 3 * 200.0)

    after = db.load_goods_catalog(shop_id)

    # Остаток существующего товара вырос ровно на количество из накладной.
    assert after[existing.good_id].remainder == pytest.approx(before_remainder + 2)

    # Новый товар создан, с остатком и ценами из накладной.
    created = [g for g in after.values() if g.product_code == new_article]
    assert len(created) == 1, "новый товар должен создаться ровно один раз"
    created_good = created[0]
    assert created_good.remainder == pytest.approx(3)
    assert created_good.buy_price == pytest.approx(200.0)
    assert created_good.sell_price == pytest.approx(500.0)

    # Кросс-коды: маркер Dazzle и сам артикул (по нему товар найдётся в
    # следующей накладной, даже если основной код заведут иначе).
    crosses = [c.strip().lower() for c in created_good.cross_codes]
    assert any(c.startswith("dazzle-auto-made-from") for c in crosses), crosses
    assert new_article.lower() in crosses, crosses


def test_dry_run_changes_nothing(db, tmp_path):
    """Проверка не должна трогать базу — на этом держится доверие к кнопке."""
    shop_id = _shop_id(db)
    catalog = db.load_goods_catalog(shop_id)
    existing = next(iter(catalog.values()))
    before_remainder = existing.remainder
    before_count = len(catalog)

    new_article = f"DZLDRY{uuid.uuid4().hex[:8].upper()}"
    invoice = _invoice(
        tmp_path,
        [
            _line(1, existing.product_code, existing.name, quantity=5, price=100.0,
                  sell_price=250.0, good=existing),
            _line(2, new_article, "Товар из dry-run", quantity=1, price=300.0,
                  sell_price=700.0, action="create"),
        ],
    )

    result = db.import_invoice(invoice, _options(shop_id, dry_run=True))

    assert result.success
    assert result.dry_run is True

    after = db.load_goods_catalog(shop_id)
    assert len(after) == before_count
    assert after[existing.good_id].remainder == pytest.approx(before_remainder)
    assert not [g for g in after.values() if g.product_code == new_article]


def test_skip_line_is_not_written_while_the_rest_imports(db, tmp_path):
    """Соседняя строка импортируется, а помеченная skip остаётся нетронутой."""
    shop_id = _shop_id(db)
    catalog = db.load_goods_catalog(shop_id)
    goods = list(catalog.values())
    if len(goods) < 2:
        pytest.skip("в каталоге меньше двух товаров")

    imported_good, skipped_good = goods[0], goods[1]
    before_imported = imported_good.remainder
    before_skipped = skipped_good.remainder

    invoice = _invoice(
        tmp_path,
        [
            _line(1, imported_good.product_code, imported_good.name, quantity=4,
                  price=100.0, sell_price=250.0, good=imported_good),
            _line(2, skipped_good.product_code, skipped_good.name, quantity=7,
                  price=100.0, sell_price=250.0, good=skipped_good, action="skip"),
        ],
    )

    result = db.import_invoice(invoice, _options(shop_id, dry_run=False))

    assert result.imported_lines == 1
    assert result.skipped_lines == 1
    assert result.total_cost == pytest.approx(4 * 100.0)

    after = db.load_goods_catalog(shop_id)
    assert after[imported_good.good_id].remainder == pytest.approx(before_imported + 4)
    assert after[skipped_good.good_id].remainder == pytest.approx(before_skipped)


def test_import_of_only_skipped_lines_is_rejected(db, tmp_path):
    """Документ из одних пропусков не создаётся — писать в базу нечего."""
    from tirika_importer.db import ImportValidationError

    shop_id = _shop_id(db)
    existing = next(iter(db.load_goods_catalog(shop_id).values()))
    invoice = _invoice(
        tmp_path,
        [
            _line(1, existing.product_code, existing.name, quantity=7, price=100.0,
                  sell_price=250.0, good=existing, action="skip"),
        ],
    )

    with pytest.raises(ImportValidationError):
        db.import_invoice(invoice, _options(shop_id, dry_run=False))
