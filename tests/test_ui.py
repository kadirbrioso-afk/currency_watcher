"""Pruebas de humo de la GUI (PySide6, offscreen)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 no está instalado en este intérprete")

from PySide6.QtWidgets import QApplication  # noqa: E402

from config import Config, ConfigManager
from ui import MainWindow, Alert, asset_path  # noqa: F401


def test_mainwindow_builds_offscreen(tmp_path):
    app = QApplication.instance() or QApplication([])
    cm = ConfigManager(tmp_path / "config.json")
    config = cm.load()
    win = MainWindow(config, cm, history=None)
    try:
        assert "Currency Watcher" in win.windowTitle()
        assert win.table_view.model() is not None
        assert win.table_model.columnCount() == 9
        # El combo de moneda del gráfico excluye la base.
        assert win.chart_currency_combo.findData(config.base_currency) < 0
        win._save_config()
    finally:
        win._shutdown()


def test_app_icon_asset(tmp_path):
    """El icono existe en la raíz (asset_path) y la ventana lo usa."""
    assert asset_path("icon.png").is_file()
    app = QApplication.instance() or QApplication([])
    cm = ConfigManager(tmp_path / "config.json")
    win = MainWindow(cm.load(), cm, history=None)
    try:
        assert not win.windowIcon().isNull()
        assert win.spinner is not None
    finally:
        win._shutdown()


def test_periodic_alert_fires_after_period(tmp_path):
    app = QApplication.instance() or QApplication([])
    cm = ConfigManager(tmp_path / "config.json")
    config = Config(base_currency="USD")
    win = MainWindow(config, cm, history=None)
    try:
        alert = Alert(currency="PEN", condition="periodic", value=0.0, period_hours=1)
        win.periodic_refs = {}
        t0 = datetime.now(timezone.utc)
        # Primera comprobación: registra la referencia y no dispara.
        assert win._check_periodic(alert, 3.5, "USD", t0) is False
        assert alert.last_fired_at is None
        # Misma hora: aún no ha pasado el periodo.
        assert win._check_periodic(alert, 3.5, "USD", t0 + timedelta(minutes=30)) is False
        # Dos horas después: sí debería dispararse.
        assert win._check_periodic(alert, 3.6, "USD", t0 + timedelta(hours=2)) is True
        assert alert.last_fired_at is not None
    finally:
        win._shutdown()


def test_refresh_marks_currency_in_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    cm = ConfigManager(tmp_path / "config.json")
    config = Config(base_currency="USD")
    win = MainWindow(config, cm, history=None)
    try:
        item = {"rates": {"EUR": 1.1, "BTC": 50000.0}, "base": "USD", "stamp": "2026-09-10T23:00:00"}
        win._on_rates(item)
        assert win.rates_state["EUR"]["rate"] == 1.1
        assert win.rates_state["BTC"]["rate"] == 50000.0
    finally:
        win._shutdown()