"""
Obtención de tipos de cambio de forma asíncrona usando aiohttp.

Selecciona automáticamente entre varias APIs públicas gratuitas para
garantizar redundancia. Maneja errores de red, timeouts y respuestas inválidas.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

# APIs gratuitas de tipos de cambio. Cada proveedor define:
#   - url_template: plantilla de la URL, con un hueco {base} para la moneda base.
#   - parse: función que extrae un dict {MONEDA: float} de la respuesta JSON.
#
# open.er-api.com devuelve tasas relativas a la moneda base en "rates".
RATE_PROVIDERS: list[dict[str, Any]] = [
    {
        "name": "open.er-api.com",
        "url_template": "https://open.er-api.com/v6/latest/{base}",
        "parse": lambda data: data.get("rates", {}),
    },
    {
        "name": "frankfurter.app",
        "url_template": "https://api.frankfurter.app/latest?from={base}",
        "parse": lambda data: data.get("rates", {}),
    },
]

# Monedas que la app quiere mostrar (el código de la moneda base se excluirá).
WATCHED_CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CNY", "PEN", "RUB"]

REQUEST_TIMEOUT_SECONDS = 10.0


async def _fetch_rates_from(provider: dict[str, Any], base: str, session: aiohttp.ClientSession) -> dict[str, float]:
    """Consulta una única API y devuelve un dict {MONEDA: tasa} en relación a `base`.

    Lanza las excepciones pertinentes para que la capa superior las maneje.
    """
    url = provider["url_template"].format(base=base)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
        if not isinstance(data, dict):
            raise ValueError("Respuesta JSON no es un diccionario")

        rates = provider["parse"](data)
        if not isinstance(rates, dict):
            raise ValueError("No se encontraron tasas en la respuesta")

        # Normalizamos y validamos que los valores sean numéricos positivos.
        result: dict[str, float] = {}
        for code, rate in rates.items():
            try:
                value = float(rate)
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[code] = value
        return result


async def fetch_rates(base: str, session: aiohttp.ClientSession | None = None) -> dict[str, float]:
    """Obtiene los tipos de cambio para la moneda base indicada.

    Recorre los proveedores disponibles, usando el primero que funcione.
    Si todos fallan, propaga la última excepción después de intentar todos.

    Devuelve un dict {MONEDA: tasa} relativo a `base`.
    """
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    last_error: Exception | None = None
    try:
        for provider in RATE_PROVIDERS:
            try:
                rates = await _fetch_rates_from(provider, base, session)
                log.info("Obtenidas tasas desde %s para %s", provider["name"], base)
                return rates
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
                log.warning("Fallo del proveedor %s: %s", provider["name"], exc)
                last_error = exc
        # Si llegamos aquí, todos los proveedores fallaron.
        raise RuntimeError(f"Todas las APIs fallaron: {last_error}")
    finally:
        if own_session:
            await session.close()


async def fetch_rates_for_display(
    base: str, session: aiohttp.ClientSession | None = None
) -> dict[str, float]:
    """Obtiene tasas para todas las monedas vigiladas excepto la base.

    La tasa de la moneda base respecto a sí misma es siempre 1.0.
    """
    rates = await fetch_rates(base, session)

    # Aseguramos que la moneda base esté presente con valor 1.0,
    # por si alguna API no la incluye.
    result: dict[str, float] = {base: 1.0}
    for code in WATCHED_CURRENCIES:
        if code in rates:
            result[code] = rates[code]
    return result
