from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class UpdateError(RuntimeError):
    pass


@dataclass(slots=True)
class UpdateInfo:
    version: str
    installer_url: str
    sha256: str = ""
    notes: str = ""
    release_page_url: str = ""


def check_for_update(current_version: str, manifest_url: str, timeout_sec: float = 7.0) -> UpdateInfo | None:
    url = manifest_url.strip()
    if not url:
        return None

    manifest = _fetch_manifest(url, timeout_sec=timeout_sec)
    version = str(manifest.get("version", "")).strip()
    installer_url_raw = str(manifest.get("url", "")).strip()
    if not version or not installer_url_raw:
        raise UpdateError("В manifest нет обязательных полей: version и url.")

    installer_url = urljoin(url, installer_url_raw)
    info = UpdateInfo(
        version=version,
        installer_url=installer_url,
        sha256=str(manifest.get("sha256", "")).strip().lower(),
        notes=str(manifest.get("notes", "")).strip(),
        release_page_url=str(manifest.get("release_page_url", "")).strip(),
    )
    if not is_newer_version(info.version, current_version):
        return None
    return info


def download_installer(update: UpdateInfo, target_dir: Path, timeout_sec: float = 45.0) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    name = _installer_filename(update)
    final_path = target_dir / name
    temp_path = target_dir / f"{name}.part"

    req = Request(update.installer_url, headers={"User-Agent": "Dazzle-Updater/1.0"})
    try:
        with urlopen(req, timeout=timeout_sec) as resp, temp_path.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise UpdateError(f"Не удалось скачать обновление: {exc}") from exc

    if update.sha256:
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


def run_installer(installer_path: Path) -> None:
    if not installer_path.exists():
        raise UpdateError(f"Файл установщика не найден: {installer_path}")

    args = [
        str(installer_path),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/FORCECLOSEAPPLICATIONS",
    ]
    try:
        subprocess.Popen(args)
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
    return _version_tuple(candidate) > _version_tuple(current)


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
    req = Request(manifest_url, headers={"User-Agent": "Dazzle-Updater/1.0"})
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            payload = resp.read().decode("utf-8")
    except Exception as exc:
        raise UpdateError(f"Не удалось получить manifest обновлений: {exc}") from exc

    try:
        raw = json.loads(payload)
    except Exception as exc:
        raise UpdateError(f"Manifest обновлений не является валидным JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise UpdateError("Manifest должен быть JSON-объектом.")
    return raw

