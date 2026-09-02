"""Tests para la lógica de evaluación de alertas (alerts.py)."""

from __future__ import annotations

from alerts import describe_condition, evaluate, is_periodic
from config import Alert, CONDITIONS, PERIODIC_CONDITION, SUPPORTED_CURRENCIES


def _alert(condition: str, value: float = 1.0) -> Alert:
    return Alert(currency="EUR", condition=condition, value=value)


def test_is_periodic_false_for_threshold():
    assert not is_periodic(_alert("greater_than"))


def test_is_periodic_true_for_periodic():
    assert is_periodic(_alert(PERIODIC_CONDITION))


def test_greater_than_trigger():
    result, msg = evaluate(_alert("greater_than", 1.0), 1.5, None)
    assert result is True
    assert msg == f"EUR ({SUPPORTED_CURRENCIES['EUR']}): {CONDITIONS['greater_than']['label']} 1"


def test_greater_than_not_trigger():
    result, _ = evaluate(_alert("greater_than", 1.0), 0.5, None)
    assert result is False


def test_less_than_trigger():
    result, _ = evaluate(_alert("less_than", 1.0), 0.5, None)
    assert result is True


def test_greater_or_equal_equal_trigger():
    result, _ = evaluate(_alert("greater_or_equal", 1.0), 1.0, None)
    assert result is True


def test_less_or_equal_equal_trigger():
    result, _ = evaluate(_alert("less_or_equal", 1.0), 1.0, None)
    assert result is True


def test_percent_up_trigger():
    result, _ = evaluate(_alert("percent_up", 5.0), 11.0, 10.0)
    assert result is True


def test_percent_up_not_trigger():
    result, _ = evaluate(_alert("percent_up", 10.0), 10.5, 10.0)
    assert result is False


def test_percent_down_trigger():
    # Bajada del 20% (de 10 a 8) supera el umbral del 15%.
    result, _ = evaluate(_alert("percent_down", 15.0), 8.0, 10.0)
    assert result is True


def test_percent_down_needs_previous():
    result, _ = evaluate(_alert("percent_down", 15.0), 8.0, None)
    assert result is False


def test_periodic_never_triggers_here():
    result, _ = evaluate(_alert(PERIODIC_CONDITION), 1.5, None)
    assert result is False


def test_current_none_returns_false():
    result, _ = evaluate(_alert("greater_than", 1.0), None, None)
    assert result is False


def test_unknown_condition_returns_false():
    result, _ = evaluate(_alert("bogus_condition"), 1.5, None)
    assert result is False


def test_describe_condition_periodic():
    alert = Alert(currency="GBP", condition=PERIODIC_CONDITION, value=0.0, period_hours=12)
    assert "informe periódico cada 12 horas" in describe_condition(alert)


def test_describe_condition_threshold():
    assert "mayor que" in describe_condition(_alert("greater_than", 1.5))