"""Fun settings (Cat Mode). User-level only; stored as JSON in config dir."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from enigmars_util.paths import config_dir

FILE_NAME = "fun.json"


@dataclass(frozen=True)
class FunSettings:
    cat_mode: bool = False
    meow_on_nav: bool = True
    meow_on_login: bool = True
    kde_sounds: bool = False  # Plasma login/logout meow via KDE event sounds
    volume: int = 80


def _coerce(raw: object) -> FunSettings:
    if not isinstance(raw, dict):
        return FunSettings()
    vol = raw.get("volume", 80)
    try:
        vol = int(vol)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        vol = 80
    return FunSettings(
        cat_mode=bool(raw.get("cat_mode", False)),
        meow_on_nav=bool(raw.get("meow_on_nav", True)),
        meow_on_login=bool(raw.get("meow_on_login", True)),
        kde_sounds=bool(raw.get("kde_sounds", False)),
        volume=max(0, min(100, vol)),
    )


def load_settings() -> FunSettings:
    path = config_dir() / FILE_NAME
    if not path.is_file():
        return FunSettings()
    try:
        return _coerce(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return FunSettings()


def save_settings(settings: FunSettings) -> None:
    path = config_dir() / FILE_NAME
    path.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")


def should_meow_on_nav(settings: FunSettings) -> bool:
    return settings.cat_mode and settings.meow_on_nav


def should_meow_on_login(settings: FunSettings) -> bool:
    return settings.cat_mode and settings.meow_on_login
