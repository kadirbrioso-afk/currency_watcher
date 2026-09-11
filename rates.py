"""
Obtención de tipos de cambio de forma asíncrona usando aiohttp.

Selecciona automáticamente entre varias APIs públicas gratuitas para
garantizar redundancia. Las criptomonedas se obtienen de CoinGecko.
Maneja errores de red, timeouts y respuestas inválidas.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from config import CRYPTO_IDS, FIAT_CURRENCIES

log = logging.getLogger(__name__)

# APIs gratuitas de tipos de cambio fiat. Cada proveedor define:
#   - url_template: plantilla de la URL, con un hueco {base} para la moneda base.
#   - parse: función que extrae un dict {MONEDA: float} de la respuesta JSON.
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

REQUEST_TIMEOUT_SECONDS = 10.0
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# Últimos precios crypto conocidos, para no perderlos si CoinGecko falla
# (p. ej. por rate-limit 429).
_crypto_cache: dict[str, float] = {}


async def _fetch_rates_from(provider: dict[str, Any], base: str, session: aiohttp.ClientSession) -> dict[str, float]:
    """Consulta una única API fiat y devuelve un dict {MONEDA: tasa} en relación a `base`."""
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

        result: dict[str, float] = {}
        for code, rate in rates.items():
            try:
                value = float(rate)
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[code] = value
        return result


async def _fetch_crypto_usd(session: aiohttp.ClientSession) -> dict[str, float]:
    """Obtiene precios de criptomonedas en USD desde CoinGecko.

    Devuelve un dict {CRYPTO_CODE: price_in_USD}.
    """
    gecko_ids = list(CRYPTO_IDS.values())
    ids_param = ",".join(gecko_ids)
    url = f"{COINGECKO_URL}?ids={ids_param}&vs_currencies=usd"
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async with session.get(url, timeout=timeout) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
        if not isinstance(data, dict):
            raise ValueError("CoinGecko: respuesta no es diccionario")

        result: dict[str, float] = {}
        for code, gecko_id in CRYPTO_IDS.items():
            entry = data.get(gecko_id)
            if isinstance(entry, dict):
                try:
                    price = float(entry["usd"])
                except (TypeError, ValueError, KeyError):
                    continue
                if price > 0:
                    result[code] = price
        if result:
            _crypto_cache.update(result)
        return result


async def fetch_rates(base: str, session: aiohttp.ClientSession | None = None) -> dict[str, float]:
    """Obtiene tasas fiat para la moneda base indicada.

    Recorre los proveedores disponibles, usando el primero que funcione.
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
        raise RuntimeError(f"Todas las APIs fiat fallaron: {last_error}")
    finally:
        if own_session:
            await session.close()


async def fetch_rates_for_display(
    base: str, session: aiohttp.ClientSession | None = None
) -> dict[str, float]:
    """Obtiene tasas fiat + precios de criptomonedas, todo en paralelo.

    Las criptomonedas siempre se obtienen en USD; si la moneda base no es
    USD, se convierten usando la tasa fiat correspondiente.
    """
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        fiat_coro = fetch_rates(base, session)
        crypto_coro = _fetch_crypto_usd(session)
        results = await asyncio.gather(fiat_coro, crypto_coro, return_exceptions=True)
        fiat_result, crypto_result = results[0], results[1]

        # Manejo de errores: si fiat falla, usamos lo que tengamos.
        fiat_rates: dict[str, float] = {}
        if isinstance(fiat_result, dict):
            fiat_rates = fiat_result
        else:
            log.warning("Error obteniendo tasas fiat: %s", fiat_result)

        if isinstance(crypto_result, Exception):
            log.warning("CoinGecko falló (uso caché): %s", crypto_result)
            crypto_usd = dict(_crypto_cache)
        else:
            crypto_usd = crypto_result

        # Construimos el resultado.
        result: dict[str, float] = {base: 1.0}

        # Tasas fiat.
        for code in FIAT_CURRENCIES:
            if code != base and code in fiat_rates:
                result[code] = fiat_rates[code]

        # Criptomonedas: convertir a la moneda base si no es USD.
        # fiat_rates[code] = cuántas unidades de `code` por 1 unidad de `base`.
        # Si base=EUR: fiat_rates["USD"]=1.16 significa 1 EUR = 1.16 USD.
        # Para BTC/EUR = BTC/USD × USD/EUR = price_usd × fiat_rates["USD"]
        usd_rate = fiat_rates.get("USD", 1.0) if base != "USD" else 1.0
        for code, price_usd in crypto_usd.items():
            if code != base:
                result[code] = price_usd * usd_rate

        return result
    finally:
        if own_session:
            await session.close()
