from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class UpdateError(RuntimeError):
    pass


@dataclass
class UpdateInfo:
    version: str
    installer_url: str
    sha256: str = ""
    notes: str = ""
    release_page_url: str = ""


# Установщик принимаем только с доверенных хостов по HTTPS (цепочка релизов на GitHub).
_TRUSTED_HOST_SUFFIXES = ("github.com", "githubusercontent.com")


def _is_trusted_installer_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in _TRUSTED_HOST_SUFFIXES)


def _is_valid_sha256(value: str) -> bool:
    v = (value or "").strip().lower()
    return len(v) == 64 and all(c in "0123456789abcdef" for c in v)


def check_for_update(current_version: str, manifest_url: str, timeout_sec: float = 20.0) -> UpdateInfo | None:
    url = manifest_url.strip()
    if not url:
        return None

    manifest = _fetch_manifest(url, timeout_sec=timeout_sec)
    version = str(manifest.get("version", "")).strip()
    installer_url_raw = str(manifest.get("url", "")).strip()
    if not version or not installer_url_raw:
        raise UpdateError("В manifest нет обязательных полей: version и url.")

    installer_url = urljoin(url, installer_url_raw)
    if not _is_trusted_installer_url(installer_url):
        raise UpdateError(
            "URL установщика не на доверенном хосте (ожидается github.com / "
            f"githubusercontent.com по HTTPS): {installer_url}"
        )
    sha256 = str(manifest.get("sha256", "")).strip().lower()
    if not _is_valid_sha256(sha256):
        raise UpdateError(
            "В manifest нет корректного sha256 установщика — обновление отклонено "
            "в целях безопасности. Добавьте поле sha256 (64 hex) в latest.json."
        )
    info = UpdateInfo(
        version=version,
        installer_url=installer_url,
        sha256=sha256,
        notes=str(manifest.get("notes", "")).strip(),
        release_page_url=str(manifest.get("release_page_url", "")).strip(),
    )
    if not is_newer_version(info.version, current_version):
        return None
    return info


