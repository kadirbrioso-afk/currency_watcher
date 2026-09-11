# Currency Watcher

Aplicación gráfica de escritorio para **Linux** que muestra en tiempo casi real
el precio de varias monedas respecto a una moneda base elegida por el usuario,
y que permite programar **alertas/notificaciones** cuando una moneda sube, baja,
alcanza un valor concreto o varía un porcentaje determinado.

Construida con **Python 3.10+** (desarrollada y probada en **3.14.7**),
**pyside6**, **asyncio** y **aiohttp**.

## Monedas soportadas

| Código | Nombre |
|--------|--------|
| EUR | Euro |
| GBP | Libra esterlina |
| USD | Dólar estadounidense |
| JPY | Yen japonés |
| CNY | Yuan chino |
| PEN | Sol peruano |
| RUB | Rublo ruso |

## Instalación

El proyecto está gestionado con **`uv`**. Instálalo (si no lo tienes) y
ejecuta `uv sync` para crear el entorno e instalar las dependencias:

```bash
cd currency_watcher
uv sync
```

Esto crea un `.venv` con la versión de Python indicada en `.python-version`
(actualmente **3.14.7**) e instala las dependencias declaradas en
`pyproject.toml`, generando `uv.lock`.

### Dependencias del sistema para notificaciones

El programa usa `notify-send` (el estándar en GNOME, KDE Plasma y XFCE). Suele
venir instalado, pero si no, instálalo:

- **Debian/Ubuntu**: `sudo apt install libnotify-bin`
- **Arch**: `sudo pacman -S libnotify`
- **Fedora**: `sudo dnf install libnotify`

Si `notify-send` no está disponible, el programa intenta usar `plyer` y, si
tampoco funciona, muestra el aviso dentro de la propia interfaz (nunca se
cierra por un fallo de notificaciones).

### Dependencias del sistema para el sonido

Para reproducir un sonido al dispararse una alerta, el programa usa, por orden
de preferencia: `canberra-gtk-play`, `paplay`, `aplay` o `ffplay`. La mayoría
de escritorios ya traen alguno. Si quieres asegurarlo:

- **Debian/Ubuntu**: `sudo apt install libcanberra-gtk-module pulseaudio-utils`
- **Arch**: `sudo pacman -S libcanberra pulseaudio-utils`
- **Fedora**: `sudo dnf install libcanberra-gtk3 pulseaudio-utils`

Si no hay ningún reproductor, la alerta se muestra igualmente (sin sonido) sin
romper la aplicación.

## Ejecución

Con uv (recomendado):

```bash
cd currency_watcher
uv run main.py
```

También puedes usar el comando instalado:

```bash
uv run currency-watcher
```

O, de forma clásica:

```bash
source .venv/bin/activate
python main.py
```

## Estructura del proyecto

```
currency_watcher/
├── main.py          # Punto de entrada: integra la UI con el hilo asyncio.
├── ui.py            # Interfaz gráfica ttkbootstrap + consumo de la cola.
├── rates.py         # Obtención asíncrona de tasas con aiohttp (varias APIs).
├── alerts.py        # Evaluación de las condiciones de las alertas.
├── notifier.py      # Notificaciones de escritorio (notify-send / plyer / fallback).
├── sounds.py        # Reproducción de sonido de alerta (canberra / paplay / aplay / ffplay).
├── config.py        # Configuración persistente y reglas de alerta (JSON).
├── build.sh         # Automatiza el empaquetado con PyInstaller (--onedir).
├── pyproject.toml   # Metadatos y dependencias (gestión con uv).
├── uv.lock          # Resolución de dependencias bloqueada.
└── README.md
```

## Empaquetado (build con PyInstaller)

El proyecto incluye `build.sh`, que empaqueta la aplicación en un directorio
distribuible con PyInstaller en modo `--onedir` (carpeta con el binario y sus
dependencias) y genera además un tarball. Solo hay que ejecutarlo:

```bash
./build.sh
```

Opcionalmente se puede pasar la versión para el nombre del tarball:

```bash
./build.sh 1.0.0
```

Resultados:
- `dist/currency-watcher/` → la app empaquetada (`currency-watcher` es el ejecutable).
- `dist/currency-watcher-<version>-linux-x64.tar.gz` → tarball distribuir.

