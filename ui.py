"""
Interfaz gráfica con ttkbootstrap.

Este módulo contiene toda la parte visual de ttkbootstrap/tkinter, así como la
integración con el bucle de eventos de asyncio. La lógica de negocio (tasas,
alertas, configuración) se delega en los otros módulos.

Para combinar tkinter con asyncio se usa la siguiente estrategia:
  - El bucle de asyncio se ejecuta en un hilo en segundo plano (ver main.py).
  - La interfaz usa `root.after(...)` para consultar periódicamente una cola
    segura (`queue.Queue`) en la que las corrutinas depositan resultados.
  - Las corrutinas envían datos a la interfaz a través de esa cola en lugar de
    tocar directamente los widgets (acceso seguro entre hilos).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Any, Callable

import ttkbootstrap as ttk

from alerts import evaluate
from config import (
    CONDITIONS,
    SUPPORTED_CURRENCIES,
    Alert,
    Config,
    ConfigManager,
    copy_alert,
)
from notifier import notify, is_available


class RatesController:
    """Puente entre la interfaz y el worker asíncrono.

    Expone `request()` para pedir una actualización sin bloquear, y la cola
    `results` que la interfaz consume periódicamente para refrescar los widgets.
    """

    def __init__(self) -> None:
        self.results: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._request_fn: Callable[[], None] | None = None

    def set_request_handler(self, handler: Callable[[], None]) -> None:
        """Conecta el handler que dispara la petición asíncrona real."""
        self._request_fn = handler

    def request(self) -> None:
        """Pide una actualización (no bloqueante)."""
        if self._request_fn is not None:
            try:
                self._request_fn()
            except Exception:
                pass


class AlertDialog:
    """Ventana modal para crear o editar una alerta."""

    def __init__(self, parent: ttk.Window, base_currency: str, alert: Alert | None = None) -> None:
        self.parent = parent
        self.base_currency = base_currency
        self.alert = alert
        self.result: Alert | None = None

        self.dialog = ttk.Toplevel(parent)
        self.dialog.title("Nueva alerta" if alert is None else "Editar alerta")
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        self._build_widgets()
        self._center_on_parent()
        self.dialog.transient(parent)
        self.dialog.bind("<Return>", lambda _e: self._save())
        self.dialog.bind("<Escape>", lambda _e: self._cancel())

    def _center_on_parent(self) -> None:
        self.dialog.update_idletasks()
        x = self.parent.winfo_rootx() + 40
        y = self.parent.winfo_rooty() + 40
        self.dialog.geometry(f"+{x}+{y}")

    def _build_widgets(self) -> None:
        pad = {"padx": 12, "pady": 6}

        # ----- Moneda -----
        ttk.Label(self.dialog, text="Moneda:").grid(row=0, column=0, sticky="w", **pad)
        self.currency_var = tk.StringVar(
            value=self.alert.currency if self.alert else "EUR"
        )
        currency_box = ttk.Combobox(
            self.dialog,
            textvariable=self.currency_var,
            values=list(SUPPORTED_CURRENCIES.keys()),
            state="readonly",
            width=14,
        )
        currency_box.grid(row=0, column=1, sticky="w", **pad)

        # ----- Condición -----
        ttk.Label(self.dialog, text="Condición:").grid(row=1, column=0, sticky="w", **pad)
        self.condition_var = tk.StringVar(
            value=self.alert.condition if self.alert else "greater_than"
        )
        condition_labels = [c["label"] for c in CONDITIONS.values()]
        condition_box = ttk.Combobox(
            self.dialog,
            textvariable=self.condition_var,
            values=condition_labels,
            state="readonly",
            width=30,
        )
        condition_box.grid(row=1, column=1, sticky="w", **pad)

        # ----- Valor -----
        ttk.Label(self.dialog, text="Valor objetivo:").grid(row=2, column=0, sticky="w", **pad)
        self.value_var = tk.StringVar(
            value=f"{self.alert.value:g}" if self.alert and self.alert.value else ""
        )
        self.value_entry = ttk.Entry(self.dialog, textvariable=self.value_var, width=32)
        self.value_entry.grid(row=2, column=1, sticky="w", **pad)

        # ----- Opciones -----
        self.notify_once_var = tk.BooleanVar(
            value=self.alert.notify_once if self.alert else False
        )
        ttk.Checkbutton(
            self.dialog, text="Notificar una sola vez", variable=self.notify_once_var
        ).grid(row=3, column=1, sticky="w", **pad)

        self.enabled_var = tk.BooleanVar(
            value=self.alert.enabled if self.alert else True
        )
        ttk.Checkbutton(
            self.dialog, text="Activada al guardar", variable=self.enabled_var
        ).grid(row=4, column=1, sticky="w", **pad)

        # ----- Botones -----
        buttons = ttk.Frame(self.dialog)
        buttons.grid(row=5, column=0, columnspan=2, pady=14)
        ttk.Button(buttons, text="Guardar", command=self._save, bootstyle="success").pack(
            side="left", padx=8
        )
        ttk.Button(buttons, text="Cancelar", command=self._cancel, bootstyle="secondary").pack(
            side="left", padx=8
        )

    def _save(self) -> None:
        """Valida los campos y construye la Alert resultante."""
        currency = self.currency_var.get()
        if currency not in SUPPORTED_CURRENCIES:
            self._show_error("Selecciona una moneda válida.")
            return

        labels = [c["label"] for c in CONDITIONS.values()]
        picked_label = self.condition_var.get()
        if picked_label not in labels:
            self._show_error("Selecciona una condición válida.")
            return
        condition = list(CONDITIONS.keys())[labels.index(picked_label)]

        try:
            value = float(self.value_var.get().replace(",", "."))
        except ValueError:
            self._show_error("El valor objetivo debe ser un número.")
            return

        data = {
            "currency": currency,
            "condition": condition,
            "value": value,
            "enabled": self.enabled_var.get(),
            "notify_once": self.notify_once_var.get(),
        }
        if self.alert is not None:
            data["id"] = self.alert.id
            data["created_at"] = self.alert.created_at
            self.result = Alert.from_dict(data)
        else:
            self.result = Alert.from_dict(data)

        self.dialog.destroy()

    def _cancel(self) -> None:
        self.dialog.destroy()

    def _show_error(self, message: str) -> None:
        """Muestra un aviso dentro de la ventana de alerta."""
        reason = getattr(self, "_error_label", None)
        if reason is None or not reason.winfo_exists():
            self._error_label = ttk.Label(self.dialog, text="", bootstyle="danger")
            self._error_label.grid(row=6, column=0, columnspan=2, **{"padx": 12, "pady": 4})
        self._error_label.config(text=message)


class CurrencyWatcherUI:
    """Ventana principal de la aplicación."""

    def __init__(
        self,
        root: ttk.Window,
        config: Config,
        config_manager: ConfigManager,
        controller: RatesController,
    ) -> None:
        self.root = root
        self.config = config
        self.config_manager = config_manager
        self.controller = controller

        self.root.title("Currency Watcher — Monitor de tipos de cambio")
        self.root.geometry("860x620")
        self.root.minsize(720, 520)

        # Estado de precios: {MONEDA: {"rate": float, "prev": float|None, "time": str}}
        self.rates_state: dict[str, dict[str, Any]] = {}
        # Estado de estado de actualización global.
        self.status_var = tk.StringVar(value="Listo")

        # Construcción de la interfaz.
        self._build_ui()
        self._refresh_alerts_table()

        # Consumo periódico de la cola con resultados del worker asíncrono.
        self.root.after(150, self._poll_results)

        # Registramos el fallback de notificaciones dentro de la aplicación.
        from notifier import set_fallback

        set_fallback(self._in_app_notification)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self._build_header()
        self._build_rates_table()
        self._build_status_bar()
        self._build_alerts_panel()

    def _build_header(self) -> None:
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=(10, 6))

        ttk.Label(header, text="Currency Watcher", font=("", 16, "bold")).pack(
            side="left", padx=(0, 20)
        )

        # Selector de moneda base.
        ttk.Label(header, text="Moneda base:").pack(side="left")
        self.base_var = tk.StringVar(value=self.config.base_currency)
        base_box = ttk.Combobox(
            header,
            textvariable=self.base_var,
            values=list(SUPPORTED_CURRENCIES.keys()),
            state="readonly",
            width=5,
        )
        base_box.pack(side="left", padx=6)
        base_box.bind("<<ComboboxSelected>>", lambda _e: self._on_base_change())

        # Botón de actualización manual.
        ttk.Button(
            header, text="Actualizar", command=self.manual_refresh, bootstyle="primary"
        ).pack(side="left", padx=10)

        # Selector de intervalo.
        ttk.Label(header, text="Intervalo:").pack(side="left", padx=(10, 0))
        self.interval_var = tk.IntVar(value=self.config.refresh_interval)
        interval_box = ttk.Combobox(
            header,
            textvariable=self.interval_var,
            values=[30, 60, 300],
            state="readonly",
            width=6,
        )
        interval_box.pack(side="left", padx=6)
        interval_box.bind("<<ComboboxSelected>>", lambda _e: self._on_interval_change())

        # Botón iniciar/detener actualización automática.
        self.auto_var = tk.BooleanVar(value=self.config.auto_refresh)
        self.auto_button = ttk.Checkbutton(
            header,
            text="Auto",
            variable=self.auto_var,
            command=self._on_auto_toggle,
            bootstyle="round-toggle",
        )
        self.auto_button.pack(side="left", padx=10)

    def _build_rates_table(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Precios actuales", padding=8)
        frame.pack(fill="both", expand=True, padx=10, pady=6)

        columns = ("clock", "currency", "currency_name", "price", "time", "change", "change_pct", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)

        headings = [
            ("clock", "Símbolo"),
            ("currency", "Código"),
            ("currency_name", "Moneda"),
            ("price", "Precio actual"),
            ("time", "Última actualización"),
            ("change", "Cambio"),
            ("change_pct", "Variación"),
            ("status", "Estado"),
        ]
        widths = {
            "clock": 40,
            "currency": 70,
            "currency_name": 180,
            "price": 110,
            "time": 130,
            "change": 90,
            "change_pct": 90,
            "status": 100,
        }
        for col_name, text in headings:
            self.tree.heading(col_name, text=text)
            self.tree.column(col_name, width=widths[col_name], anchor="w")

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # Tagging de colores: verde=sube, rojo=baja, gris/amarillo=sin datos/error.
        self.tree.tag_configure("up", foreground="#2ecc71")
        self.tree.tag_configure("down", foreground="#e74c3c")
        self.tree.tag_configure("neutral", foreground="#f1c40f")
        self.tree.tag_configure("error", foreground="#95a5a6")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=(2, 6))

        self.status_dot = ttk.Label(bar, text="●", width=2, bootstyle="secondary")
        self.status_dot.pack(side="left")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left", padx=6)

        self.msg_label = ttk.Label(bar, text="", bootstyle="secondary")
        self.msg_label.pack(side="right")

    def _build_alerts_panel(self) -> None:
        panel = ttk.LabelFrame(self.root, text="Alertas / Notificaciones", padding=8)
        panel.pack(fill="x", padx=10, pady=(6, 10))

        row = ttk.Frame(panel)
        row.pack(fill="x")

        self.alerts_list = tk.Listbox(row, height=5)
        self.alerts_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(row, orient="vertical", command=self.alerts_list.yview)
        self.alerts_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        actions = ttk.Frame(row)
        actions.pack(side="right", padx=(10, 0), fill="y")
        ttk.Button(
            actions, text="Nueva alerta", command=self._new_alert, bootstyle="success"
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions, text="Editar", command=self._edit_alert, bootstyle="primary"
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions, text="Activar / Desactivar", command=self._toggle_alert, bootstyle="warning"
        ).pack(fill="x", pady=2)
        ttk.Button(
            actions, text="Eliminar", command=self._delete_alert, bootstyle="danger"
        ).pack(fill="x", pady=2)

    # ------------------------------------------------------------ status

    def _set_status(self, text: str, style: str = "secondary") -> None:
        """Actualiza la barra de estado (actualizando, actualizado, error)."""
        self.status_var.set(text)
        try:
            self.status_dot.configure(bootstyle=style)
        except Exception:
            pass

    def _set_message(self, text: str, style: str = "secondary") -> None:
        self.msg_label.configure(text=text, bootstyle=style)

    # ------------------------------------------------ interacción de UI

    def _on_base_change(self) -> None:
        self.config.base_currency = self.base_var.get()
        self.controller.request()
        self._save_config()

    def _on_interval_change(self) -> None:
        self.config.refresh_interval = int(self.interval_var.get())
        self._save_config()

    def _on_auto_toggle(self) -> None:
        self.config.auto_refresh = self.auto_var.get()
        if self.config.auto_refresh:
            self.controller.request()
        self._save_config()

    def manual_refresh(self) -> None:
        self.controller.request()

    # ---------------------------------------------------- gestión alertas

    def _refresh_alerts_table(self) -> None:
        """Vuelve a pintar la lista de alertas desde la configuración actual."""
        self.alerts_list.delete(0, tk.END)
        for alert in self.config.alerts:
            state = "ON " if alert.enabled else "OFF"
            once = " (1 vez)" if alert.notify_once else ""
            self.alerts_list.insert(tk.END, f"[{state}]{once} {_alert_line(alert)}")

    def _selected_alert(self) -> Alert | None:
        sel = self.alerts_list.curselection()
        if not sel:
            return None
        idx = sel[0]
        if idx >= len(self.config.alerts):
            return None
        return self.config.alerts[idx]

    def _new_alert(self) -> None:
        dialog = AlertDialog(self.root, self.config.base_currency)
        self.root.wait_window(dialog.dialog)
        if dialog.result is not None:
            self.config_manager.add_alert(self.config, dialog.result.to_dict())
            self._save_config()
            self._refresh_alerts_table()

    def _edit_alert(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            self._set_message("Selecciona una alerta para editar.", "warning")
            return
        working = copy_alert(alert)
        dialog = AlertDialog(self.root, self.config.base_currency, working)
        self.root.wait_window(dialog.dialog)
        if dialog.result is not None:
            self.config_manager.update_alert(
                self.config, alert.id, dialog.result.to_dict()
            )
            self._save_config()
            self._refresh_alerts_table()

    def _toggle_alert(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            self._set_message("Selecciona una alerta para activar/desactivar.", "warning")
            return
        alert.enabled = not alert.enabled
        if alert.enabled:
            # Al re-activar, permitimos que vuelva a dispararse.
            alert.trigger_on_next_check = False
        self._save_config()
        self._refresh_alerts_table()
        self._set_message(f"Alerta {alert.currency} {'activada' if alert.enabled else 'desactivada'}.")

    def _delete_alert(self) -> None:
        alert = self._selected_alert()
        if alert is None:
            self._set_message("Selecciona una alerta para eliminar.", "warning")
            return
        self.config_manager.delete_alert(self.config, alert.id)
        self._save_config()
        self._refresh_alerts_table()
        self._set_message(f"Alerta {alert.currency} eliminada.")

    # ------------------------------------------- consumo de resultados

    def _poll_results(self) -> None:
        """Vuelve a programarse a sí misma y drena la cola de resultados."""
        try:
            while True:
                item = self.controller.results.get_nowait()
                kind = item.get("kind")
                if kind == "rates":
                    self._apply_rates(item)
                elif kind == "error":
                    self._apply_error(item)
                elif kind == "notify":
                    self._set_message(item.get("message", ""), "info")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_results)

    def _apply_rates(self, item: dict[str, Any]) -> None:
        """Actualiza la tabla de precios con un resultado exitoso."""
        rates: dict[str, float] = item["rates"]
        base: str = item["base"]
        stamp = item["stamp"]
        now = datetime.now().strftime("%H:%M:%S")

        for code, rate in rates.items():
            prev = None
            if code in self.rates_state:
                prev = self.rates_state[code].get("rate")
            self.rates_state[code] = {"rate": rate, "prev": prev, "time": stamp}

        self._render_table(base, now)
        # Tras actualizar precios, evaluamos las alertas sobre los nuevos datos.
        self._check_alerts()

        self._set_status(f"Actualizado {now}", "success")
        self._set_message("", "")

    def _apply_error(self, item: dict[str, Any]) -> None:
        """Muestra un error de red/API en la interfaz sin cerrar la app."""
        now = datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Error {now}", "danger")
        self._set_message(item.get("message", "Error desconocido."), "danger")
        # Pintamos las filas con estado error si no hay datos previos.
        for code in SUPPORTED_CURRENCIES:
            if code not in self.rates_state:
                self.rates_state[code] = {"rate": None, "prev": None, "time": None}
        self._render_table(base=item.get("base", self.config.base_currency), now=now)

    def _render_table(self, base: str, now: str) -> None:
        """Rellena el Treeview con el estado actual de las monedas."""
        for child in self.tree.get_children():
            self.tree.delete(child)

        for code, name in SUPPORTED_CURRENCIES.items():
            if code == base:
                continue
            state = self.rates_state.get(code)
            rate = state["rate"] if state else None
            prev = state["prev"] if state else None
            stamp = state["time"] if state else None

            tag = "neutral"
            change_text = "—"
            pct_text = "—"
            status_text = "OK" if rate is not None else "Sin datos"

            if rate is not None and prev is not None:
                diff = rate - prev
                if abs(diff) < 1e-12:
                    change_text = "0"
                    pct_text = "0.00%"
                    tag = "neutral"
                elif diff > 0:
                    change_text = f"+{diff:.6g}"
                    pct_text = f"+{(diff / prev) * 100:.2f}%"
                    tag = "up"
                else:
                    change_text = f"{diff:.6g}"
                    pct_text = f"{(diff / prev) * 100:.2f}%"
                    tag = "down"

            price_display = f"{rate:.6g}" if rate is not None else "—"
            time_display = (stamp or "—").split("T")[-1][:8] if stamp else "—"

            self.tree.insert(
                "",
                "end",
                values=(
                    code,
                    code,
                    name,
                    price_display,
                    time_display,
                    change_text,
                    pct_text,
                    status_text,
                ),
                tags=(tag,),
            )

    # ------------------------------------------------------- alerts check

    def _check_alerts(self) -> None:
        """Evalúa todas las alertas habilitadas contra los últimos precios."""
        base = self.config.base_currency
        for alert in list(self.config.alerts):
            if not alert.enabled:
                continue
            if alert.currency == base:
                continue

            currency_state = self.rates_state.get(alert.currency)
            if currency_state is None:
                continue

            current = currency_state.get("rate")
            previous = currency_state.get("prev")
            if current is None:
                continue

            # Solo evaluamos la primera vez que hay un precio real (evita
            # disparos inmediatos con el primer dato recién cargado).
            if alert.trigger_on_next_check is False and previous is None:
                alert.trigger_on_next_check = True
                continue

            triggered, description = evaluate(alert, current, previous)
            if triggered:
                self._fire_alert(alert, current, base, description)
                if alert.notify_once:
                    alert.enabled = False
                    self._schedule_alerts_table_refresh()

        self._save_config()

    def _fire_alert(self, alert: Alert, current: float, base: str, description: str) -> None:
        """Dispara una notificación de escritorio cuando la alerta se cumple."""
        now = datetime.now().strftime("%H:%M:%S")
        currency_name = SUPPORTED_CURRENCIES.get(alert.currency, alert.currency)
        title = "Alerta de moneda"
        message = (
            f"La moneda {alert.currency} ({currency_name}) ha cumplido la condición.\n"
            f"Precio actual: {current:.6g}\n"
            f"Condición: {description}\n"
            f"Moneda base: {base}\n"
            f"Hora: {now}"
        )
        try:
            notify(title, message)
        except Exception:
            pass

    def _schedule_alerts_table_refresh(self) -> None:
        """Refresca la tabla de alertas en el siguiente ciclo de eventos (seguro para hilos)."""
        def _cb() -> None:
            self._refresh_alerts_table()
        self.root.after(0, _cb)

    # --------------------------------------------------- misc / persistencia

    def _in_app_notification(self, title: str, message: str) -> None:
        """Fallback: muestra la notificación dentro de la aplicación si no hay notify-send."""
        self.root.after(0, lambda: self._set_message(f"{title}: {message}", "info"))

    def _save_config(self) -> None:
        self.config_manager.save(self.config)

    def on_close(self) -> None:
        self._save_config()
        self.root.destroy()


def _alert_line(alert: Alert) -> str:
    """Devuelve una línea de texto legible para la lista de alertas."""
    label = CONDITIONS[alert.condition]["label"] if alert.condition in CONDITIONS else alert.condition
    return f"{alert.currency} {label} {alert.value:g}"
