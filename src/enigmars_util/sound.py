"""Best-effort meow playback. Qt first, external player fallback. No shell."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from enigmars_util.paths import sound_path

_player: object = None
_audio: object = None


def _clamp_volume(volume: int) -> float:
    return max(0, min(100, int(volume))) / 100.0


def external_command(sound: Path) -> list[str] | None:
    """First available external player command for sound, or None."""
    if not sound.is_file():
        return None
    exe = str(sound)
    # mp3 needs a decoder: prefer mpv/ffplay over paplay/aplay.
    # --vo=null: never create a window (must not steal focus / retrigger hooks).
    if shutil.which("mpv"):
        return ["mpv", "--no-video", "--vo=null", "--really-quiet", "--no-terminal", exe]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", exe]
    if shutil.which("paplay"):
        return ["paplay", exe]
    if shutil.which("aplay"):
        return ["aplay", "-q", exe]
    return None


def _play_qt(sound: Path, volume: int) -> bool:
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return False
    if QApplication.instance() is None:
        # No Qt event loop (tests, --meow-login): skip Qt, use external player.
        return False
    global _player, _audio
    try:
        if _player is None:
            _player = QMediaPlayer()
            _audio = QAudioOutput()
            _player.setAudioOutput(_audio)  # type: ignore[attr-defined]
        _audio.setVolume(_clamp_volume(volume))  # type: ignore[attr-defined]
        _player.setSource(QUrl.fromLocalFile(str(sound)))  # type: ignore[attr-defined]
        _player.play()  # type: ignore[attr-defined]
        return True
    except Exception:  # noqa: BLE001
        return False


def _play_external(cmd: list[str]) -> bool:
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        return True
    except OSError:
        return False


def play_meow(volume: int = 80, name: str = "meow.mp3") -> bool:
    """Non-blocking meow. Returns True if playback was started."""
    sound = sound_path(name)
    if not sound.is_file():
        cmd = external_command(sound)
        return _play_external(cmd) if cmd else False
    if _play_qt(sound, volume):
        return True
    cmd = external_command(sound)
    return _play_external(cmd) if cmd else False


def play_meow_blocking(volume: int = 80, timeout: int = 10) -> bool:
    """Blocking variant for --meow-login / daemon (no Qt event loop needed)."""
    del volume
    sound = sound_path()
    cmd = external_command(sound)
    if cmd is None:
        return False
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=timeout)  # noqa: S603
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
