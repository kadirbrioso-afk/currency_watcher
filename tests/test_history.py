"""Tests para el almacenamiento de historial SQLite (history.py)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from history import HistoryStore


def _recent_ts(hours_ago: float) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


@pytest.fixture
def store(tmp_path: Path) -> HistoryStore:
    hs = HistoryStore(tmp_path / "test_history.db")
    hs.connect()
    yield hs
    hs.close()


def test_record_and_series(store: HistoryStore):
    assert store.record("USD", {"EUR": 0.9, "GBP": 0.8}, ts=_recent_ts(1))
    series = store.series("USD", "EUR", hours=48)
    assert len(series) == 1
    assert series[0]["rate"] == 0.9


def test_series_filters_by_base_and_currency(store: HistoryStore):
    ts = _recent_ts(1)
    store.record("USD", {"EUR": 0.9}, ts=ts)
    store.record("USD", {"GBP": 0.8}, ts=ts)
    store.record("EUR", {"USD": 1.1}, ts=ts)
    assert len(store.series("USD", "EUR", hours=48)) == 1
    assert len(store.series("USD", "GBP", hours=48)) == 1
    assert len(store.series("EUR", "USD", hours=48)) == 1


def test_series_ordered_ascending(store: HistoryStore):
    store.record("USD", {"EUR": 0.8}, ts=_recent_ts(2))
    store.record("USD", {"EUR": 0.9}, ts=_recent_ts(1))
    rates = [s["rate"] for s in store.series("USD", "EUR", hours=48)]
    assert rates == [0.8, 0.9]


def test_series_hours_filter(store: HistoryStore):
    store.record("USD", {"EUR": 0.9}, ts=_recent_ts(2))
    # Fuera de la ventana de 1 hora; dentro de la de 3 horas.
    assert store.series("USD", "EUR", hours=1) == []
    assert len(store.series("USD", "EUR", hours=3)) == 1


def test_series_limit(store: HistoryStore):
    for i in range(3, 23):
        store.record("USD", {"EUR": 0.8 + i / 100}, ts=_recent_ts(i))
    assert len(store.series("USD", "EUR", hours=48, limit=5)) == 5


def test_skip_none_rates(store: HistoryStore):
    store.record("USD", {"EUR": None, "GBP": 0.8}, ts=_recent_ts(1))
    assert store.series("USD", "EUR", hours=48) == []
    assert len(store.series("USD", "GBP", hours=48)) == 1


def test_daily_min_max(store: HistoryStore):
    store.record("USD", {"EUR": 0.8}, ts=_recent_ts(2))
    store.record("USD", {"EUR": 0.9}, ts=_recent_ts(1))
    result = store.daily_min_max("USD", "EUR", days=3)
    assert result is not None
    assert result["min"] == 0.8
    assert result["max"] == 0.9
    assert result["count"] == 2


def test_daily_min_max_not_enough_history(store: HistoryStore):
    store.record("USD", {"EUR": 0.8}, ts=_recent_ts(2 * 24 * 30))
    assert store.daily_min_max("USD", "EUR", days=1) is None


def test_moving_average(store: HistoryStore):
    for i in range(10):
        store.record("USD", {"EUR": float(i)}, ts=_recent_ts(i))
    avg = store.moving_average("USD", "EUR", window=5)
    assert len(avg) == 6


def test_moving_average_insufficient(store: HistoryStore):
    for i in range(2):
        store.record("USD", {"EUR": float(i)}, ts=_recent_ts(i))
    assert store.moving_average("USD", "EUR", window=5) == []


def test_record_before_connect_is_false():
    hs = HistoryStore("/tmp/opencode/never_connected.db")
    assert hs.record("USD", {"EUR": 0.9}) is False
    hs.close()


def test_series_unconnected_is_empty():
    hs = HistoryStore("/tmp/opencode/never_connected.db")
    assert hs.series("USD", "EUR") == []
    hs.close()