#!/bin/sh
# Build a portable x86_64 AppImage (Python + PySide6 + app data).
# Output: dist/Enigmars_Utils-<version>-x86_64.AppImage
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('${ROOT}/pyproject.toml','rb'))['project']['version'])")"
STAGE="${TMPDIR:-/tmp}/enigmars-utils-appimage-$$"
APPDIR="$STAGE/Enigmars_Utils.AppDir"
OUT="${ROOT}/dist"
ARCH="${ARCH:-x86_64}"
NAME="Enigmars_Utils-${VERSION}-${ARCH}.AppImage"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

umask 022
mkdir -p "$OUT" "$APPDIR/usr"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="${HOME}/.local/bin:${PATH}"
  export PATH
fi

# Relocatable CPython (manylinux-compatible), then PySide6 into that prefix.
UV_PYTHON_INSTALL_DIR="$STAGE/cpython"
export UV_PYTHON_INSTALL_DIR
uv python install 3.12
PY="$(uv python find 3.12)"
PREFIX="$(CDPATH= cd -- "$(dirname "$PY")/.." && pwd)"
cp -a "$PREFIX"/. "$APPDIR/usr/"

APP_PY="$APPDIR/usr/bin/python3"
if [ ! -x "$APP_PY" ]; then
  APP_PY="$(find "$APPDIR/usr" -type f -name python3 | head -n1)"
fi
# Copied uv CPython is marked externally managed. Install into prefix site-packages.
PYVER="$("$APP_PY" -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))')"
SITE="$APPDIR/usr/lib/python${PYVER}/site-packages"
mkdir -p "$SITE"
# Widgets-only stack; skip Qt 3D / NFC / etc. addons (~160MB).
UV_LINK_MODE=copy uv pip install --python "$APP_PY" --target "$SITE" PySide6-Essentials

mkdir -p "$APPDIR/usr/lib/enigmars-utils"
cp -a "$ROOT/src/enigmars_util" "$ROOT/src/enigmars_util_helper" \
  "$APPDIR/usr/lib/enigmars-utils/"
find "$APPDIR/usr/lib/enigmars-utils" -type d -name '__pycache__' -prune -exec rm -rf {} +

share="$APPDIR/usr/share/enigmars-util"
install -d "$share"
cp -a "$ROOT/data/tweaks" "$ROOT/data/catalog" "$ROOT/data/kernels" \
  "$ROOT/data/branding" "$ROOT/data/icons" "$ROOT/data/sounds" "$share/"

install -Dm755 "$ROOT/packaging/appimage/enigmars-util.wrapper" "$APPDIR/AppRun"
install -Dm755 "$ROOT/packaging/appimage/enigmars-util.wrapper" \
  "$APPDIR/usr/bin/enigmars-util"
install -Dm755 "$ROOT/packaging/libexec/enigmars-util-helper" \
  "$APPDIR/usr/libexec/enigmars-util-helper"
install -Dm644 "$ROOT/data/polkit/org.enigmars.util.policy" \
  "$APPDIR/usr/share/polkit-1/actions/org.enigmars.util.policy"

install -Dm644 "$ROOT/data/desktop/org.enigmars.Util.desktop" \
  "$APPDIR/enigmars-utils.desktop"
# appimagetool wants Exec=binary-in-usr-bin and Icon=basename in AppDir root
sed -i 's|^Exec=.*|Exec=enigmars-util|' "$APPDIR/enigmars-utils.desktop"
sed -i 's|^Icon=.*|Icon=enigmarsos|' "$APPDIR/enigmars-utils.desktop"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.png" "$APPDIR/enigmarsos.png"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.png" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps/enigmarsos.png"

TOOL="$STAGE/appimagetool"
curl -fsSL -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
chmod +x "$TOOL"

mkdir -p "$OUT"
# GHA / containers often have no FUSE.
export APPIMAGE_EXTRACT_AND_RUN=1
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT/$NAME"
chmod +x "$OUT/$NAME"
echo "Built $OUT/$NAME"
ls -lh "$OUT/$NAME"