> **Nota técnica**: el script usa preferentemente el **Python del sistema**,
> no el gestionado por uv, porque algunos Pythons gestionados traen un tkinter
> que no enlaza correctamente con el Tcl/Tk del sistema (evitando el error
> `undefined symbol: TclBN_mp_to_ubin`). Verifica también que `tkinter` funcione
> y recopila los assets de `ttkbootstrap` y `PIL`.

Si el sistema no tiene `python3-tkinter`, instálalo:
- **Fedora**: `sudo dnf install python3-tkinter`
- **Debian/Ubuntu**: `sudo apt install python3-tk`

Para ejecutar la app empaquetada:

```bash
dist/currency-watcher/currency-watcher
```

## Funcionalidades

- **Panel principal de precios**: tabla con código, nombre, precio actual
  respecto a la base, última actualización, cambio absoluto, variación
  porcentual y estado. Color **verde** si sube, **rojo** si baja, **amarillo**
  sin cambios y **gris** si hay error/sin datos.
- **Moneda base seleccionable** desde un desplegable.
- **Actualización automática asíncrona** con intervalo configurable
  (30 s, 1 min, 5 min), botón de actualización manual, y para iniciar/parar
  la actualización automática. Barra de estado: actualizando / actualizado /
  error.
- **Alertas configurables**: por moneda y condición:
  - Precio mayor que (`>`)
  - Precio menor que (`<`)
  - Precio mayor o igual (`>=`)
  - Precio menor o igual (`<=`)
  - Subida porcentual mayor que (respecto a la actualización anterior)
  - Bajada porcentual mayor que (respecto a la actualización anterior)
  - Con opción de notificar una sola vez, activar/desactivar y eliminar.
- **Notificaciones de escritorio de Linux** con un mensaje detallado.
- **Sonido de alerta**: al dispararse una notificación se reproduce un sonido
  del tema del sistema (o el primero disponible del reproductor encontrado).
- **Persistencia** en `config.json`: moneda base, intervalo, modo auto y reglas.

## Cómo funcionan las alertas

En cada actualización de precios, la aplicación evalúa todas las alertas
**habilitadas**. Cada alerta compara el precio actual de su moneda con el valor
objetivo (o con la actualización anterior para las condiciones porcentuales).
Si la condición se cumple, se muestra una notificación de escritorio, por
ejemplo:

```
Alerta de moneda
La moneda EUR (Euro) ha cumplido la condición.
Precio actual: 1.0952
Condición: EUR (Euro): Precio mayor que (>) 1.09
Moneda base: USD
Hora: 14:32:10
```

- Si la alerta tiene **"notificar una sola vez"**, se desactiva automáticamente
  tras dispararse.
- Se evita disparar con el primer dato recién cargado en condiciones
  porcentuales (necesita al menos dos valores para calcular la variación).

## Configuración (config.json)

Ejemplo de contenido:

```json
{
  "base_currency": "USD",
  "refresh_interval": 60,
  "auto_refresh": true,
  "alerts": [
    {
      "currency": "EUR",
      "condition": "greater_than",
      "value": 1.09,
      "enabled": true,
      "notify_once": false,
      "id": "uuid",
      "created_at": "2026-09-02T12:00:00"
    }
  ]
}
```

Si el archivo está corrupto, el programa carga la configuración por defecto en
lugar de cerrarse.

## APIs de tipos de cambio

Se usan APIs públicas gratuitas sin registro, con redundancia automática:

- `https://open.er-api.com/v6/latest/{BASE}`
- `https://api.frankfurter.app/latest?from={BASE}`

Si una API falla o da una respuesta inválida, el programa prueba la siguiente.
Si todas fallan, muestra un mensaje de error en la interfaz y reanuda la
actualización automática en el siguiente ciclo (sin cerrarse).

## Manejo de errores

- Falta de conexión / timeout: se muestra el error en la barra de estado.
- Respuesta HTTP o JSON inválida: se descarta y se intenta otro proveedor.
- Moneda no disponible: no se añade a la tabla.
- Configuración corrupta: se restaura por defecto.
- Notificaciones fallidas: se delega al fallback interno (o se ignora).

## Posibles mejoras futuras

- Soporte de más monedas y de cifras de la API configurable.
- Histórico de notificaciones disparadas en la propia app.
- Sonido configurable por el usuario (activar/desactivar, elegir sonido).
- Notificaciones mediante `dbus-next` para un control más fino.
- Empaquetado en `.desktop` / AppImage para integrarse en el escritorio.
