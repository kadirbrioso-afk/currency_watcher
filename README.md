# Currency Watcher

Aplicación gráfica de escritorio para **Linux** que muestra en tiempo casi real
el precio de varias monedas (fiat y criptomonedas) respecto a una moneda base
elegida por el usuario, y que permite programar **alertas/notificaciones**
cuando una moneda sube, baja, alcanza un valor concreto o varía un porcentaje
determinado. Incluye **historial (SQLite)**, **gráfico de evolución**, temas
claro/oscuro y **exportación** a CSV/JSON.

Construida con **Python 3.10+** (desarrollada y probada en **3.14.7**),
**PySide6**, **asyncio** y **aiohttp**.

## Monedas soportadas

| Código | Nombre |
|--------|--------|
| USD | Dólar estadounidense |
| EUR | Euro |
| GBP | Libra esterlina |
| JPY | Yen japonés |
| CNY | Yuan chino |
| PEN | Sol peruano |
| RUB | Rublo ruso |
| BTC | Bitcoin |
| ETH | Ethereum |
| SOL | Solana |
| TRX | Tron |
| USDT | Tether |
| XRP | Ripple |
| DOGE | Dogecoin |
| SUI | Sui |
| LINK | Chainlink |

> La **moneda base** solo puede ser fiat (USD, EUR, GBP, JPY, CNY, PEN, RUB);
> las criptomonedas se convierten vía su precio en USD. Los precios fiat
> proceden de las APIs públicas y las criptos de CoinGecko.

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
├── main.py          # Punto de entrada: crea QApplication, ventana e historial.
├── ui.py            # Interfaz gráfica PySide6 (tabla, gráfico, alertas, temas).
├── rates.py         # Obtención asíncrona de tasas con aiohttp (fiat + CoinGecko).
├── alerts.py        # Evaluación de las condiciones de las alertas.
├── notifier.py      # Notificaciones de escritorio (notify-send / plyer / fallback).
├── sounds.py        # Reproducción de sonido de alerta (canberra / paplay / aplay / ffplay).
├── history.py       # Historial SQLite (WAL) con retención de 90 días.
├── config.py        # Configuración persistente, monedas soportadas y temas (JSON).
├── build.sh         # Automatiza el empaquetado con PyInstaller (--onedir).
├── currency-watcher.spec  # Spec de PyInstaller (excluye módulos Qt no usados).
├── tests/           # Tests (pytest): alerts, config, history y smoke de la GUI.
├── pyproject.toml   # Metadatos y dependencias (gestión con uv).
├── uv.lock          # Resolución de dependencias bloqueada.
└── README.md
```

## Empaquetado (build con PyInstaller)

El proyecto incluye `build.sh`, que empaqueta la aplicación en un directorio
distribuible con PyInstaller en modo `--onedir` (carpeta con el binario y sus
dependencias) y genera además un tarball:

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

> **Nota técnica**: `build.sh` usa un Python del **sistema** que ya tenga
> instaladas las dependencias (`aiohttp`, `pyside6`, `plyer`) y PyInstaller;
> así el build tarda ~1 minuto y no descarga PySide6. El empaquetado usa el
> spec `currency-watcher.spec`, que **excluye los módulos Qt que la app no usa**
> (WebEngine, QML/Quick, Multimedia, 3D, PDF…) y aplica `strip`. Tras el build
> se purgan además los plugins Qt que arrastran librerías anchas (QtPdf,
> QtQuick/Qml y KDE Breeze); el resultado pesa ~230 MB en directorio y ~95 MB
> comprimido.

Para ejecutar la app empaquetada:

```bash
dist/currency-watcher/currency-watcher
```

## Tests

```bash
uv run pytest -q
```

Los tests de la GUI (`tests/test_ui.py`) se ejecutan en modo *offscreen* con
PySide6; si el entorno no tiene PySide6 instalado se omiten automáticamente
(`pytest.importorskip`).

## Funcionalidades

- **Panel principal de precios**: tabla con código, nombre, precio actual
  respecto a la base, símbolo, última actualización, cambio absoluto, variación
  porcentual y estado. Filas con **color de fondo alternado**. Color **verde**
  si sube, **rojo** si baja, **amarillo** sin cambios y **gris** si hay
  error/sin datos. Filtro **"Solo favoritas"** para quedarse con las marcadas.
- **Moneda base seleccionable** (solo fiat) desde un desplegable. Al cambiar la
  base se actualizan la tabla, el historial y las monedas del gráfico.
- **Historial en SQLite** (`history.db`, con WAL): cada ciclo de actualización
  guarda una muestra de todas las monedas; se conservan **90 días** y se
  limpian los registros antiguos automáticamente.
- **Gráfico de evolución** dibujado con QPainter: selector de **moneda** y de
  **rango** (6h, 24h, 3 días, 7 días), **eje temporal** con la marca de inicio
  y fin de la ventana, y *tooltip* al pasar el ratón por encima.
- **Exportación** a **CSV** o **JSON** del historial en formato ancho
  (columna por moneda), con el nombre de archivo `rates_<fecha>.csv/json`.
- **Temas claro/oscuro** configurables (p. ej. `cyborg`, `solar`, `light`)
  aplicados vía QSS; se guardan en `config.json`.
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
  - **Informe periódico**: notifica el precio cada X horas sin necesidad de
    condición.
  - Con opción de notificar una sola vez, activar/desactivar y eliminar.
- **Notificaciones de escritorio de Linux** con un mensaje detallado.
- **Sonido de alerta**: al dispararse una notificación se reproduce un sonido
  del tema del sistema (o el primero disponible del reproductor encontrado).
- **Persistencia** en `config.json`: moneda base, intervalo, modo auto, tema,
  favoritas y reglas de alerta.

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
- Las alertas de **informe periódico** (`periodic`) no comparan ningún valor:
  muestran el precio actual de su moneda cada `period_hours` horas, anotando la
  fecha de la última emisión para no repetirse en cada ciclo.

## Configuración (config.json)

Ejemplo de contenido:

```json
{
  "base_currency": "USD",
  "refresh_interval": 60,
  "auto_refresh": true,
  "theme": "cyborg",
  "favorites": ["EUR", "PEN"],
  "alerts": [
    {
      "currency": "EUR",
      "condition": "greater_than",
      "value": 1.09,
      "enabled": true,
      "notify_once": false,
      "id": "uuid",
      "created_at": "2026-09-02T12:00:00"
    },
    {
      "currency": "PEN",
      "condition": "periodic",
      "value": 0.0,
      "enabled": true,
      "notify_once": false,
      "period_hours": 1,
      "last_fired_at": "2026-09-11T03:09:34",
      "id": "uuid2",
      "created_at": "2026-09-11T03:09:34"
    }
  ]
}
```

Si el archivo está corrupto, el programa carga la configuración por defecto en
lugar de cerrarse.

## APIs de tipos de cambio

Se usan APIs públicas gratuitas sin registro, con redundancia automática:

- `https://open.er-api.com/v6/latest/{BASE}` (fiat)
- `https://api.frankfurter.app/latest?from={BASE}` (fiat)
- **CoinGecko** (criptomonedas): se consultan en paralelo los precios en USD
  de BTC, ETH, SOL, TRX, USDT, XRP, DOGE, SUI y LINK.

