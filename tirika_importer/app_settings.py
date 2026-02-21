from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppSettings:
    db_path: str = ""
    invoices_dir: str = ""
    markup_percent: float = 50.0
    round_step: float = 50.0
    price_alert_threshold_percent: float = 35.0
    supplier_id: int = 1
    user_id: int = 1
    shop_id: int = 0
    payment_type: int = 1
    payment_mapping_version: int = 2
    create_missing_goods: bool = True
    update_existing_goods_fields: bool = False
    update_goods_buy_price: bool = True
    update_existing_sell_price: bool = False
    update_existing_buy_price: bool = True
    update_existing_supplier: bool = True
    update_existing_name: bool = False
    update_existing_manufacturer: bool = False
    auto_pay: bool = True
    backup_before_import: bool = True
    prefix_new_goods_with_order: bool = True
    table_layout_version: int = 2
    table_header_state: str = ""
    update_manifest_url: str = "https://raw.githubusercontent.com/ahiokk/Dazzle/main/updates/latest.json"
    auto_check_updates: bool = True
    ignored_update_version: str = ""


def settings_file_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Dazzle" / "settings.json"
    return Path.home() / ".dazzle_settings.json"


def load_app_settings() -> AppSettings:
    path = settings_file_path()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()

    defaults = AppSettings()
    mapping_version_raw = raw.get("payment_mapping_version")
    if mapping_version_raw is None:
        mapping_version = 1
    else:
        mapping_version = _to_int(mapping_version_raw, defaults.payment_mapping_version)
    payment_type = _to_int(raw.get("payment_type"), defaults.payment_type)
    if mapping_version < defaults.payment_mapping_version:
        payment_type = _migrate_payment_type_from_legacy(payment_type)
    mapping_version = defaults.payment_mapping_version

    layout_version_raw = raw.get("table_layout_version")
    if layout_version_raw is None:
        layout_version = 1
    else:
        layout_version = _to_int(layout_version_raw, defaults.table_layout_version)
    table_header_state = str(raw.get("table_header_state", defaults.table_header_state) or "")
    if layout_version < defaults.table_layout_version:
        table_header_state = ""
    layout_version = defaults.table_layout_version

    return AppSettings(
        db_path=str(raw.get("db_path", defaults.db_path) or ""),
        invoices_dir=str(raw.get("invoices_dir", defaults.invoices_dir) or ""),
        markup_percent=_to_float(raw.get("markup_percent"), defaults.markup_percent),
        round_step=max(1.0, _to_float(raw.get("round_step"), defaults.round_step)),
        price_alert_threshold_percent=max(
            0.0,
            _to_float(
                raw.get("price_alert_threshold_percent"),
                defaults.price_alert_threshold_percent,
            ),
        ),
        supplier_id=_to_int(raw.get("supplier_id"), defaults.supplier_id),
        user_id=_to_int(raw.get("user_id"), defaults.user_id),
        shop_id=_to_int(raw.get("shop_id"), defaults.shop_id),
        payment_type=payment_type,
        payment_mapping_version=mapping_version,
        create_missing_goods=_to_bool(raw.get("create_missing_goods"), defaults.create_missing_goods),
        update_existing_goods_fields=_to_bool(
            raw.get("update_existing_goods_fields"),
            defaults.update_existing_goods_fields,
        ),
        update_goods_buy_price=_to_bool(
            raw.get("update_goods_buy_price"),
            defaults.update_goods_buy_price,
        ),
        update_existing_sell_price=_to_bool(
            raw.get("update_existing_sell_price"),
            defaults.update_existing_sell_price,
        ),
        update_existing_buy_price=_to_bool(
            raw.get("update_existing_buy_price"),
            defaults.update_existing_buy_price,
        ),
        update_existing_supplier=_to_bool(
            raw.get("update_existing_supplier"),
            defaults.update_existing_supplier,
        ),
        update_existing_name=_to_bool(
            raw.get("update_existing_name"),
            defaults.update_existing_name,
        ),
        update_existing_manufacturer=_to_bool(
            raw.get("update_existing_manufacturer"),
            defaults.update_existing_manufacturer,
        ),
        auto_pay=_to_bool(raw.get("auto_pay"), defaults.auto_pay),
        backup_before_import=_to_bool(raw.get("backup_before_import"), defaults.backup_before_import),
        prefix_new_goods_with_order=_to_bool(
            raw.get("prefix_new_goods_with_order"),
            defaults.prefix_new_goods_with_order,
        ),
        table_layout_version=layout_version,
        table_header_state=table_header_state,
        update_manifest_url=_to_nonempty_str(
            raw.get("update_manifest_url"),
            defaults.update_manifest_url,
        ),
        auto_check_updates=_to_bool(raw.get("auto_check_updates"), defaults.auto_check_updates),
        ignored_update_version=str(raw.get("ignored_update_version", defaults.ignored_update_version) or ""),
    )


def save_app_settings(settings: AppSettings) -> Path:
    path = settings_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _to_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _to_nonempty_str(value: object, default: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return str(default or "")


def _migrate_payment_type_from_legacy(value: int) -> int:
    # Legacy mapping used in older builds:
    #   cash=1, wire=0. New mapping is aligned with Tirika IDs:
    #   cash=0, wire=1.
    if value == 0:
        return 1
    if value == 1:
        return 0
    return value
