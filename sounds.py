"""
Reproducción de sonido de alerta en Linux.

Elige automáticamente el reproductor disponible en el sistema, con prioridad
a herramientas orientadas a notificaciones:

  1. `canberra-gtk-play`  -> reproducción de sonidos del tema freedesktop
     (integración nativa con los escritorios GNOME/KDE/...).
  2. `paplay`             -> reproductor de PulseAudio (muy común).
  3. `aplay`              -> reproductor de ALSA.
  4. `ffplay`             -> fallback genérico (FFmpeg).

Si ninguna está disponible, simplemente no se reproduce sonido y el programa
sigue funcionando con normalidad (las notificaciones visuales no dependen de él).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Sonidos del tema freedesktop usados por defecto si existen en el sistema.
_FD_THEME = Path("/usr/share/sounds/freedesktop/stereo")
_SOUND_NAMES = [
    "dialog-information",
    "message-new-information",
    "complete",
    "bell",
    "alarm-clock-elapsed",
]


def _find_theme_sound() -> Path | None:
    """Devuelve la ruta de un sonido del tema freedesktop disponible, o None."""
    if not _FD_THEME.is_dir():
        return None
    for name in _SOUND_NAMES:
        oga = _FD_THEME / f"{name}.oga"
        if oga.exists():
            return oga
    return None


def _play_canberra(sound: str) -> bool:
    """Reproduce un sonido del tema con canberra-gtk-play. Devuelve True si ok."""
    try:
        subprocess.run(
            ["canberra-gtk-play", "-i", sound],
            timeout=10,
            capture_output=True,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("canberra-gtk-play falló: %s", exc)
        return False


def _play_paplay(path: Path) -> bool:
    try:
        subprocess.run(["paplay", str(path)], timeout=10, capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("paplay falló: %s", exc)
        return False


def _play_aplay(path: Path) -> bool:
    try:
        subprocess.run(["aplay", "-q", str(path)], timeout=15, capture_output=True)
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("aplay falló: %s", exc)
        return False


def _play_ffplay(path: Path) -> bool:
    try:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
            timeout=15,
            capture_output=True,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("ffplay falló: %s", exc)
        return False


def play_alert_sound() -> bool:
    """Reproduce un sonido de alerta. Devuelve True si se reprodujo con éxito.

    Es totalmente opcional: si falla, solo se registra y la app continúa.
    """
    if shutil.which("canberra-gtk-play"):
        if _play_canberra("dialog-information"):
            return True

    sound_path = _find_theme_sound()
    if sound_path is None:
        return False

    if shutil.which("paplay") and _play_paplay(sound_path):
        return True
    if shutil.which("aplay") and _play_aplay(sound_path):
        return True
    if shutil.which("ffplay") and _play_ffplay(sound_path):
        return True
    return False
