"""Tests para la gestión de configuración (config.py)."""

from __future__ import annotations

import json

import pytest

from config import (
    Alert,
    Config,
    ConfigManager,
    SUPPORTED_CURRENCIES,
    THEMES,
    copy_alert,
)


def test_default_config():
    config = Config()
    assert config.base_currency == "USD"
    assert config.refresh_interval == 60
    assert config.auto_refresh is True
    assert config.theme == "darkly"
    assert config.favorites == []
    assert config.alerts == []


def test_config_from_dict_roundtrip():
    config = Config(
        base_currency="EUR",
        refresh_interval=30,
        theme="superhero",
        favorites=["USD", "JPY"],
        alerts=[Alert(currency="GBP", condition="greater_than", value=1.2)],
    )
    loaded = Config.from_dict(config.to_dict())
    assert loaded == config


def test_invalid_theme_falls_back_to_darkly():
    config = Config.from_dict({"theme": "no_such_theme"})
    assert config.theme == "darkly"


def test_invalid_base_currency_falls_back(tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    manager.path.write_text(json.dumps({"base_currency": "ZZZ"}), encoding="utf-8")
    config = manager.load()
    assert config.base_currency == "USD"


def test_config_manager_save_load(tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    config = Config(base_currency="PEN", favorites=["EUR"], theme="minty")
    assert manager.save(config) is True
    loaded = manager.load()
    assert loaded.base_currency == "PEN"
    assert loaded.favorites == ["EUR"]
    assert loaded.theme == "minty"


def test_config_manager_missing_file(tmp_path):
    manager = ConfigManager(tmp_path / "nope.json")
    config = manager.load()
    assert config == Config()


def test_config_manager_corrupt_file(tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    manager.path.write_text("{ not valid json", encoding="utf-8")
    assert manager.load() == Config()


def test_add_update_delete_alert():
    manager = ConfigManager()
    config = Config()
    alert = manager.add_alert(config, {"currency": "EUR", "condition": "less_than", "value": 0.9})
    assert len(config.alerts) == 1

    assert manager.update_alert(config, alert.id, {"currency": "EUR", "condition": "greater_than", "value": 1.1})
    assert config.alerts[0].condition == "greater_than"

    assert manager.delete_alert(config, alert.id)
    assert config.alerts == []


def test_copy_alert_is_deep():
    original = Alert(currency="EUR", condition="greater_than", value=1.0)
    copied = copy_alert(original)
    copied.value = 2.0
    assert original.value == 1.0


def test_alert_roundtrip():
    alert = Alert(currency="JPY", condition="percent_up", value=5.0, period_hours=12)
    restored = Alert.from_dict(alert.to_dict())
    assert restored == alert


def test_themes_available():
    assert "darkly" in THEMES
    assert len(THEMES) > 5


def test_supported_currencies_has_euro():
    assert "EUR" in SUPPORTED_CURRENCIES
    assert SUPPORTED_CURRENCIES["EUR"] == "Euro"