"""Локальное шифрование секретов (пароль Микадо) через Windows DPAPI.

В settings.json хранится только шифротекст с префиксом, привязанный к учётной
записи/машине Windows. Если DPAPI недоступен (не Windows / нет pywin32) —
безопасный fallback в base64 с явным префиксом «plain:» (не шифрование, но и не
голый текст), чтобы поведение было предсказуемым.
"""
from __future__ import annotations

import base64

try:
    import win32crypt  # из pywin32 (уже зависимость проекта)

    _HAVE_DPAPI = True
except Exception:  # pragma: no cover - зависит от платформы
    win32crypt = None  # type: ignore[assignment]
    _HAVE_DPAPI = False

_DPAPI_PREFIX = "dpapi:"
_PLAIN_PREFIX = "plain:"
_ENTROPY = b"Dazzle/Mikado"


def is_dpapi_available() -> bool:
    return _HAVE_DPAPI


def encrypt(text: str) -> str:
    """Зашифровать строку для хранения. Пустая строка → пустая строка."""
    text = text or ""
    if not text:
        return ""
    if _HAVE_DPAPI:
        try:
            blob = win32crypt.CryptProtectData(
                text.encode("utf-8"), "Dazzle", _ENTROPY, None, None, 0
            )
            return _DPAPI_PREFIX + base64.b64encode(bytes(blob)).decode("ascii")
        except Exception:
            pass
    return _PLAIN_PREFIX + base64.b64encode(text.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Расшифровать токен из хранилища обратно в строку."""
    token = (token or "").strip()
    if not token:
        return ""
    if token.startswith(_DPAPI_PREFIX):
        if not _HAVE_DPAPI:
            return ""
        try:
            raw = base64.b64decode(token[len(_DPAPI_PREFIX):])
            _desc, data = win32crypt.CryptUnprotectData(raw, _ENTROPY, None, None, 0)
            return bytes(data).decode("utf-8")
        except Exception:
            return ""
    if token.startswith(_PLAIN_PREFIX):
        try:
            return base64.b64decode(token[len(_PLAIN_PREFIX):]).decode("utf-8")
        except Exception:
            return ""
    # Легаси/случай голого текста — вернуть как есть.
    return token
