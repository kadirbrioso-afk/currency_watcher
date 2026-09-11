"""
Punto de entrada de Currency Watcher.

Combina la interfaz gráfica PySide6 con un hilo QThread para operaciones async.

  Hilo principal  -> PySide6 / Qt (UI).
  Hilo worker     -> asyncio: red (aiohttp) + actualización de tasas.

La comunicación se hace mediante signals/slots de Qt.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from config import ConfigManager, FIAT_CURRENCIES
from history import HistoryStore
from ui import MainWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("currency_watcher")


def main() -> None:
    config_manager = ConfigManager()
    config = config_manager.load()
    if config.base_currency not in FIAT_CURRENCIES:
        config.base_currency = "USD"

    app = QApplication(sys.argv)
    app.setApplicationName("Currency Watcher")

    history = HistoryStore()
    history.connect()

    window = MainWindow(config, config_manager, history=history)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
