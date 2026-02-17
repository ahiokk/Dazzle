from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    env_path: Path
    db_dir: Path | None


def _parse_env_value(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'} and value[-1] == value[0]:
        value = value[1:-1]
    return value


def load_config(env_path: Path | None = None) -> AppConfig:
    env = env_path or Path(".ENV")
    if not env.exists():
        return AppConfig(env_path=env, db_dir=None)

    db_dir: Path | None = None
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip().lower() == "path_to_db":
            parsed = _parse_env_value(raw_value)
            if parsed:
                db_dir = Path(parsed)
    return AppConfig(env_path=env, db_dir=db_dir)