def download_installer(
    update: UpdateInfo,
    target_dir: Path,
    timeout_sec: float = 90.0,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    name = _installer_filename(update)
    final_path = target_dir / name
    temp_path = target_dir / f"{name}.part"

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        req = Request(update.installer_url, headers={"User-Agent": "Dazzle-Updater/1.0"})
        try:
            with urlopen(req, timeout=timeout_sec) as resp, temp_path.open("wb") as out:
                total_raw = resp.headers.get("Content-Length", "").strip()
                total_bytes = int(total_raw) if total_raw.isdigit() else 0
                downloaded = 0
                if progress_cb is not None:
                    progress_cb(0, total_bytes)
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb is not None:
                        progress_cb(downloaded, total_bytes)
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(1.2 * attempt)
                continue
    if last_exc is not None:
        raise UpdateError(f"Не удалось скачать обновление: {last_exc}") from last_exc

    if not _is_valid_sha256(update.sha256):
        temp_path.unlink(missing_ok=True)
        raise UpdateError("Обновление без корректного sha256 отклонено в целях безопасности.")
    actual = sha256_file(temp_path)
    if actual.lower() != update.sha256.lower():
        temp_path.unlink(missing_ok=True)
        raise UpdateError(
            "Проверка SHA256 не пройдена. "
            f"Ожидался: {update.sha256}, получен: {actual}."
        )

    if final_path.exists():
        final_path.unlink(missing_ok=True)
    temp_path.replace(final_path)
    return final_path


def run_installer(
    installer_path: Path,
    *,
    relaunch_executable: Path | None = None,
) -> None:
    if not installer_path.exists():
        raise UpdateError(f"Файл установщика не найден: {installer_path}")

    try:
        args = _installer_args(installer_path)
        if relaunch_executable is None:
            subprocess.Popen(args)
            return

        _run_installer_with_relaunch(args, relaunch_executable)
    except Exception as exc:
        raise UpdateError(f"Не удалось запустить установщик: {exc}") from exc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def is_newer_version(candidate: str, current: str) -> bool:
    a = _version_tuple(candidate)
    b = _version_tuple(current)
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return a > b


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    if not parts:
        return (0,)
    out = tuple(int(x) for x in parts)
    return out


def _installer_filename(update: UpdateInfo) -> str:
    parsed = urlparse(update.installer_url)
    name = Path(parsed.path).name.strip()
    if name.lower().endswith(".exe") and name:
        return name
    return f"Dazzle-Setup-{update.version}.exe"


def _fetch_manifest(manifest_url: str, timeout_sec: float) -> dict[str, object]:
    urls = _manifest_candidate_urls(manifest_url)
    last_exc: Exception | None = None
    for url in urls:
        for attempt in range(1, 4):
            req = Request(url, headers={"User-Agent": "Dazzle-Updater/1.0"})
            try:
                with urlopen(req, timeout=timeout_sec) as resp:
                    payload = resp.read().decode("utf-8-sig")
                raw = _parse_manifest_payload(payload)
                if not isinstance(raw, dict):
                    raise UpdateError("Manifest должен быть JSON-объектом.")
                return raw
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    time.sleep(0.8 * attempt)
                    continue
    raise UpdateError(f"Не удалось получить manifest обновлений: {last_exc}") from last_exc


def _parse_manifest_payload(payload: str) -> dict[str, object]:
    try:
        raw = json.loads(payload.lstrip("\ufeff"))
    except Exception as exc:
        raise UpdateError(f"Manifest обновлений не является валидным JSON: {exc}") from exc

    # GitHub Contents API response format:
    # { "content": "<base64>", "encoding": "base64", ... }
    if isinstance(raw, dict) and "content" in raw and "encoding" in raw and "version" not in raw:
        try:
            encoded = str(raw.get("content", "") or "")
            decoded = base64.b64decode(encoded, validate=False).decode("utf-8-sig")
            raw = json.loads(decoded.lstrip("\ufeff"))
        except Exception as exc:
            raise UpdateError(f"Не удалось разобрать manifest из GitHub API: {exc}") from exc

    if not isinstance(raw, dict):
        raise UpdateError("Manifest должен быть JSON-объектом.")
    return raw


def _manifest_candidate_urls(manifest_url: str) -> list[str]:
    url = manifest_url.strip()
    if not url:
        return []

    out: list[str] = []

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in out:
            out.append(c)

    add(url)
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if host == "raw.githubusercontent.com":
        parts = path.split("/", 3)
        if len(parts) == 4:
            owner, repo, ref, rel_path = parts
            add(f"https://api.github.com/repos/{owner}/{repo}/contents/{rel_path}?ref={ref}")
            add(f"https://github.com/{owner}/{repo}/raw/{ref}/{rel_path}")
    elif host == "github.com":
        parts = path.split("/")
        if len(parts) >= 5:
            owner, repo, marker, ref = parts[0], parts[1], parts[2], parts[3]
            rel_path = "/".join(parts[4:])
            if marker in {"raw", "blob"}:
                add(f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{rel_path}")
                add(f"https://api.github.com/repos/{owner}/{repo}/contents/{rel_path}?ref={ref}")

    return out


def _installer_args(installer_path: Path) -> list[str]:
    return [
        str(installer_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/FORCECLOSEAPPLICATIONS",
    ]


def _run_installer_with_relaunch(installer_args: list[str], relaunch_executable: Path) -> None:
    relaunch_path = Path(relaunch_executable)
    if not relaunch_path.exists():
        raise UpdateError(f"Не найден исполняемый файл для перезапуска: {relaunch_path}")

    # Run installer and, after completion, start app again from a detached CMD script.
    script_path = Path(tempfile.gettempdir()) / "dazzle_update_relaunch.cmd"
    cmd_line = subprocess.list2cmdline(installer_args)
    script = (
        "@echo off\r\n"
        "setlocal\r\n"
        f"{cmd_line}\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f"if exist \"{relaunch_path}\" start \"\" \"{relaunch_path}\"\r\n"
        "del \"%~f0\" >nul 2>nul\r\n"
    )
    script_path.write_text(script, encoding="cp1251", errors="ignore")

    creation_flags = 0
    creation_flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    creation_flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
    subprocess.Popen(
        ["cmd.exe", "/c", str(script_path)],
        creationflags=creation_flags,
    )

