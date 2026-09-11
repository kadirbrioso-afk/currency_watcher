#!/usr/bin/env bash
# =============================================================================
# build.sh — Empaqueta Currency Watcher con PyInstaller en modo --onedir.
#
# Uso:
#   ./build.sh [VERSION]
#
# Estrategia:
#   Rápida: usa un Python que YA tenga aiohttp, pyside6, plyer y PyInstaller
#   (p. ej. /usr/bin/python3 con pip --user), sin descargar nada. Reduce el
#   build a ~30 s.
#   Fallback: si no existe, crea un venv de build en /tmp y hace pip install
#   (lento, primero descarga PySide6).
#
# Final:
#   - Ejecuta PyInstaller con currency-watcher.spec (excluye módulos Qt
#     innecesarios y aplica strip para reducir tamaño).
#   - Purga plugins/librerías Qt que la app no usa (~80 MB menos).
#   - Deja el resultado en dist/currency-watcher/ y genera un tarball.
# =============================================================================
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="currency-watcher"
BUILD_VENV_DIR="${BUILD_VENV_DIR:-/tmp/opencode/currency-watcher-build-venv}"
VERSION="${1:-0.1.0}"

echo "[build] Empaquetando ${APP_NAME} v${VERSION} (PyInstaller --onedir)..."

# ---------------------------------------------------------------------------
# 1. Elegir un Python que ya tenga todas las dependencias.
# ---------------------------------------------------------------------------
PYTHON_BIN=""
for cand in /usr/bin/python3 /usr/local/bin/python3 "$BUILD_VENV_DIR/bin/python"; do
    if [[ -x "$cand" ]] && \
       "$cand" -c "import aiohttp, plyer, PySide6, PyInstaller" 2>/dev/null; then
        PYTHON_BIN="$cand"
        break
    fi
done

# Fallback: crear un venv de build e instalar las dependencias (lento).
if [[ -z "$PYTHON_BIN" ]]; then
    echo "[build] Sin Python con deps completas; creando venv e instalando (lento)..."
    BASE=""
    for c in /usr/bin/python3 /usr/local/bin/python3; do
        [[ -x "$c" ]] && BASE="$c" && break
    done
    [[ -z "$BASE" ]] && { echo "[build] ERROR: no hay python3." >&2; exit 1; }
    if [[ ! -x "$BUILD_VENV_DIR/bin/python" ]]; then
        "$BASE" -m venv "$BUILD_VENV_DIR"
    fi
    "$BUILD_VENV_DIR/bin/pip" install --quiet aiohttp pyside6 plyer pyinstaller
    PYTHON_BIN="$BUILD_VENV_DIR/bin/python"
fi

echo "[build] Python de build: $("$PYTHON_BIN" --version)"

# ---------------------------------------------------------------------------
# 2. Limpieza y build con PyInstaller (usa el spec con excludes + strip).
# ---------------------------------------------------------------------------
rm -rf build dist
echo "[build] Ejecutando PyInstaller (currency-watcher.spec)..."
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean currency-watcher.spec

DIST_DIR="dist/${APP_NAME}"
if [[ ! -x "$DIST_DIR/${APP_NAME}" ]]; then
    echo "[build] ERROR: no se generó el binario en $DIST_DIR" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Purga de plugins y librerías Qt que la app no usa (reduce ~80 MB).
#    Se eliminan plugins cuya carga arrastra libQt6Pdf, QtQuick/QtQml y KDE
#    (Breeze); el resto de Qt sigue funcionando con fallbacks estándar.
# ---------------------------------------------------------------------------
echo "[build] Purgando plugins/librerías Qt innecesarios..."
QT_LIB="$DIST_DIR/_internal/PySide6/Qt/lib"
rm -f \
    "$DIST_DIR/_internal/PySide6/Qt/plugins/imageformats/libqpdf.so" \
    "$DIST_DIR/_internal/PySide6/Qt/plugins/imageformats/kimg_"*.so \
    "$DIST_DIR/_internal/PySide6/Qt/plugins/platformthemes/KDEPlasmaPlatformTheme6.so" \
    "$DIST_DIR/_internal/PySide6/Qt/plugins/styles/breeze6.so"
for lib in libQt6Pdf libQt6Quick libQt6QuickControls2 libQt6QuickTemplates2 \
           libQt6QuickLayouts libQt6Qml libQt6QmlMeta libQt6QmlModels \
           libQt6QmlWorkerScript libKF6BreezeIcons libKF6IconThemes \
           libKF6Notifications libKF6ConfigCore libKF6WindowSystem libKF6I18n; do
    rm -f "$DIST_DIR/_internal/${lib}".so.* "$QT_LIB/${lib}".so.* 2>/dev/null || true
done

# ---------------------------------------------------------------------------
# 4. Comprobación rápida y empaquetado en tarball.
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