"""
Almacenamiento local del historial de tasas usando SQLite.

Guarda muestras periódicas de cada par (base, currency) para permitir:
  - dibujar gráficos de evolución histórica,
  - calcular indicadores simples (media móvil, mín/máx del día).

El módulo es autónomo (sin GUI) y se usa desde el worker asíncrono y desde la
interfaz para recuperar series de datos.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate REAL NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_pair_ts ON samples(base, currency, ts);
"""

_RETENTION_DAYS = 90


class HistoryStore:
    """Persiste y consulta muestras de tasas en una base SQLite local."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Abre la conexión (creando el esquema la primera vez).

        - `check_same_thread=False` permite que el worker (QThread) y el
          hilo principal compartan la misma conexión SQLite.
        - `journal_mode=WAL` + `busy_timeout=5000` evitan errores de
          "database is locked" cuando UI y worker acceden en paralelo.
        - Se eliminan registros antiguos (> 90 días) para mantener el tamaño.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._prune()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _prune(self, days: int = _RETENTION_DAYS) -> None:
        """Borra muestras más antiguas que `days` días (mismo esquema de ts local)."""
        if self._conn is None:
            return
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        try:
            with self._conn:
                self._conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
        except sqlite3.Error:
            pass

    def record(self, base: str, rates: dict[str, float], ts: str | None = None) -> bool:
        """Guarda una fila de muestras. Devuelve True si hubo éxito."""
        if self._conn is None:
            return False
        if ts is None:
            ts = datetime.now().isoformat(timespec="seconds")
        try:
            with self._conn:
                for currency, rate in rates.items():
                    if rate is None:
                        continue
                    self._conn.execute(
                        "INSERT INTO samples(base, currency, rate, ts) VALUES (?, ?, ?, ?)",
                        (base, currency, float(rate), ts),
                    )
            return True
        except (sqlite3.Error, ValueError):
            return False

    def series(
        self,
        base: str,
        currency: str,
        hours: int = 24,
        limit: int | None = 500,
    ) -> list[dict[str, Any]]:
        """Devuelve las muestras del par ordenadas por tiempo, limitadas en nº.

        Devuelve una lista de dicts: {"ts": "YYYY-MM-DDTHH:MM:SS", "rate": float}.
        """
        if self._conn is None:
            return []
        since = datetime.now() - timedelta(hours=max(hours, 1))
        since_iso = since.isoformat(timespec="seconds")
        try:
            cur = self._conn.execute(
                """
                SELECT ts, rate FROM samples
                WHERE base = ? AND currency = ?
                  AND ts >= ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (base, currency, since_iso, limit or 500),
            )
            return [{"ts": row[0], "rate": row[1]} for row in cur.fetchall()]
        except sqlite3.Error:
            return []

    def daily_min_max(self, base: str, currency: str, days: int = 1) -> dict[str, float] | None:
        """Devuelve el mínimo y máximo de las últimas `days` horas para el par."""
        series = self.series(base, currency, hours=max(days, 1) * 24, limit=10000)
        if not series:
            return None
        rates = [s["rate"] for s in series]
        return {"min": min(rates), "max": max(rates), "count": len(rates)}

    def moving_average(self, base: str, currency: str, window: int = 14) -> list[float]:
        """Devuelve la media móvil simple sobre las últimas muestras del par."""
        series = self.series(base, currency, hours=24 * 30, limit=10000)
        rates = [s["rate"] for s in series]
        if len(rates) < window:
            return []
        window = max(window, 1)
        return [sum(rates[i - window:i]) / window for i in range(window, len(rates) + 1)]