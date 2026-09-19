"""KDE login/logout meow via native event sounds. User-level only (no root).

Plasma fires ``startkde`` (Login) and ``exitkde`` (Logout) notification
events (see /usr/share/knotifications6/plasma_workspace.notifyrc). This
module points just those two events at bundled meow sounds via a user
``plasma_workspace.notifyrc`` override — the rest of the sound theme is
untouched. No listeners, no overlays, no polling.
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
from pathlib import Path

THEME_DIR_NAME = "enigmars-fun"
NOTIFY_FILE = "plasma_workspace.notifyrc"

# event -> bundled source file in data/sounds/
EVENTS = {
    "startkde": "meow-login.oga",
    "exitkde": "meow-logout.oga",
}


def sounds_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "sounds" / THEME_DIR_NAME


def notify_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / NOTIFY_FILE


def _bundled(name: str) -> Path:
    from enigmars_util.paths import data_root

    safe = Path(name).name
    return data_root() / "sounds" / safe


def _read_notify() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # keep key case (KDE keys are case-sensitive)
    path = notify_path()
    if path.is_file():
        try:
            cfg.read(path, encoding="utf-8")
        except (OSError, configparser.Error):
            pass
    return cfg


def _write_notify(cfg: configparser.ConfigParser) -> None:
    path = notify_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        cfg.write(fh)


def event_sound(event: str) -> Path | None:
    """Configured sound file for an event, if any."""
    cfg = _read_notify()
    section = f"Event/{event}"
    if cfg.has_option(section, "Sound"):
        return Path(cfg.get(section, "Sound"))
    return None


def enabled() -> bool:
    """True when both login/logout events point at our installed sounds."""
    for event, source in EVENTS.items():
        target = sounds_dir() / source
        if not target.is_file():
            return False
        if event_sound(event) != target:
            return False
    return True


def install() -> bool:
    """Install sounds + point KDE login/logout events at them."""
    dest = sounds_dir()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for source in EVENTS.values():
            src = _bundled(source)
            if not src.is_file():
                return False
            shutil.copyfile(src, dest / source)
        cfg = _read_notify()
        for event, source in EVENTS.items():
            section = f"Event/{event}"
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, "Sound", str(dest / source))
        _write_notify(cfg)
    except OSError:
        return False
    return enabled()


def uninstall() -> bool:
    """Remove our event overrides (only ones pointing at our sounds)."""
    try:
        cfg = _read_notify()
        changed = False
        for event in EVENTS:
            section = f"Event/{event}"
            if not cfg.has_option(section, "Sound"):
                continue
            if Path(cfg.get(section, "Sound")).parent == sounds_dir():
                cfg.remove_option(section, "Sound")
                changed = True
        if changed:
            _write_notify(cfg)
        shutil.rmtree(sounds_dir(), ignore_errors=True)
    except OSError:
        return False
    return not enabled()


def preview(event: str) -> bool:
    """Play the installed event sound once (for the Preview button)."""
    source = EVENTS.get(event)
    if not source:
        return False
    target = sounds_dir() / source
    if not target.is_file():
        target = _bundled(source)
    if not target.is_file():
        return False
    if shutil.which("paplay"):
        cmd = ["paplay", str(target)]
    elif shutil.which("mpv"):
        cmd = ["mpv", "--no-video", "--vo=null", "--really-quiet", "--no-terminal", str(target)]
    elif shutil.which("ffplay"):
        cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(target)]
    else:
        return False
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True
