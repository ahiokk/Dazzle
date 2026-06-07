"""Тесты локального шифрования секретов (DPAPI с fallback)."""
from tirika_importer import secret_store


def test_roundtrip():
    token = secret_store.encrypt("s3cret-pw")
    assert token  # не пусто
    assert token != "s3cret-pw"  # не голый текст
    assert secret_store.decrypt(token) == "s3cret-pw"


def test_empty():
    assert secret_store.encrypt("") == ""
    assert secret_store.decrypt("") == ""


def test_unicode_roundtrip():
    secret = "Пароль-Ω-123"
    assert secret_store.decrypt(secret_store.encrypt(secret)) == secret


def test_legacy_plaintext_passthrough():
    # Токен без известного префикса трактуется как голый текст (легаси).
    assert secret_store.decrypt("legacy-plain") == "legacy-plain"
