"""
Interfaz gráfica con PySide6.

Este módulo contiene toda la parte visual usando PySide6/Qt, así como la
integración con el bucle de eventos de asyncio mediante QThread.
La lógica de negocio (tasas, alertas, configuración) se delega en los
otros módulos.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from alerts import describe_condition, evaluate, is_periodic
from config import (
    CONDITIONS,
    PERIOD_OPTIONS,
    PERIODIC_CONDITION,
    THEMES,
    THRESHOLD_CONDITIONS,
    SUPPORTED_CURRENCIES,
    CURRENCY_SYMBOLS,
    Alert,
    Config,
    ConfigManager,
    copy_alert,
)
from notifier import notify

HEADERS = ["Fav", "Símbolo", "Código", "Moneda", "Precio", "Hora", "Cambio", "Variación", "Estado"]
COL_KEYS = ["fav", "symbol", "code", "name", "price", "time", "change", "change_pct", "status"]
COL_WIDTHS = [40, 44, 72, 170, 120, 100, 90, 90, 90]

COLOR_UP = "#2ecc71"
COLOR_DOWN = "#e74c3c"
COLOR_FAV = "#f39c12"
COLOR_TEXT = "#e0e0e0"
COLOR_BG = "#1a1a2e"
COLOR_SURFACE = "#16213e"
COLOR_SURFACE_ALT = "#1a2446"
COLOR_BORDER = "#2c3e50"


def _shade(hex_color: str, factor: float) -> str:
    """Devuelve una variante más clara (factor>1) u oscura (factor<1) del color."""
    c = QColor(hex_color)
    ret = QColor(
        min(255, int(c.red() * factor)),
        min(255, int(c.green() * factor)),
        min(255, int(c.blue() * factor)),
    )
    return ret.name()


def build_qss(theme: dict[str, str]) -> str:
    """Construye una hoja de estilo QSS completa a partir de un diccionario de colores."""
    bg = theme["bg"]
    fg = theme["fg"]
    surface = theme["surface"]
    accent = theme["accent"]
    accent_fg = theme["accent_fg"]
    border = theme["border"]
    success = theme["success"]
    danger = theme["danger"]
    warning = theme["warning"]

    return f"""
    QMainWindow, QDialog {{
        background-color: {bg};
        color: {fg};
    }}
    QWidget {{
        background-color: {bg};
        color: {fg};
        font-size: 13px;
    }}
    QGroupBox {{
        border: 1px solid {border};
        border-radius: 6px;
        margin-top: 12px;
        padding: 12px 8px 8px 8px;
        font-weight: bold;
        color: {fg};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}
    QToolBar {{
        background-color: {surface};
        border-bottom: 1px solid {border};
        spacing: 8px;
        padding: 4px;
    }}
    QToolBar QComboBox, QToolBar QPushButton {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 10px;
        min-height: 24px;
    }}
    QToolBar QComboBox:hover, QToolBar QPushButton:hover {{
        border-color: {accent};
    }}
    QToolBar QLabel {{
        color: {fg};
    }}
    QComboBox {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 24px;
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        selection-background-color: {accent};
        selection-color: {accent_fg};
    }}
    QLineEdit {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
        min-height: 24px;
    }}
    QLineEdit:focus {{
        border-color: {accent};
    }}
    QPushButton {{
        background-color: {accent};
        color: {accent_fg};
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        min-height: 24px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        opacity: 0.9;
    }}
    QPushButton:pressed {{
        padding-top: 8px;
    }}
    QPushButton[cssClass="success"] {{
        background-color: {success};
    }}
    QPushButton[cssClass="danger"] {{
        background-color: {danger};
    }}
    QPushButton[cssClass="warning"] {{
        background-color: {warning};
        color: #000;
    }}
    QPushButton[cssClass="outline"] {{
        background-color: transparent;
        border: 1px solid {border};
        color: {fg};
    }}
    QPushButton[cssClass="outline"]:hover {{
        border-color: {accent};
    }}
    QTableView {{
        background-color: {surface};
        alternate-background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        gridline-color: {border};
        selection-background-color: {accent};
        selection-color: {accent_fg};
        font-size: 13px;
    }}
    QTableView::item {{
        padding: 4px 6px;
    }}
    QHeaderView::section {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        padding: 6px 8px;
        font-weight: bold;
    }}
    QStatusBar {{
        background-color: {surface};
        border-top: 1px solid {border};
        color: {fg};
    }}
    QListWidget {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        font-size: 12px;
    }}
    QListWidget::item {{
        padding: 4px 8px;
    }}
    QListWidget::item:selected {{
        background-color: {accent};
        color: {accent_fg};
    }}
    QCheckBox {{
        color: {fg};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QSplitter::handle {{
        background-color: {border};
    }}
    QSplitter::handle:horizontal {{
        width: 3px;
    }}
    QSplitter::handle:vertical {{
        height: 3px;
    }}
    QScrollBar:vertical {{
        background-color: {bg};
        width: 10px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {border};
        border-radius: 5px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QMenu {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: {accent_fg};
    }}
    QToolTip {{
        background-color: {surface};
        color: {fg};
        border: 1px solid {border};
        padding: 4px;
    }}
    """


# ──────────────────────────────────────────────────────────── Worker Thread
# -----------------------------------------------------------------------

def asset_path(name: str) -> Path:
    """Resuelve la ruta de un asset (p. ej. icon.png) en código o empaquetado.

    - En el bundle de PyInstaller, los assets viajan en ``sys._MEIPASS``.
    - En desarrollo, junto al módulo (raíz del proyecto).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent / name


class _WorkerSignals(QObject):
    """Señales que el worker emite hacia la UI (seguras entre hilos)."""
    rates_ready = Signal(dict)
    error = Signal(str)
    loading = Signal(bool)


class _WorkerThread(QThread):
    """Hilo que ejecuta peticiones async de tasas."""

    def __init__(self, get_base, history, parent=None):
        super().__init__(parent)
        self._get_base = get_base
        self._history = history
        self.signals = _WorkerSignals()
        self._stop = False
        self._loop = None

    def request_refresh(self):
        if self._loop is not None:
            self.signals.loading.emit(True)
            import asyncio
            asyncio.run_coroutine_threadsafe(self._do_refresh(), self._loop)

    def stop(self):
        """Detiene el hilo de forma segura (seguro de llamar más de una vez)."""
        self._stop = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait(2500)

    async def _do_refresh(self):
        from rates import fetch_rates_for_display
        base = self._get_base()
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                rates = await fetch_rates_for_display(base, session)
            stamp = datetime.now().isoformat(timespec="seconds")
            if self._history is not None:
                try:
                    self._history.record(base, rates, ts=stamp)
                except Exception:
                    pass
            self.signals.rates_ready.emit({"rates": rates, "base": base, "stamp": stamp})
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.loading.emit(False)

    def run(self):
        import asyncio

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            if self._stop:
                return
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()
            self._loop = None


# ──────────────────────────────────────────────────────── Table Model (MVC)
# ---------------------------------------------------------------------------

class RateTableModel(QAbstractTableModel):
    """Modelo de datos para la tabla de precios (MVC)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[list[str]] = []
        self._colors: list[str] = []
        self._fav_colors: list[str] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(COL_KEYS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._data):
            return None
        val = self._data[row][col]
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return val
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role == Qt.ForegroundRole:
            if col == 0 and self._fav_colors[row]:
                return QColor(self._fav_colors[row])
            if col in (4, 6, 7) and self._colors[row]:
                return QColor(self._colors[row])
            return QColor(COLOR_TEXT)
        if role == Qt.BackgroundRole:
            return QColor(COLOR_SURFACE_ALT) if row % 2 else QColor(COLOR_SURFACE)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return HEADERS[section]
        return None

    def update_data(self, rows: list[list[str]], colors: list[str], fav_colors: list[str]):
        """Actualiza el modelo con nuevos datos (actualización incremental)."""
        self.beginResetModel()
        self._data = rows
        self._colors = colors
        self._fav_colors = fav_colors
        self.endResetModel()

    def get_code(self, row: int) -> str:
        """Devuelve el código de moneda de la fila indicada."""
        if 0 <= row < len(self._data):
            return self._data[row][2]  # code column
        return ""


# ──────────────────────────────────────────────────── Chart Widget (QPainter)
# ---------------------------------------------------------------------------

class ChartWidget(QWidget):
    """Widget que dibuja el gráfico de evolución histórica con QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMaximumHeight(200)
        self._series: list[dict[str, Any]] = []
        self._currency = "EUR"
        self._currency_name = "Euro"
        self._range_label = "24h"
        self._hover_index: int | None = None
        self._progress = 1.0  # progreso de la animación de dibujo (0→1)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_step)
        self.setMouseTracking(True)

    def set_data(self, series: list[dict[str, Any]], currency: str, range_label: str):
        self._series = series
        self._currency = currency
        self._currency_name = SUPPORTED_CURRENCIES.get(currency, currency)
        self._range_label = range_label
        self._hover_index = None
        if len(series) >= 2:
            self._progress = 0.0
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            self._progress = 1.0
            self._anim_timer.stop()
        self.update()

    def _anim_step(self):
        self._progress = min(1.0, self._progress + 0.07)
        if self._progress >= 1.0:
            self._anim_timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Fondo
        painter.fillRect(0, 0, w, h, QColor(COLOR_BG))

        if not self._series:
            painter.setPen(QColor("#95a5a6"))
            painter.setFont(QFont("", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "Sin historial suficiente aún")
            painter.end()
            return

        rates = [s["rate"] for s in self._series]
        mn, mx = min(rates), max(rates)
        span = mx - mn or 1.0
        pad = 14
        margin_bottom = 36
        margin_top = 18
        plot_h = h - margin_bottom - margin_top
        plot_w = w - 2 * pad

        # Animación: solo se dibuja la porción ya "revelada" del historial.
        n_anim = max(0, int(len(rates) * self._progress))
        plot = rates[:n_anim]
        if not plot:
            plot = rates[:1]

        def sx(i):
            if len(rates) <= 1:
                return pad + 1
            return pad + (i / (len(rates) - 1)) * plot_w

        def sy(r):
            ratio = (r - mn) / span
            return margin_top + (1.0 - ratio) * plot_h

        # Área sombreada
        path = QPainterPath()
        path.moveTo(sx(0), margin_top + plot_h)
        for i, r in enumerate(plot):
            path.lineTo(sx(i), sy(r))
        path.lineTo(sx(len(plot) - 1), margin_top + plot_h)
        path.closeSubpath()
        brush = QBrush(QColor(46, 204, 113, 60))
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Línea de precios
        pen = QPen(QColor(COLOR_UP), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        polyline = [QPointF(sx(i), sy(r)) for i, r in enumerate(plot)]
        painter.drawPolyline(polyline)

        # Hover tooltip
        if self._hover_index is not None and n_anim > 0:
            idx = min(self._hover_index, n_anim - 1)
            x, y = sx(idx), sy(rates[idx])
            painter.setPen(QPen(QColor("#fff"), 1))
            painter.setBrush(QBrush(QColor("#fff")))
            painter.drawEllipse(QPointF(x, y), 4, 4)
            tooltip = f"{rates[idx]:.6g}"
            painter.setFont(QFont("", 9))
            painter.setPen(QColor("#fff"))
            painter.drawText(int(x + 8), int(y - 6), tooltip)

        # Línea base
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawLine(pad, margin_top + plot_h, w - pad, margin_top + plot_h)

        # Etiquetas min/max
        painter.setFont(QFont("", 8))
        painter.setPen(QColor("#95a5a6"))
        painter.drawText(pad + 4, margin_top + plot_h - 4, f"min {mn:.6g}")
        painter.drawText(
            QRectF(w - pad - 4 - 150, margin_top + 8, 150, 20),
            Qt.AlignRight,
            f"max {mx:.6g}",
        )

        # Título de moneda
        painter.setFont(QFont("", 9, QFont.Bold))
        painter.setPen(QColor(COLOR_FAV))
        painter.drawText(pad + 4, margin_top, f"{self._currency} ({self._currency_name})")

        # Rango
        painter.setFont(QFont("", 8))
        painter.setPen(QColor("#95a5a6"))
        painter.drawText(
            QRectF(w - pad - 4 - 150, margin_top + plot_h - 24, 150, 20),
            Qt.AlignRight,
            f"último {self._range_label}",
        )

        # Eje temporal: primera, media y última marca de la ventana mostrada
        n = len(rates)
        axis = sorted({0, n // 2, n - 1})
        painter.setFont(QFont("", 8))
        painter.setPen(QColor("#95a5a6"))
        anchors = {
            0: Qt.AlignLeft,
            n // 2: Qt.AlignHCenter,
            n - 1: Qt.AlignRight,
        }
        for idx in axis:
            wdt = 80
            if anchors[idx] == Qt.AlignLeft:
                x = sx(idx)
            elif anchors[idx] == Qt.AlignRight:
                x = sx(idx) - wdt
            else:
                x = sx(idx) - wdt / 2
            painter.drawText(
                QRectF(x, margin_top + plot_h + 8, wdt, 18),
                anchors[idx],
                self._fmt_ts(self._series[idx]["ts"]),
            )

        painter.end()

    def mouseMoveEvent(self, event):
        if not self._series:
            return
        rates = [s["rate"] for s in self._series]
        w = self.width()
        pad = 14
        plot_w = w - 2 * pad
        x = event.position().x()
        if len(rates) > 1:
            idx = int((x - pad) / plot_w * (len(rates) - 1))
            idx = max(0, min(idx, len(rates) - 1))
            if idx != self._hover_index:
                self._hover_index = idx
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            self.update()
        super().leaveEvent(event)

    @staticmethod
    def _fmt_ts(ts: str) -> str:
        """Formatea una marca ISO a "HH:MM" (hoy) o "DD/MM HH:MM" (otros días)."""
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return ""
        if dt.date() == datetime.now().date():
            return dt.strftime("%H:%M")
        return dt.strftime("%d/%m %H:%M")


# ──────────────────────────────────────────────────────────── Spinner (QPainter)
# ---------------------------------------------------------------------------

class Spinner(QWidget):
    """Indicador circular animado mostrado mientras se refrescan las tasas."""

    def __init__(self, parent=None, size: int = 16):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(size, size)
        self.setVisible(False)

    def _tick(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def start(self):
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setPen(QPen(QColor("#3a3f58"), 2))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(QPen(QColor(COLOR_FAV), 2))
        painter.drawArc(rect, -(self._angle % 360) * 16, 110 * 16)
        painter.end()


# ──────────────────────────────────────────────────────── Alert Dialog (QDialog)
# ---------------------------------------------------------------------------

class AlertDialog(QDialog):
    """Ventana modal para crear o editar una alerta."""

    def __init__(self, parent: QWidget, base_currency: str, alert: Alert | None = None):
        super().__init__(parent)
        self.base_currency = base_currency
        self.alert = alert
        self.result: Alert | None = None
        self.setWindowTitle("Nueva alerta" if alert is None else "Editar alerta")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        grid = QGridLayout(self)
        grid.setSpacing(10)

        # Moneda
        grid.addWidget(QLabel("Moneda:"), 0, 0)
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(list(SUPPORTED_CURRENCIES.keys()))
        if self.alert:
            idx = self.currency_combo.findText(self.alert.currency)
            if idx >= 0:
                self.currency_combo.setCurrentIndex(idx)
        grid.addWidget(self.currency_combo, 0, 1)

        # Condición
        grid.addWidget(QLabel("Condición:"), 1, 0)
        self.condition_combo = QComboBox()
        condition_labels = [c["label"] for c in CONDITIONS.values()]
        self.condition_combo.addItems(condition_labels)
        if self.alert:
            label = CONDITIONS.get(self.alert.condition, {}).get("label", "")
            idx = self.condition_combo.findText(label)
            if idx >= 0:
                self.condition_combo.setCurrentIndex(idx)
        self.condition_combo.currentIndexChanged.connect(self._on_condition_change)
        grid.addWidget(self.condition_combo, 1, 1)

        # Valor
        self.value_label = QLabel("Valor objetivo:")
        grid.addWidget(self.value_label, 2, 0)
        self.value_edit = QLineEdit()
        if self.alert and self.alert.value:
            self.value_edit.setText(f"{self.alert.value:g}")
        grid.addWidget(self.value_edit, 2, 1)

        # Periodo
        self.period_label = QLabel("Periodo:")
        self.period_combo = QComboBox()
        self.period_combo.addItems([str(h) for h in PERIOD_OPTIONS.keys()])
        if self.alert:
            idx = self.period_combo.findText(str(self.alert.period_hours))
            if idx >= 0:
                self.period_combo.setCurrentIndex(idx)
        grid.addWidget(self.period_label, 3, 0)
        grid.addWidget(self.period_combo, 3, 1)
        self.period_label.hide()
        self.period_combo.hide()

        # Notify once
        self.notify_once_check = QCheckBox("Notificar una sola vez")
        if self.alert:
            self.notify_once_check.setChecked(self.alert.notify_once)
        grid.addWidget(self.notify_once_check, 4, 1)

        # Enabled
        self.enabled_check = QCheckBox("Activada al guardar")
        self.enabled_check.setChecked(self.alert.enabled if self.alert else True)
        grid.addWidget(self.enabled_check, 5, 1)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.hide()
        grid.addWidget(self.error_label, 6, 0, 1, 2)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 7, 0, 1, 2)

        self._on_condition_change()

    def _on_condition_change(self):
        label = self.condition_combo.currentText()
        is_p = label == CONDITIONS[PERIODIC_CONDITION]["label"]
        self.value_label.setVisible(not is_p)
        self.value_edit.setVisible(not is_p)
        self.period_label.setVisible(is_p)
        self.period_combo.setVisible(is_p)
        self.notify_once_check.setVisible(not is_p)

    def _save(self):
        currency = self.currency_combo.currentText()
        if currency not in SUPPORTED_CURRENCIES:
            self.error_label.setText("Selecciona una moneda válida.")
            self.error_label.show()
            return

        labels = [c["label"] for c in CONDITIONS.values()]
        picked = self.condition_combo.currentText()
        if picked not in labels:
            self.error_label.setText("Selecciona una condición válida.")
            self.error_label.show()
            return
        condition = list(CONDITIONS.keys())[labels.index(picked)]

        value = 0.0
        period_hours = 1
        if condition in THRESHOLD_CONDITIONS:
            try:
                value = float(self.value_edit.text().replace(",", "."))
            except ValueError:
                self.error_label.setText("El valor objetivo debe ser un número.")
                self.error_label.show()
                return
        else:
            try:
                period_hours = int(self.period_combo.currentText())
            except ValueError:
                period_hours = 1
            if period_hours not in PERIOD_OPTIONS:
                period_hours = 1

        data = {
            "currency": currency,
            "condition": condition,
            "value": value,
            "period_hours": period_hours,
            "enabled": self.enabled_check.isChecked(),
            "notify_once": self.notify_once_check.isChecked() if condition in THRESHOLD_CONDITIONS else False,
        }
        if self.alert is not None and self.alert.last_fired_at:
            data["last_fired_at"] = self.alert.last_fired_at
        if self.alert is not None:
            data["id"] = self.alert.id
            data["created_at"] = self.alert.created_at
        self.result = Alert.from_dict(data)
        self.accept()


# ──────────────────────────────────────────────── History Dialog (QDialog)
# ---------------------------------------------------------------------------

class HistoryDialog(QDialog):
    """Popup con el historial de notificaciones emitidas."""

    def __init__(self, log: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Historial de notificaciones")
        self.setMinimumSize(460, 320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Notificaciones emitidas"))

        self.list_widget = QListWidget()
        if log:
            self.list_widget.addItems(log)
        else:
            self.list_widget.addItem("Todavía no hay notificaciones.")
        layout.addWidget(self.list_widget)

        btn = QPushButton("Cerrar")
        btn.setProperty("cssClass", "outline")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignCenter)


# ──────────────────────────────────────────────── Main Window (QMainWindow)
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Ventana principal de Currency Watcher."""

    def __init__(
        self,
        config: Config,
        config_manager: ConfigManager,
        history: Any | None = None,
    ):
        super().__init__()
        self.config = config
        self.config_manager = config_manager
        self.history = history

        self.setWindowTitle("Currency Watcher — Monitor de tipos de cambio")
        self.setWindowIcon(QIcon(str(asset_path("icon.png"))))
        self.resize(980, 800)
        self.setMinimumSize(860, 660)

        # Estado de precios: {MONEDA: {"rate": float, "prev": float|None, "time": str}}
        self.rates_state: dict[str, dict[str, Any]] = {}
        self.periodic_refs: dict[str, dict[str, Any]] = {}
        self.notification_log: list[str] = []
        self._search_term = ""
        self._only_fav = False

        # Worker thread (creado antes de _build_ui porque los botones se conectan a él)
        self._worker = _WorkerThread(
            get_base=lambda: self.config.base_currency,
            history=self.history,
            parent=self,
        )
        self._worker.signals.rates_ready.connect(self._on_rates)
        self._worker.signals.error.connect(self._on_error)
        self._worker.signals.loading.connect(self._on_loading)

        self._build_ui()
        self._apply_theme(config.theme)
        self._refresh_alerts_list()

        self._worker.start()

        # Auto-refresh timer
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._worker.request_refresh)
        self._auto_timer.setInterval(config.refresh_interval * 1000)
        if config.auto_refresh:
            self._auto_timer.start()

        # Notificaciones
        from notifier import set_fallback
        set_fallback(self._in_app_notification)

        # System tray
        self._setup_tray()

        # Primera carga
        QTimer.singleShot(250, self._worker.request_refresh)

    # ──────────────────────────────────────────────────────── UI Build
    # -------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Toolbar
        self._build_toolbar(main_layout)

        # Splitter: [tabla + gráfico] | [alertas]
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        # Panel izquierdo: tabla + gráfico
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._build_rates_table(left_layout)
        self._build_chart(left_layout)
        splitter.addWidget(left)

        # Panel derecho: alertas
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._build_alerts_panel(right_layout)
        splitter.addWidget(right)

        splitter.setSizes([650, 310])

        # Status bar
        self._build_status_bar()

    def _build_toolbar(self, parent_layout: QVBoxLayout):
        toolbar = QToolBar("Principal")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("Moneda base:"))
        self.base_combo = QComboBox()
        self.base_combo.addItems(list(SUPPORTED_CURRENCIES.keys()))
        idx = self.base_combo.findText(self.config.base_currency)
        if idx >= 0:
            self.base_combo.setCurrentIndex(idx)
        self.base_combo.currentIndexChanged.connect(self._on_base_change)
        toolbar.addWidget(self.base_combo)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Tema:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        idx = self.theme_combo.findText(self.config.theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_change)
        toolbar.addWidget(self.theme_combo)

        toolbar.addSeparator()

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.clicked.connect(self._worker.request_refresh)
        toolbar.addWidget(btn_refresh)

        self.spinner = Spinner(self)
        self.spinner.setToolTip("Actualizando tasas…")
        toolbar.addWidget(self.spinner)

        toolbar.addWidget(QLabel("Intervalo:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["30", "60", "300"])
        idx = self.interval_combo.findText(str(self.config.refresh_interval))
        if idx >= 0:
            self.interval_combo.setCurrentIndex(idx)
        self.interval_combo.currentIndexChanged.connect(self._on_interval_change)
        toolbar.addWidget(self.interval_combo)

        self.auto_check = QCheckBox("Auto")
        self.auto_check.setChecked(self.config.auto_refresh)
        self.auto_check.toggled.connect(self._on_auto_toggle)
        toolbar.addWidget(self.auto_check)

        from PySide6.QtWidgets import QSizePolicy
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        toolbar.addWidget(spacer)

        btn_export = QPushButton("Exportar")
        btn_export.setProperty("cssClass", "outline")
        btn_export.clicked.connect(self._export)
        toolbar.addWidget(btn_export)

    def _build_rates_table(self, layout: QVBoxLayout):
        group = QGroupBox("Precios actuales")
        group_layout = QVBoxLayout(group)

        # Buscador y filtro
        top = QHBoxLayout()
        top.addWidget(QLabel("Buscar:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtrar moneda...")
        self.search_edit.setMaximumWidth(180)
        self.search_edit.textChanged.connect(self._on_search)
        top.addWidget(self.search_edit)

        top.addWidget(QLabel("Gráfico:"))
        self.chart_currency_combo = QComboBox()
        self.chart_currency_combo.currentIndexChanged.connect(self._on_chart_currency_change)
        self._rebuild_chart_currency_combo()
        top.addWidget(self.chart_currency_combo)

        top.addWidget(QLabel("último:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["6h", "24h", "3d", "7d"])
        self.range_combo.setCurrentText("24h")
        self.range_combo.currentIndexChanged.connect(self._on_range_change)
        top.addWidget(self.range_combo)

        self.fav_check = QCheckBox("Solo favoritas")
        self.fav_check.toggled.connect(self._on_fav_toggle)
        top.addWidget(self.fav_check)
        top.addStretch()
        group_layout.addLayout(top)

        # Tabla MVC
        self.table_model = RateTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectRows)
        self.table_view.setSelectionMode(QTableView.SingleSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setShowGrid(True)
        self.table_view.verticalHeader().setVisible(False)
        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(True)
        for i, w in enumerate(COL_WIDTHS):
            header.resizeSection(i, w)
        self.table_view.clicked.connect(self._on_table_click)
        group_layout.addWidget(self.table_view)

        layout.addWidget(group, 1)

    def _build_chart(self, layout: QVBoxLayout):
        group = QGroupBox("Evolución histórica")
        group_layout = QVBoxLayout(group)
        self.chart = ChartWidget()
        group_layout.addWidget(self.chart)
        layout.addWidget(group)

    def _build_alerts_panel(self, layout: QVBoxLayout):
        group = QGroupBox("Alertas / Notificaciones")
        group_layout = QVBoxLayout(group)

        self.alerts_list = QListWidget()
        group_layout.addWidget(self.alerts_list, 1)

        # Botones de acciones
        btns = QVBoxLayout()
        btn_new = QPushButton("Nueva alerta")
        btn_new.setProperty("cssClass", "success")
        btn_new.clicked.connect(self._new_alert)
        btns.addWidget(btn_new)

        btn_edit = QPushButton("Editar")
        btn_edit.clicked.connect(self._edit_alert)
        btns.addWidget(btn_edit)

        btn_toggle = QPushButton("Activar / Desactivar")
        btn_toggle.setProperty("cssClass", "warning")
        btn_toggle.clicked.connect(self._toggle_alert)
        btns.addWidget(btn_toggle)

        btn_delete = QPushButton("Eliminar")
        btn_delete.setProperty("cssClass", "danger")
        btn_delete.clicked.connect(self._delete_alert)
        btns.addWidget(btn_delete)

        btn_history = QPushButton("Historial de notificaciones")
        btn_history.setProperty("cssClass", "outline")
        btn_history.clicked.connect(self._show_history)
        btns.addWidget(btn_history)

        group_layout.addLayout(btns)
        layout.addWidget(group)

    def _build_status_bar(self):
        bar = self.statusBar()
        self.status_label = QLabel("● Listo")
        bar.addWidget(self.status_label)
        self.msg_label = QLabel("")
        bar.addPermanentWidget(self.msg_label)

    # ──────────────────────────────────────────────────────── Theme
    # -------------------------------------------------------------------

    def _apply_theme(self, theme_name: str):
        if theme_name not in THEMES:
            theme_name = "darkly" if "darkly" in THEMES else list(THEMES.keys())[0]
        theme = THEMES[theme_name]
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_qss(theme))
        global COLOR_TEXT, COLOR_BG, COLOR_SURFACE, COLOR_SURFACE_ALT, COLOR_BORDER, COLOR_FAV
        COLOR_TEXT = theme["fg"]
        COLOR_BG = theme["bg"]
        COLOR_SURFACE = theme["surface"]
        COLOR_SURFACE_ALT = _shade(theme["surface"], 0.92 if theme["bg"].startswith("#f") or theme["bg"] == "#fff" else 1.12)
        COLOR_BORDER = theme["border"]
        COLOR_FAV = theme.get("warning", "#f39c12")
        self.chart.update()

    # ──────────────────────────────────────────────────── Slots / Events
    # -------------------------------------------------------------------

    def _rebuild_chart_currency_combo(self):
        """Refresca el desplegable de moneda del gráfico según la base actual.

        Excluye la moneda base y conserva la selección anterior si existe.
        """
        current = self.chart_currency_combo.currentData()
        self.chart_currency_combo.blockSignals(True)
        self.chart_currency_combo.clear()
        base = self.config.base_currency
        for code, name in SUPPORTED_CURRENCIES.items():
            if code == base:
                continue
            self.chart_currency_combo.addItem(f"{code} ({name})", userData=code)
        idx = self.chart_currency_combo.findData(current if current != base else "EUR")
        if idx < 0:
            idx = self.chart_currency_combo.findData("EUR")
        self.chart_currency_combo.setCurrentIndex(max(0, idx))
        self.chart_currency_combo.blockSignals(False)

    def _on_base_change(self):
        self.config.base_currency = self.base_combo.currentText()
        self._rebuild_chart_currency_combo()
        self._render_chart()
        self._worker.request_refresh()
        self._save_config()

    def _on_theme_change(self):
        theme = self.theme_combo.currentText()
        if theme not in THEMES:
            return
        self.config.theme = theme
        self._apply_theme(theme)
        self._save_config()

    def _on_interval_change(self):
        try:
            self.config.refresh_interval = int(self.interval_combo.currentText())
        except ValueError:
            return
        self._auto_timer.setInterval(self.config.refresh_interval * 1000)
        self._save_config()

    def _on_auto_toggle(self, checked):
        self.config.auto_refresh = checked
        if checked:
            self._auto_timer.start()
            self._worker.request_refresh()
        else:
            self._auto_timer.stop()
        self._save_config()

    def _on_search(self, text):
        self._search_term = text.strip().lower()
        self._render_table()

    def _on_fav_toggle(self, checked):
        self._only_fav = checked
        self._render_table()

    def _on_range_change(self):
        self._render_chart()

    def _on_chart_currency_change(self):
        self._render_chart()

    def _on_table_click(self, index: QModelIndex):
        if not index.isValid():
            return
        col = index.column()
        if col == 0:  # Fav column
            row = index.row()
            code = self.table_model.get_code(row)
            if code:
                if code in self.config.favorites:
                    self.config.favorites.remove(code)
                else:
                    self.config.favorites.append(code)
                self._save_config()
                self._render_table()

    # ──────────────────────────────────────────────────── Data / Rendering
    # ----------------------------------------------------------------------

    def _on_loading(self, loading: bool):
        if loading:
            self.spinner.start()
        else:
            self.spinner.stop()

    @Slot(dict)
    def _on_rates(self, item: dict):
        rates = item["rates"]
        base = item["base"]
        stamp = item["stamp"]
        now = datetime.now().strftime("%H:%M:%S")

        for code, rate in rates.items():
            prev = None
            if code in self.rates_state:
                prev = self.rates_state[code].get("rate")
            self.rates_state[code] = {"rate": rate, "prev": prev, "time": stamp}

        self._render_table(base, now)
        self._render_chart()
        self._check_alerts()
        self._flash_status(f"Actualizado {now}", COLOR_UP)
        self.msg_label.setText("")

    @Slot(str)
    def _on_error(self, message: str):
        now = datetime.now().strftime("%H:%M:%S")
        self._flash_status(f"Error {now}", COLOR_DOWN)
        self.msg_label.setText(message)
        self.msg_label.setStyleSheet(f"color: {COLOR_DOWN};")
        for code in SUPPORTED_CURRENCIES:
            if code not in self.rates_state:
                self.rates_state[code] = {"rate": None, "prev": None, "time": None}
        self._render_table(self.config.base_currency, now)

    def _render_table(self, base: str | None = None, now: str | None = None):
        if base is None:
            base = self.config.base_currency
        if now is None:
            now = datetime.now().strftime("%H:%M:%S")

        rows = []
        colors = []
        fav_colors = []

        for code, name in SUPPORTED_CURRENCIES.items():
            if code == base:
                continue
            if self._search_term and self._search_term not in code.lower() and self._search_term not in name.lower():
                continue
            state = self.rates_state.get(code)
            rate = state["rate"] if state else None
            prev = state["prev"] if state else None
            stamp = state["time"] if state else None

            is_fav = code in self.config.favorites
            if self._only_fav and not is_fav:
                continue

            tag_color = ""
            change_text = "—"
            pct_text = "—"
            status_text = "OK" if rate is not None else "Sin datos"

            if rate is not None and prev is not None:
                diff = rate - prev
                if abs(diff) < 1e-12:
                    change_text = "0"
                    pct_text = "0.00%"
                elif diff > 0:
                    change_text = f"+{diff:.6g}"
                    pct_text = f"+{(diff / prev) * 100:.2f}%"
                    tag_color = COLOR_UP
                else:
                    change_text = f"{diff:.6g}"
                    pct_text = f"{(diff / prev) * 100:.2f}%"
                    tag_color = COLOR_DOWN

            price_display = f"{rate:.6g}" if rate is not None else "—"
            time_display = (stamp or "—").split("T")[-1][:8] if stamp else "—"

            rows.append([
                "★" if is_fav else "☆",
                CURRENCY_SYMBOLS.get(code, code),
                code,
                name,
                price_display,
                time_display,
                change_text,
                pct_text,
                status_text,
            ])
            colors.append(tag_color)
            fav_colors.append(COLOR_FAV if is_fav else "")

        self.table_model.update_data(rows, colors, fav_colors)

    def _render_chart(self):
        if self.history is None:
            return
        base = self.config.base_currency
        range_label = self.range_combo.currentText()
        hours_map = {"6h": 6, "24h": 24, "3d": 72, "7d": 168}
        hours = hours_map.get(range_label, 24)

        idx = self.chart_currency_combo.currentIndex()
        cur = self.chart_currency_combo.itemData(idx) if idx >= 0 else "EUR"

        series = self.history.series(base, cur, hours=hours, limit=1000)
        self.chart.set_data(series, cur, range_label)

    # ──────────────────────────────────────────────────── Alerts
    # -----------------------------------------------------------------

    def _refresh_alerts_list(self):
        self.alerts_list.clear()
        for alert in self.config.alerts:
            state = "ON " if alert.enabled else "OFF"
            once = " (1 vez)" if alert.notify_once else ""
            self.alerts_list.addItem(f"[{state}]{once} {describe_condition(alert)}")

    def _selected_alert(self) -> Alert | None:
        row = self.alerts_list.currentRow()
        if row < 0 or row >= len(self.config.alerts):
            return None
        return self.config.alerts[row]

    def _new_alert(self):
        dlg = AlertDialog(self, self.config.base_currency)
        if dlg.exec() == QDialog.Accepted and dlg.result is not None:
            self.config_manager.add_alert(self.config, dlg.result.to_dict())
            self._save_config()
            self._refresh_alerts_list()

    def _edit_alert(self):
        alert = self._selected_alert()
        if alert is None:
            self.msg_label.setText("Selecciona una alerta para editar.")
            return
        working = copy_alert(alert)
        dlg = AlertDialog(self, self.config.base_currency, working)
        if dlg.exec() == QDialog.Accepted and dlg.result is not None:
            self.config_manager.update_alert(self.config, alert.id, dlg.result.to_dict())
            self._save_config()
            self._refresh_alerts_list()

    def _toggle_alert(self):
        alert = self._selected_alert()
        if alert is None:
            self.msg_label.setText("Selecciona una alerta para activar/desactivar.")
            return
        alert.enabled = not alert.enabled
        if alert.enabled:
            alert.trigger_on_next_check = False
        self._save_config()
        self._refresh_alerts_list()
        self.msg_label.setText(f"Alerta {alert.currency} {'activada' if alert.enabled else 'desactivada'}.")

    def _delete_alert(self):
        alert = self._selected_alert()
        if alert is None:
            self.msg_label.setText("Selecciona una alerta para eliminar.")
            return
        self.config_manager.delete_alert(self.config, alert.id)
        self._save_config()
        self._refresh_alerts_list()
        self.msg_label.setText(f"Alerta {alert.currency} eliminada.")

    # ──────────────────────────────────────────────── Check Alerts Logic
    # ---------------------------------------------------------------------

    def _check_alerts(self):
        base = self.config.base_currency
        now = datetime.now(timezone.utc)
        before = [(a.id, a.enabled, a.last_fired_at) for a in self.config.alerts]

        for alert in list(self.config.alerts):
            if not alert.enabled or alert.currency == base:
                continue
            cs = self.rates_state.get(alert.currency)
            if cs is None:
                continue
            current = cs.get("rate")
            if current is None:
                continue

            if is_periodic(alert):
                if self._check_periodic(alert, current, base, now):
                    if alert.notify_once:
                        alert.enabled = False
                        self._refresh_alerts_list()
                continue

            previous = cs.get("prev")
            if alert.trigger_on_next_check is False and previous is None:
                alert.trigger_on_next_check = True
                continue

            triggered, description = evaluate(alert, current, previous)
            if triggered:
                self._fire_alert(alert, current, base, description)
                if alert.notify_once:
                    alert.enabled = False
                    self._refresh_alerts_list()

        after = [(a.id, a.enabled, a.last_fired_at) for a in self.config.alerts]
        if before != after:
            self._save_config()

    def _check_periodic(self, alert, current, base, now):
        alert_id = alert.id
        ref = self.periodic_refs.get(alert_id)
        if ref is None:
            self.periodic_refs[alert_id] = {
                "price": current,
                "time": now.isoformat(timespec="seconds"),
            }
            return False

        last_fired = self._parse_iso(alert.last_fired_at) or self._parse_iso(ref.get("time"))
        elapsed_h = (now - last_fired).total_seconds() / 3600.0 if last_fired else 0.0
        if elapsed_h < alert.period_hours:
            return False

        ref_price = ref.get("price")
        self._fire_periodic_report(alert, ref_price, current, base, ref.get("time"), now)
        alert.last_fired_at = now.isoformat(timespec="seconds")
        self.periodic_refs[alert_id] = {
            "price": current,
            "time": now.isoformat(timespec="seconds"),
        }
        return True

    @staticmethod
    def _parse_iso(value):
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _fire_periodic_report(self, alert, ref_price, current, base, ref_time, now):
        currency_name = SUPPORTED_CURRENCIES.get(alert.currency, alert.currency)
        ref_dt = self._parse_iso(ref_time)
        period_label = PERIOD_OPTIONS.get(alert.period_hours, f"{alert.period_hours} h").lower()

        lines = [
            f"Informe periódico ({period_label}) de {alert.currency} ({currency_name}).",
            f"Moneda base: {base}",
            f"Precio actual: {current:.6g}",
        ]
        if ref_price is not None and ref_price > 0:
            pct = ((current - ref_price) / ref_price) * 100.0
            diff = current - ref_price
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "•")
            trend = "ha subido" if diff > 0 else ("ha bajado" if diff < 0 else "se ha mantenido")
            ref_label = f"la actualización de las {ref_dt.strftime('%H:%M:%S')}" if ref_dt else "la última actualización"
            lines.append(f"Respecto a {ref_label}: {arrow} {diff:+.6g} ({pct:+.2f}%).")
            lines.append(f"La moneda {alert.currency} {trend} en este periodo.")
        else:
            lines.append("Sin referencia previa para calcular la variación.")
        lines.append(f"Hora: {now.strftime('%H:%M:%S')}")

        try:
            notify("Informe de moneda", "\n".join(lines))
        except Exception:
            pass

    def _fire_alert(self, alert, current, base, description):
        now = datetime.now().strftime("%H:%M:%S")
        currency_name = SUPPORTED_CURRENCIES.get(alert.currency, alert.currency)
        message = (
            f"La moneda {alert.currency} ({currency_name}) ha cumplido la condición.\n"
            f"Precio actual: {current:.6g}\n"
            f"Condición: {description}\n"
            f"Moneda base: {base}\n"
            f"Hora: {now}"
        )
        try:
            notify("Alerta de moneda", message)
        except Exception:
            pass

    # ──────────────────────────────────────────────── Notification / History
    # ------------------------------------------------------------------------

    def _in_app_notification(self, title, message):
        self.notification_log.append(f"{title}: {message}")
        if len(self.notification_log) > 50:
            self.notification_log = self.notification_log[-50:]
        QTimer.singleShot(0, lambda: self.msg_label.setText(f"{title}: {message}"))

    def _show_history(self):
        dlg = HistoryDialog(self.notification_log, self)
        dlg.exec()

    # ──────────────────────────────────────────────── Export
    # ---------------------------------------------------------------

    def _build_history_matrix(self) -> tuple[str, list[str], list[str], dict[str, dict[str, float]]]:
        """Reúne el historial en una matriz: {moneda: {ts: rate}}.

        Devuelve (base, currencies, timestamps_ordenados, matrix).
        """
        base = self.config.base_currency
        currencies = list(SUPPORTED_CURRENCIES)
        by_currency: dict[str, dict[str, float]] = {c: {} for c in currencies}
        if self.history is not None:
            for currency in currencies:
                for sample in self.history.series(base, currency, hours=24 * 30, limit=10000):
                    by_currency[currency][sample["ts"]] = sample["rate"]
        timestamps = sorted(set().union(*(c.keys() for c in by_currency.values())))
        return base, currencies, timestamps, by_currency

    def _export(self):
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Exportar datos", f"rates_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        try:
            p = Path(path)
            if path.endswith(".json"):
                base, currencies, timestamps, by_currency = self._build_history_matrix()
                payload = {
                    "base": base,
                    "exported_at": datetime.now().isoformat(timespec="seconds"),
                    "currencies": currencies,
                    "samples": [
                        {"ts": ts, **{c: by_currency[c].get(ts) for c in currencies}}
                        for ts in timestamps
                    ],
                }
                p.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                base, currencies, timestamps, by_currency = self._build_history_matrix()
                with open(p, "w", encoding="utf-8", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["base", "ts", *currencies])
                    for ts in timestamps:
                        writer.writerow([
                            base,
                            ts,
                            *(by_currency[c].get(ts, "") for c in currencies),
                        ])
            self.msg_label.setText(f"Exportado: {p.name}")
        except Exception as exc:
            self.msg_label.setText(f"No se pudo exportar: {exc}")

    # ──────────────────────────────────────────────── System Tray
    # ---------------------------------------------------------------

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(QIcon(str(asset_path("icon.png"))))
        self._tray.setToolTip("Currency Watcher")
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Mostrar")
        show_action.triggered.connect(self._show_from_tray)
        quit_action = tray_menu.addAction("Salir")
        quit_action.triggered.connect(self._real_close)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    # ──────────────────────────────────────────────── Misc / Status
    # ---------------------------------------------------------------

    def _set_status(self, text, color=None):
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;" if color else "")

    def _flash_status(self, text, color):
        """Muestra el estado con un destello de color que se desvanece."""
        self._set_status(text, color)
        QTimer.singleShot(900, lambda: self._set_status(text))

    def _save_config(self):
        self.config_manager.save(self.config)

    def _shutdown(self):
        """Detiene el worker y cierra el historial de forma ordenada."""
        if hasattr(self, '_worker'):
            self._worker.stop()
        if self.history is not None:
            self.history.close()

    def closeEvent(self, event):
        self._save_config()
        if hasattr(self, '_tray') and self._tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self._shutdown()
            event.accept()

    def _real_close(self):
        self._save_config()
        if hasattr(self, '_tray'):
            self._tray.hide()
        self._shutdown()
        QApplication.instance().quit()
