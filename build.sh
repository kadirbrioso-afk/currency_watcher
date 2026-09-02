#!/usr/bin/env bash
# =============================================================================
# build.sh — Empaqueta Currency Watcher con PyInstaller en modo --onedir.
#
# Uso:
#   ./build.sh
#
# Qué hace:
#   1. Detecta un intérprete de Python compatible con tkinter (importante:
#      el tkinter debe enlazar con el Tcl/Tk del sistema).
#   2. Crea (o reutiliza) un entorno virtual de build aislado.
#   3. Instala en él las dependencias de ejecución y PyInstaller.
#   4. Lanza PyInstaller con --onedir --windowed, recopilando los datos de
#      ttkbootstrap y PIL (assets/iconos) y el módulo oculto de PIL para tkinter.
#   5. Deja el resultado en dist/currency-watcher/ y genera un tarball.
#
# Reproducible para versiones futuras: solo hay que ejecutarlo de nuevo.
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="currency-watcher"
BUILD_VENV_DIR="${BUILD_VENV_DIR:-/tmp/opencode/currency-watcher-build-venv}"
VERSION="${1:-0.1.0}"

echo "[build] Empaquetando ${APP_NAME} v${VERSION} (PyInstaller --onedir)..."

# ---------------------------------------------------------------------------
# 1. Elegir un intérprete de Python compatible con tkinter.
# ---------------------------------------------------------------------------
# AVISO: algunos Pythons gestionados por herramientas de gestión de entornos
# (p. ej. el proporcionado por uv) pueden traer un tkinter que no enlaza
# correctamente con el Tcl/Tk del sistema. Para evitar el error
# "undefined symbol: TclBN_mp_to_ubin", usamos preferentemente el Python del
# sistema, verificando que importa tkinter sin errores.
PYTHON_BIN=""

# Intérpretes candidatos, por orden de preferencia.
for cand in /usr/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$cand" ]] && "$cand" -c "import tkinter" 2>/dev/null; then
        PYTHON_BIN="$cand"
        break
    fi
done

# Si ninguno del sistema sirve, caemos en el python del proyecto (con venv).
if [[ -z "$PYTHON_BIN" && -x "./.venv/bin/python" ]]; then
    if "./.venv/bin/python" -c "import tkinter" 2>/dev/null; then
        PYTHON_BIN="./.venv/bin/python"
    fi
fi

if [[ -z "$PYTHON_BIN" ]]; then
    echo "[build] ERROR: no se encontró un Python con tkinter funcional." >&2
    echo "[build] Instala tkinter de tu sistema, p. ej.:" >&2
    echo "[build]   dnf install python3-tkinter   (Fedora)" >&2
    echo "[build]   apt install python3-tk        (Debian/Ubuntu)" >&2
    exit 1
fi

echo "[build] Intérprete de build: $PYTHON_BIN"
"$PYTHON_BIN" --version

# ---------------------------------------------------------------------------
# 2. Entorno virtual de build.
# ---------------------------------------------------------------------------
if [[ ! -x "$BUILD_VENV_DIR/bin/python" ]]; then
    echo "[build] Creando entorno virtual de build en $BUILD_VENV_DIR"
    "$PYTHON_BIN" -m venv "$BUILD_VENV_DIR"
fi

BUILD_PY="$BUILD_VENV_DIR/bin/python"
# Reinstalamos si cambia el intérprete base.
"$BUILD_PY" -c "import sys; sys.exit(0) if sys.executable else None" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Dependencias.
# ---------------------------------------------------------------------------
echo "[build] Instalando dependencias de build (aiohttp, ttkbootstrap, plyer, pyinstaller)..."
"$BUILD_VENV_DIR/bin/pip" install --quiet --upgrade pip
"$BUILD_VENV_DIR/bin/pip" install --quiet aiohttp ttkbootstrap plyer pyinstaller

# ---------------------------------------------------------------------------
# 4. Limpieza y build con PyInstaller.
# ---------------------------------------------------------------------------
rm -rf build dist
echo "[build] Ejecutando PyInstaller --onedir --windowed..."
"$BUILD_VENV_DIR/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --onedir \
    --collect-data ttkbootstrap \
    --collect-all PIL \
    --hidden-import PIL._tkinter_finder \
    main.py

DIST_DIR="dist/${APP_NAME}"
if [[ ! -x "$DIST_DIR/${APP_NAME}" ]]; then
    echo "[build] ERROR: no se generó el binario en $DIST_DIR" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Comprobación rápida y empaquetado en tarball.
# ---------------------------------------------------------------------------
echo "[build] Build OK. Resultado en $DIST_DIR"
ls -la "$DIST_DIR"

TARBALL="dist/${APP_NAME}-${VERSION}-linux-x64.tar.gz"
tar -czf "$TARBALL" -C dist "$APP_NAME"
echo "[build] Tarball generado: $TARBALL"
echo
echo "Ejecuta la app con:"
echo "  $DIST_DIR/${APP_NAME}"
echo "o extrae el tarball y ejecuta '$APP_NAME'."