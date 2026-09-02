"""
Sistema de notificaciones de escritorio para Linux.

Intenta usar `notify-send` (el estándar en la mayoría de escritorios Linux).
Si no está disponible, recurre a `plyer` si está instalado. Si ninguno funciona,
las notificaciones se envían a un callback dentro de la propia aplicación
(por ejemplo, un aviso en la interfaz), de modo que el programa nunca falle.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Callable

from sounds import play_alert_sound

log = logging.getLogger(__name__)

FALLBACK_TRIGGER: Callable[[str, str], None] | None = None


def set_fallback(handler: Callable[[str, str], None] | None) -> None:
    """Registra un handler alternativo si las notificaciones nativas fallan."""
    global FALLBACK_TRIGGER
    FALLBACK_TRIGGER = handler


def _notify_via_notify_send(title: str, message: str) -> bool:
    """Envía una notificación con `notify-send`. Devuelve True en caso de éxito."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Currency Watcher", title, message],
            check=True,
            timeout=10,
            capture_output=True,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("notify-send falló: %s", exc)
        return False


def _notify_via_plyer(title: str, message: str) -> bool:
    """Envía una notificación con plyer. Devuelve True en caso de éxito."""
    try:
        from plyer import notification  # importación diferida

        notification.notify(title=title, message=message, timeout=10)
        return True
    except Exception as exc:  # plyer puede fallar de muchas formas en dependencias
        log.warning("plyer falló: %s", exc)
        return False


def notify(title: str, message: str, play_sound: bool = True) -> bool:
    """Envía una notificación de escritorio probando varios métodos.

    Si `play_sound` es True, reproduce también un sonido de alerta (fallo
    silencioso si no hay reproductor disponible).

    Devuelve True si se pudo mostrar, o si se delegó al fallback.
    """
    has_notify_send = shutil.which("notify-send") is not None
    if has_notify_send and _notify_via_notify_send(title, message):
        if play_sound:
            play_alert_sound()
        return True
    if _notify_via_plyer(title, message):
        if play_sound:
            play_alert_sound()
        return True

    # Última opción: mostrar la notificación dentro de la propia app.
    if FALLBACK_TRIGGER is not None:
        try:
            FALLBACK_TRIGGER(title, message)
            if play_sound:
                play_alert_sound()
            return True
        except Exception as exc:  # nunca debe tumbar la aplicación
            log.error("Fallback de notificación falló: %s", exc)
            return False
    return False


def is_available() -> bool:
    """Indica si hay algún método de notificación nativo disponible."""
    return shutil.which("notify-send") is not None
