"""Autostart entry for the Fun login sound. User-level only (no root, no shell)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

LOGIN_NAME = "org.enigmars.Fun-Meow.desktop"

_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Enigmars Fun Meow
Comment=Cat Mode login sound
Exec={exec_line}
Icon=enigmarsos
Terminal=false
NoDisplay=true
X-KDE-autostart-phase=1
X-GNOME-Autostart-enabled=true
"""


def _autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart"


def _exec_args() -> list[str]:
    """Argv for the login meow. Installed binary preferred, else checkout."""
    if shutil.which("enigmars-util"):
        return ["enigmars-util", "--meow-login"]
    from enigmars_util.paths import data_root

    root = data_root()
    repo = root.parent if root.name == "data" else root
    src = repo / "src"
    if (src / "enigmars_util").is_dir():
        return ["env", f"PYTHONPATH={src}", sys.executable, "-m", "enigmars_util", "--meow-login"]
    return [sys.executable, "-m", "enigmars_util", "--meow-login"]


def login_enabled() -> bool:
    return (_autostart_dir() / LOGIN_NAME).is_file()


def set_login_enabled(on: bool) -> None:
    path = _autostart_dir() / LOGIN_NAME
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TEMPLATE.format(exec_line=" ".join(_exec_args())), encoding="utf-8")
    elif path.exists():
        path.unlink()