Si una API falla o da una respuesta inválida, el programa prueba la siguiente.
Para las criptos mantiene además una **caché en memoria** del último precio
conocido: si CoinGecko falla (p. ej. por límite de peticiones) se reutiliza la
última cotización en vez de perder las criptos. Si todas las fuentes fallan,
muestra un mensaje de error en la interfaz y reanuda la actualización
automática en el siguiente ciclo (sin cerrarse).

## Manejo de errores

- Falta de conexión / timeout: se muestra el error en la barra de estado.
- Respuesta HTTP o JSON inválida: se descarta y se intenta otro proveedor.
- Moneda no disponible: no se añade a la tabla.
- Configuración corrupta: se restaura por defecto.
- Notificaciones fallidas: se delega al fallback interno (o se ignora).
- Historial SQLite: usa WAL y `busy_timeout` para tolerar accesos simultáneos
  de la UI y el hilo de trabajo; los registros se podan pasados >90 días.

## Posibles mejoras futuras

- Soporte de más monedas y de cifras de la API configurable.
- Histórico de notificaciones disparadas en la propia app.
- Sonido configurable por el usuario (activar/desactivar, elegir sonido).
- Exportación a hoja de cálculo (xlsx) además de CSV/JSON.
- Notificaciones mediante `dbus-next` para un control más fino.
- Empaquetado en `.desktop` / AppImage para integrarse en el escritorio.
