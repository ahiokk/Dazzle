"""Минимальная наценка магазина и подсветка колонки «Наценка»."""
from tirika_importer.db import (
    MARKUP_BAND_EXTREME,
    MARKUP_BAND_GOOD,
    MARKUP_BAND_HIGH,
    MARKUP_BAND_LOW,
    MARKUP_BAND_NORMAL,
    calculate_markup_percent,
    enforce_min_markup_price,
    markup_band,
)


def test_calculate_markup_percent():
    assert calculate_markup_percent(100, 150) == 50.0
    assert calculate_markup_percent(100, 100) == 0.0
    assert calculate_markup_percent(0, 150) is None      # закупка неизвестна
    assert calculate_markup_percent(None, 150) is None
    assert calculate_markup_percent(100, None) is None


def test_markup_band_ranges():
    assert markup_band(35) == MARKUP_BAND_LOW          # ниже минимума 50%
    assert markup_band(49.9) == MARKUP_BAND_LOW
    assert markup_band(50) == MARKUP_BAND_NORMAL       # 50–75 оранжевый
    assert markup_band(74.9) == MARKUP_BAND_NORMAL
    assert markup_band(75) == MARKUP_BAND_GOOD         # 75–100 зелёный
    assert markup_band(99.9) == MARKUP_BAND_GOOD
    assert markup_band(100) == MARKUP_BAND_HIGH        # 100–200 жёлтый
    assert markup_band(199.9) == MARKUP_BAND_HIGH
    assert markup_band(200) == MARKUP_BAND_EXTREME     # больше 200 красный
    assert markup_band(1000) == MARKUP_BAND_EXTREME
    assert markup_band(None) is None


def test_markup_band_follows_custom_minimum():
    assert markup_band(55, min_markup_percent=60) == MARKUP_BAND_LOW
    assert markup_band(65, min_markup_percent=60) == MARKUP_BAND_NORMAL


def test_min_markup_raises_cheap_db_price():
    # Купили за 1000, в базе продаётся за 1350 (наценка 35%) — поднимаем до 50%.
    new_price = enforce_min_markup_price(
        1000, 1350, min_markup_percent=50, round_step=50
    )
    assert new_price == 1500
    assert calculate_markup_percent(1000, new_price) == 50.0


def test_min_markup_keeps_normal_price():
    assert enforce_min_markup_price(1000, 1500, min_markup_percent=50, round_step=50) is None
    assert enforce_min_markup_price(1000, 2500, min_markup_percent=50, round_step=50) is None


def test_min_markup_rounding_never_drops_below_minimum():
    # Округление вверх до шага 50 не должно оставлять наценку ниже минимума.
    new_price = enforce_min_markup_price(
        333, 400, min_markup_percent=50, round_step=50
    )
    assert new_price == 500
    assert calculate_markup_percent(333, new_price) >= 50.0


def test_min_markup_disabled_or_unknown_buy_price():
    assert enforce_min_markup_price(1000, 1350, min_markup_percent=0, round_step=50) is None
    assert enforce_min_markup_price(0, 1350, min_markup_percent=50, round_step=50) is None
    assert enforce_min_markup_price(None, 1350, min_markup_percent=50, round_step=50) is None


def test_markup_band_with_custom_bounds():
    """Магазин может сдвинуть границы полос в настройках."""
    from tirika_importer.db import (
        MARKUP_BAND_EXTREME,
        MARKUP_BAND_GOOD,
        MARKUP_BAND_HIGH,
        MARKUP_BAND_NORMAL,
        markup_band,
    )

    bounds = [80.0, 120.0, 250.0]
    assert markup_band(70, bounds=bounds) == MARKUP_BAND_NORMAL
    assert markup_band(79.9, bounds=bounds) == MARKUP_BAND_NORMAL
    assert markup_band(80, bounds=bounds) == MARKUP_BAND_GOOD
    assert markup_band(119.9, bounds=bounds) == MARKUP_BAND_GOOD
    assert markup_band(120, bounds=bounds) == MARKUP_BAND_HIGH
    assert markup_band(249.9, bounds=bounds) == MARKUP_BAND_HIGH
    assert markup_band(250, bounds=bounds) == MARKUP_BAND_EXTREME


def test_markup_band_bounds_are_repaired():
    """Границы правит человек — кривой ввод чиним, а не падаем."""
    from tirika_importer.app_settings import (
        DEFAULT_MARKUP_BAND_BOUNDS,
        normalize_markup_band_bounds,
    )

    assert normalize_markup_band_bounds(None) == list(DEFAULT_MARKUP_BAND_BOUNDS)
    assert normalize_markup_band_bounds("ерунда") == list(DEFAULT_MARKUP_BAND_BOUNDS)
    assert normalize_markup_band_bounds([250, 80, 120]) == [80.0, 120.0, 250.0]
    # Совпавшие границы разводим: иначе полоса схлопнулась бы в ничто.
    assert normalize_markup_band_bounds([100, 100, 100]) == [100.0, 101.0, 102.0]
    # Не хватило значений — добираем стандартными.
    assert normalize_markup_band_bounds([90]) == [90.0, 100.0, 200.0]


def test_markup_band_colors_are_repaired():
    from tirika_importer.app_settings import (
        DEFAULT_MARKUP_BAND_COLORS,
        normalize_markup_band_colors,
    )

    assert normalize_markup_band_colors(None) == list(DEFAULT_MARKUP_BAND_COLORS)
    mixed = normalize_markup_band_colors(["#123456", "не цвет", "", "#ABCDEF"])
    assert mixed[0] == "#123456"
    assert mixed[1] == DEFAULT_MARKUP_BAND_COLORS[1]   # мусор заменён стандартным
    assert mixed[2] == DEFAULT_MARKUP_BAND_COLORS[2]
    assert mixed[3] == "#ABCDEF"
    assert mixed[4] == DEFAULT_MARKUP_BAND_COLORS[4]   # значения не было вовсе


def test_settings_roundtrip_keeps_bands_and_update_check(tmp_path, monkeypatch):
    """Настройки должны переживать перезапуск: и полосы, и дата проверки."""
    import tirika_importer.app_settings as app_settings

    monkeypatch.setattr(
        app_settings, "settings_file_path", lambda: tmp_path / "settings.json"
    )
    saved = app_settings.AppSettings(
        markup_band_bounds=[80.0, 120.0, 250.0],
        markup_band_colors=["#F8BBD0", "#B3E5FC", "#C8E6C9", "#D1C4E9", "#455A64"],
        last_update_check="09.09.2026 11:42",
    )
    app_settings.save_app_settings(saved)
    loaded = app_settings.load_app_settings()

    assert loaded.markup_band_bounds == [80.0, 120.0, 250.0]
    assert loaded.markup_band_colors == saved.markup_band_colors
    assert loaded.last_update_check == "09.09.2026 11:42"
