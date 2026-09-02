"""
Evaluación de las condiciones de las alertas sobre los precios.

Contiene la lógica pura (sin GUI ni I/O) para decidir si una alerta
se cumple con un precio dado, incluyendo condiciones porcentuales.
"""

from __future__ import annotations

from typing import Any

from config import Alert, CONDITIONS, SUPPORTED_CURRENCIES


def describe_condition(alert: Alert) -> str:
    """Devuelve una descripción legible de la condición de una alerta."""
    label = CONDITIONS[alert.condition]["label"] if alert.condition in CONDITIONS else alert.condition
    symbol = SUPPORTED_CURRENCIES.get(alert.currency, alert.currency)
    return f"{alert.currency} ({symbol}): {label} {alert.value:g}"


def _to_float(value: Any) -> float | None:
    """Convierte un valor a float si es posible, si no devuelve None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate(alert: Alert, current: float | None, previous: float | None) -> tuple[bool, str]:
    """Evalúa una alerta contra el precio actual (y el anterior si procede).

    Devuelve una tupla (se_cumple: bool, mensaje_descripcion: str).
    """
    current = _to_float(current)
    if current is None:
        return False, describe_condition(alert)

    cond = alert.condition

    if cond == "greater_than":
        return current > alert.value, describe_condition(alert)

    if cond == "less_than":
        return current < alert.value, describe_condition(alert)

    if cond == "greater_or_equal":
        return current >= alert.value, describe_condition(alert)

    if cond == "less_or_equal":
        return current <= alert.value, describe_condition(alert)

    # Condiciones porcentuales: necesitan el valor anterior.
    if cond in ("percent_up", "percent_down"):
        previous = _to_float(previous)
        if previous is None or previous == 0:
            return False, describe_condition(alert)

        percent_change = ((current - previous) / previous) * 100.0
        if cond == "percent_up":
            return percent_change > alert.value, describe_condition(alert)
        # percent_down: bajada porcentual (negativa), comparamos valor absoluto.
        return (-percent_change) > alert.value, describe_condition(alert)

    # Condición desconocida: no evaluamos.
    return False, describe_condition(alert)
