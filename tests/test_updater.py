"""Тесты апдейтера: сравнение версий, валидация sha256/хоста, разбор manifest."""
import base64
import json

import pytest

from tirika_importer.updater import (
    UpdateError,
    UpdateInfo,
    _installer_filename,
    _is_trusted_installer_url,
    _is_valid_sha256,
    _parse_manifest_payload,
    is_newer_version,
)


def test_version_compare():
    assert is_newer_version("1.2.1", "1.2.0")
    assert not is_newer_version("1.2.0", "1.2.0")
    assert not is_newer_version("1.2", "1.2.0")   # починенный краевой случай
    assert not is_newer_version("1.2.0", "1.2")
    assert is_newer_version("1.10.0", "1.9.0")
    assert is_newer_version("2.0", "1.99.99")


def test_valid_sha256():
    assert _is_valid_sha256("a" * 64)
    assert not _is_valid_sha256("a" * 63)
    assert not _is_valid_sha256("")
    assert not _is_valid_sha256("Z" * 64)


def test_trusted_installer_url():
    assert _is_trusted_installer_url("https://github.com/o/r/releases/download/v1/Setup.exe")
    assert _is_trusted_installer_url("https://objects.githubusercontent.com/x")
    assert not _is_trusted_installer_url("http://github.com/x")           # не https
    assert not _is_trusted_installer_url("https://evil.com/Setup.exe")
    assert not _is_trusted_installer_url("https://github.com.evil.com/x")  # трюк с суффиксом


def test_parse_manifest_plain():
    payload = json.dumps({"version": "1.0", "url": "x", "sha256": "a" * 64})
    raw = _parse_manifest_payload(payload)
    assert raw["version"] == "1.0"


def test_parse_manifest_github_api():
    inner = json.dumps({"version": "1.0", "url": "x"})
    b64 = base64.b64encode(inner.encode()).decode()
    payload = json.dumps({"content": b64, "encoding": "base64"})
    raw = _parse_manifest_payload(payload)
    assert raw["version"] == "1.0"


def test_parse_manifest_invalid_json():
    with pytest.raises(UpdateError):
        _parse_manifest_payload("{ not json ")


def test_installer_filename():
    info = UpdateInfo(
        version="1.2.3",
        installer_url="https://github.com/o/r/releases/download/v1/Dazzle-Setup.exe",
    )
    assert _installer_filename(info) == "Dazzle-Setup.exe"
    info2 = UpdateInfo(version="1.2.3", installer_url="https://github.com/o/r/releases/download/v1/")
    assert _installer_filename(info2) == "Dazzle-Setup-1.2.3.exe"
