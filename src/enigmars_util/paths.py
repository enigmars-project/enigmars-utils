from __future__ import annotations

import os
from pathlib import Path

APP_ID = "enigmars-util"
HELPER_PATH = Path("/usr/libexec/enigmars-util-helper")
SHARE_PATH = Path("/usr/share/enigmars-util")
ESP_SYNC = Path("/usr/share/enigmarsos/scripts/sync-esp-boot.sh")


def xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def xdg_state_home() -> Path:
    raw = os.environ.get("XDG_STATE_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".local/state"


def config_dir() -> Path:
    p = xdg_config_home() / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def state_dir() -> Path:
    p = xdg_state_home() / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def autostart_path() -> Path:
    return xdg_config_home() / "autostart" / "org.enigmars.Util.desktop"


def icon_path() -> Path:
    """Canonical EnigmarsOS mark (PNG preferred, then SVG)."""
    bundled = data_root() / "icons"
    candidates = (
        Path("/usr/share/enigmarsos/logos/EnigmarsOS.png"),
        Path("/usr/share/enigmarsos/logos/EnigmarsOS.svg"),
        Path("/usr/share/pixmaps/enigmarsos.png"),
        bundled / "EnigmarsOS.png",
        bundled / "EnigmarsOS.svg",
        Path("/usr/share/icons/hicolor/scalable/apps/enigmarsos.svg"),
        Path("/usr/share/icons/hicolor/scalable/apps/org.enigmars.Util.svg"),
        bundled / "org.enigmars.Util.svg",
    )
    for path in candidates:
        if path.is_file():
            return path
    return bundled / "EnigmarsOS.png"


def data_root() -> Path:
    env = os.environ.get("ENIGMARS_UTIL_DATA")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "data"
        if (cand / "branding").is_dir() or (cand / "tweaks").is_dir():
            return cand
    if SHARE_PATH.is_dir():
        return SHARE_PATH
    return Path(__file__).resolve().parents[2] / "data"


def sound_path(name: str = "meow.mp3") -> Path:
    """Resolve a bundled sound file (allow-listed base dirs only)."""
    safe = Path(name).name
    if not safe or safe not in ("meow.mp3",):
        return data_root() / "sounds" / "meow.mp3"
    candidates = (
        data_root() / "sounds" / safe,
        SHARE_PATH / "sounds" / safe,
        Path(__file__).resolve().parents[2] / "media" / safe,
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]
