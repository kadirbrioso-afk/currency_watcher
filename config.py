"""
Gestión de la configuración persistente del programa.

Maneja la carga y el guardado de la configuración en un archivo JSON local,
incluyendo la moneda base, el intervalo de refresco y las reglas de alerta.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# Monedas soportadas por la aplicación, con su código y nombre en español.
SUPPORTED_CURRENCIES: dict[str, str] = {
    "EUR": "Euro",
    "GBP": "Libra esterlina",
    "USD": "Dólar estadounidense",
    "JPY": "Yen japonés",
    "CNY": "Yuan chino",
    "PEN": "Sol peruano",
    "RUB": "Rublo ruso",
}

# Tipos de condición soportados por las alertas.
CONDITIONS: dict[str, dict[str, str]] = {
    "greater_than": {"label": "Precio mayor que (>)"},
    "less_than": {"label": "Precio menor que (<)"},
    "greater_or_equal": {"label": "Precio mayor o igual que (>=)"},
    "less_or_equal": {"label": "Precio menor o igual que (<=)"},
    "percent_up": {"label": "Subida porcentual mayor que (%)"},
    "percent_down": {"label": "Bajada porcentual mayor que (%)"},
}


def _now_iso() -> str:
    """Devuelve la fecha/hora actual en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Alert:
    """Una regla de notificación (alerta) configurada por el usuario."""

    currency: str
    condition: str
    value: float
    enabled: bool = True
    notify_once: bool = False
    trigger_on_next_check: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Alert":
        """Construye una Alert desde un diccionario (JSON), con tolerancia a datos sueltos."""
        return cls(
            currency=str(data.get("currency", "EUR")),
            condition=str(data.get("condition", "greater_than")),
            value=float(data.get("value", 0.0)),
            enabled=bool(data.get("enabled", True)),
            notify_once=bool(data.get("notify_once", False)),
            trigger_on_next_check=bool(data.get("trigger_on_next_check", False)),
            id=str(data.get("id", str(uuid.uuid4()))),
            created_at=str(data.get("created_at", _now_iso())),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convierte la Alert a un diccionario serializable a JSON."""
        return asdict(self)


@dataclass
class Config:
    """Configuración global persistente de la aplicación."""

    base_currency: str = "USD"
    refresh_interval: int = 60
    auto_refresh: bool = True
    alerts: list[Alert] = field(default_factory=list)

    DEFAULT_INTERVALS: set[int] = field(
        default_factory=lambda: {30, 60, 300}, repr=False
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Construye una Config desde un diccionario (JSON)."""
        alerts = [Alert.from_dict(a) for a in data.get("alerts", [])]
        return cls(
            base_currency=str(data.get("base_currency", "USD")),
            refresh_interval=int(data.get("refresh_interval", 60)),
            auto_refresh=bool(data.get("auto_refresh", True)),
            alerts=alerts,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convierte la Config a un diccionario serializable a JSON."""
        return {
            "base_currency": self.base_currency,
            "refresh_interval": self.refresh_interval,
            "auto_refresh": self.auto_refresh,
            "alerts": [a.to_dict() for a in self.alerts],
        }


class ConfigManager:
    """Responsable de leer y escribir la configuración en disco."""

    def __init__(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self.path = Path(path)

    def load(self) -> Config:
        """Carga la configuración desde el archivo JSON.

        Si el archivo no existe, devuelve la configuración por defecto.
        Si el archivo está corrupto, devuelve la configuración por defecto
        con un marcador de error para mostrarlo en la interfaz.
        """
        if not self.path.exists():
            return Config()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            config = Config.from_dict(raw)
            if config.base_currency not in SUPPORTED_CURRENCIES:
                config.base_currency = "USD"
            return config
        except (json.JSONDecodeError, ValueError, TypeError, OSError):
            # Configuración corrupta: devolvemos los valores por defecto.
            return Config()

    def save(self, config: Config) -> bool:
        """Guarda la configuración en disco. Devuelve True si tuvo éxito."""
        try:
            self.path.write_text(
                json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    def add_alert(self, config: Config, data: dict[str, Any]) -> Alert:
        """Crea una alerta a partir de un diccionario y la añade a la configuración."""
        if data.get("id"):
            # Si la alerta ya tenía id, la reutilizamos (caso de edición).
            alert = Alert.from_dict({**data, "id": data["id"]})
        else:
            alert = Alert.from_dict(data)
        config.alerts.append(alert)
        return alert

    def update_alert(self, config: Config, alert_id: str, data: dict[str, Any]) -> bool:
        """Actualiza una alerta existente. Devuelve True si la encontró."""
        for i, alert in enumerate(config.alerts):
            if alert.id == alert_id:
                config.alerts[i] = Alert.from_dict({**data, "id": alert_id})
                return True
        return False

    def delete_alert(self, config: Config, alert_id: str) -> bool:
        """Elimina una alerta por su id. Devuelve True si la eliminó."""
        original = len(config.alerts)
        config.alerts = [a for a in config.alerts if a.id != alert_id]
        return len(config.alerts) != original


def copy_alert(alert: Alert) -> Alert:
    """Devuelve una copia profunda de una alerta (para editar sin mutar el original)."""
    return Alert.from_dict(copy.deepcopy(alert.to_dict()))
