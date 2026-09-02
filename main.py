"""
Punto de entrada de Currency Watcher.

Combina la interfaz gráfica ttkbootstrap con un bucle de eventos asyncio
ejecutado en un hilo independiente:

  Hilo principal  -> tkinter / ttkbootstrap (UI).
  Hilo worker     -> asyncio: red (aiohttp) + actualización automática + alertas.

La comunicación entre ambos hilos se hace mediante un queue.Queue seguro.
El hilo worker actualiza su estado interno y encola resultados; la UI los
consume con root.after() y aplica los cambios a los widgets (siempre desde el
hilo principal, que es el único que debe tocar tkinter).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any, Callable

import aiohttp

import ttkbootstrap as ttk

from config import ConfigManager, SUPPORTED_CURRENCIES
from history import HistoryStore
from rates import fetch_rates_for_display
from ui import CurrencyWatcherUI, RatesController

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("currency_watcher")


class AsyncWorker:
    """Hilo con su propio bucle de asyncio que obtiene tasas de forma periódica.

    No depende de la UI. Cuando obtiene datos, los deja en la cola del
    `RatesController`, que la UI consume de forma segura.

    Delegados: el worker consulta el estado de la configuración a través de
    callbacks para evitar acoplar esta clase a la ventana de tkinter.
    """

    def __init__(
        self,
        controller: RatesController,
        get_base: Callable[[], str],
        get_interval: Callable[[], int],
        is_auto_enabled: Callable[[], bool],
        history: HistoryStore | None = None,
    ) -> None:
        self.controller = controller
        self.get_base = get_base
        self.get_interval = get_interval
        self.is_auto_enabled = is_auto_enabled
        self.history = history

        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ----------------------------------------------------------- ciclo

    def start(self) -> None:
        """Arranca el hilo que ejecuta el bucle asyncio en segundo plano."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._main_task = self._loop.create_task(self._main_loop())
            self._loop.run_forever()
        finally:
            if self._main_task and not self._main_task.done():
                self._main_task.cancel()
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    async def _main_loop(self) -> None:
        """Bucle de actualización periódica y de peticiones puntuales."""
        self._session = aiohttp.ClientSession()
        try:
            while True:
                if self._stop_event.is_set():
                    return

                interval = max(int(self.get_interval()), 5)
                # Esperamos `interval` segundos de forma interrumpible.
                remaining = interval
                while remaining > 0:
                    await self._sleep_or_stop(1)
                    if self._stop_event.is_set():
                        return
                    remaining -= 1

                # Solo actualizamos automáticamente si el modo auto está activo;
                # las actualizaciones manuales llegan por request_refresh.
                if self.is_auto_enabled():
                    await self._refresh()
        finally:
            if self._session:
                await self._session.close()

    async def _sleep_or_stop(self, delay: float) -> None:
        """Duerme `delay` segundos, abortando antes si se pide detener."""
        try:
            await asyncio.wait_for(self._stop_wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _stop_wait(self) -> None:
        """Espera a que se active el evento de parada (no afecta a tkinter)."""
        while not self._stop_event.is_set():
            await asyncio.sleep(0.1)

    # ------------------------------------------------- public API

    def request_refresh(self) -> None:
        """Pide una actualización inmediata desde la UI (no bloqueante)."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._refresh(), self._loop)

    async def _refresh(self) -> None:
        """Obtiene las tasas y las deja en la cola de resultados."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        base = self.get_base()
        try:
            rates = await fetch_rates_for_display(base, self._session)
            stamp = datetime.now().isoformat(timespec="seconds")
            if self.history is not None:
                try:
                    self.history.record(base, rates, ts=stamp)
                except Exception:
                    pass
            self.controller.results.put(
                {"kind": "rates", "rates": rates, "base": base, "stamp": stamp}
            )
        except Exception as exc:
            log.error("Error obteniendo tasas: %s", exc)
            self.controller.results.put(
                {
                    "kind": "error",
                    "message": f"No se pudieron obtener los precios: {exc}",
                    "base": base,
                }
            )

    # Nota: el worker se detiene con el proceso (es un daemon). El evento
    # _stop_event queda como mecanismo para futuras mejoras (apagado limpio).


def main() -> None:
    # Cargamos configuración persistente (o la de por defecto).
    config_manager = ConfigManager()
    config = config_manager.load()
    if config.base_currency not in SUPPORTED_CURRENCIES:
        config.base_currency = "USD"

    # Ventana ttkbootstrap con el tema guardado.
    root = ttk.Window(themename=config.theme)

    # Controlador de comunicación UI <-> worker.
    controller = RatesController()

    # Almacén de historial SQLite (se rellena con cada actualización).
    history = HistoryStore()
    history.connect()

    # Worker asíncrono que delega la lectura de la configuración en callbacks.
    worker = AsyncWorker(
        controller,
        get_base=lambda: config.base_currency,
        get_interval=lambda: int(config.refresh_interval),
        is_auto_enabled=lambda: bool(config.auto_refresh),
        history=history,
    )

    # El botón de "Actualizar" llama al worker.
    controller.set_request_handler(worker.request_refresh)

    # Construimos la interfaz.
    ui = CurrencyWatcherUI(root, config, config_manager, controller, history=history)

    # Arrancamos el bucle asyncio y hacemos una primera actualización.
    worker.start()
    root.after(250, controller.request)

    root.protocol("WM_DELETE_WINDOW", ui.on_close)

    root.mainloop()


if __name__ == "__main__":
    main()
