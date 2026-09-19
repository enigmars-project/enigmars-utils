#!/bin/sh
# Install Enigmars Utils (GUI + pkexec helper + catalogs + polkit policy).
# Does not use pip — copies the package under $PREFIX/lib/enigmars-utils.
#
# Usage:
#   sudo ./scripts/install.sh
#   DESTDIR=/tmp/pkg PREFIX=/usr ./scripts/install.sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"

if [ "$(id -u)" -ne 0 ] && [ -z "$DESTDIR" ]; then
  echo "install.sh: run as root, or set DESTDIR for packaging." >&2
  exit 1
fi

lib="${DESTDIR}${PREFIX}/lib/enigmars-utils"
install -d "$lib"
cp -a "$ROOT/src/enigmars_util" "$ROOT/src/enigmars_util_helper" "$lib/"
find "$lib" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$lib" -type f -name '*.pyc' -delete

install -d "${DESTDIR}${PREFIX}/bin"
cat > "${DESTDIR}${PREFIX}/bin/enigmars-util" <<EOF
#!/usr/bin/python3
import sys
sys.path.insert(0, "${PREFIX}/lib/enigmars-utils")
from enigmars_util.app import main
raise SystemExit(main())
EOF
chmod 755 "${DESTDIR}${PREFIX}/bin/enigmars-util"

install -Dm755 "$ROOT/packaging/libexec/enigmars-util-helper" \
  "${DESTDIR}${PREFIX}/libexec/enigmars-util-helper"

share="${DESTDIR}${PREFIX}/share/enigmars-util"
install -d "$share"
cp -a "$ROOT/data/tweaks" "$ROOT/data/catalog" "$ROOT/data/kernels" "$ROOT/data/branding" "$ROOT/data/icons" "$ROOT/data/sounds" "$share/"

install -Dm644 "$ROOT/data/desktop/org.enigmars.Util.desktop" \
  "${DESTDIR}${PREFIX}/share/applications/org.enigmars.Util.desktop"
install -Dm644 "$ROOT/data/desktop/org.enigmars.Fun-Meow.desktop" \
  "${DESTDIR}${PREFIX}/share/applications/org.enigmars.Fun-Meow.desktop"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.svg" \
  "${DESTDIR}${PREFIX}/share/icons/hicolor/scalable/apps/enigmarsos.svg"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.svg" \
  "${DESTDIR}${PREFIX}/share/icons/hicolor/scalable/apps/org.enigmars.Util.svg"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.png" \
  "${DESTDIR}${PREFIX}/share/icons/hicolor/256x256/apps/enigmarsos.png"
install -Dm644 "$ROOT/data/icons/EnigmarsOS.png" \
  "${DESTDIR}${PREFIX}/share/pixmaps/enigmarsos.png"
install -Dm644 "$ROOT/data/polkit/org.enigmars.util.policy" \
  "${DESTDIR}${PREFIX}/share/polkit-1/actions/org.enigmars.util.policy"

revfile="${share}/revision"
if command -v git >/dev/null 2>&1 \
  && git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT" rev-parse HEAD > "$revfile"
fi

echo "Installed to ${DESTDIR}${PREFIX}"
