"""Редакции сборки: AUTO255 / Lastochka / VAG."""
import pytest

from tirika_importer import version
from tirika_importer.app_settings import (
    default_article_match_field,
    default_update_manifest_url,
)
from tirika_importer.version import (
    EDITION_AUTO255,
    EDITION_LASTOCHKA,
    EDITION_VAG,
    current_edition,
    is_win7_build,
    ozon_enabled,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DAZZLE_EDITION", raising=False)
    monkeypatch.delenv("DAZZLE_UPDATE_CHANNEL", raising=False)


def test_default_edition_is_auto255(monkeypatch):
    monkeypatch.setattr(version.sys, "executable", r"C:\Python\python.exe")
    assert current_edition().key == EDITION_AUTO255
    assert ozon_enabled() is True
    assert is_win7_build() is False


def test_edition_from_env(monkeypatch):
    monkeypatch.setenv("DAZZLE_EDITION", "vag")
    assert current_edition().key == EDITION_VAG
    assert ozon_enabled() is False
    assert is_win7_build() is False
    assert default_article_match_field() == "product_code"
    assert default_update_manifest_url().endswith("latest-vag.json?ref=main")


def test_legacy_win7_channel_maps_to_lastochka(monkeypatch):
    monkeypatch.setenv("DAZZLE_UPDATE_CHANNEL", "win7")
    assert current_edition().key == EDITION_LASTOCHKA
    assert ozon_enabled() is False
    assert is_win7_build() is True
    assert default_article_match_field() == "barcode"
    assert default_update_manifest_url().endswith("latest-win7.json?ref=main")


@pytest.mark.parametrize(
    "exe_name,expected",
    [
        (r"C:\Programs\Dazzle\Dazzle.exe", EDITION_AUTO255),
        (r"C:\Programs\Dazzle Win7\DazzleWin7.exe", EDITION_LASTOCHKA),
        (r"C:\Programs\Dazzle VAG\DazzleVAG.exe", EDITION_VAG),
    ],
)
def test_edition_from_exe_name(monkeypatch, exe_name, expected):
    monkeypatch.setattr(version.sys, "executable", exe_name)
    assert current_edition().key == expected


def test_every_edition_has_own_update_manifest():
    manifests = {e.manifest_file for e in version.EDITIONS.values()}
    assert len(manifests) == len(version.EDITIONS)
