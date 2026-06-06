"""Интеграционный тест чтения каталога: работает на КОПИИ реальной shop.db
(реальная база не мутируется). Пропускается, если базы нет на машине.
"""
import shutil
from pathlib import Path

import pytest

SHOP_DB = Path(r"C:\Program Files (x86)\Tirika Shop\shop.db")


@pytest.mark.skipif(not SHOP_DB.exists(), reason="shop.db недоступна на этой машине")
def test_load_catalog_and_build_matcher(tmp_path):
    from tirika_importer.db import TirikaDB
    from tirika_importer.matcher import GoodsMatcher

    copy = tmp_path / "shop_copy.db"
    shutil.copy2(SHOP_DB, copy)

    db = TirikaDB(copy)
    shops = db.list_shops()
    shop_id = shops[0][0] if shops else 0

    catalog = db.load_goods_catalog(shop_id)
    assert isinstance(catalog, dict)

    # Матчер строится по реальному каталогу без ошибок.
    matcher = GoodsMatcher(catalog)
    assert matcher is not None
