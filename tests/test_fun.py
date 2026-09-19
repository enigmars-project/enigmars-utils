from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from enigmars_util import fun as fun_mod
from enigmars_util.fun import FunSettings, load_settings, save_settings


class FunSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old
        self._tmp.cleanup()

    def test_defaults_when_missing(self) -> None:
        settings = load_settings()
        self.assertFalse(settings.cat_mode)
        self.assertEqual(settings.volume, 80)

    def test_round_trip(self) -> None:
        save_settings(FunSettings(cat_mode=True, volume=42, kde_sounds=True))
        loaded = load_settings()
        self.assertTrue(loaded.cat_mode)
        self.assertEqual(loaded.volume, 42)
        self.assertTrue(loaded.kde_sounds)

    def test_volume_clamped(self) -> None:
        save_settings(FunSettings(volume=999))
        self.assertEqual(load_settings().volume, 100)
        save_settings(FunSettings(volume=-5))
        self.assertEqual(load_settings().volume, 0)

    def test_corrupt_file_returns_defaults(self) -> None:
        path = Path(self._tmp.name) / "enigmars-util" / "fun.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(load_settings(), FunSettings())

    def test_helpers(self) -> None:
        self.assertTrue(fun_mod.should_meow_on_nav(FunSettings(cat_mode=True)))
        self.assertFalse(
            fun_mod.should_meow_on_nav(FunSettings(cat_mode=True, meow_on_nav=False))
        )
        self.assertTrue(fun_mod.should_meow_on_login(FunSettings(cat_mode=True)))
        self.assertFalse(fun_mod.should_meow_on_login(FunSettings()))

    def test_json_is_sorted_keys(self) -> None:
        save_settings(FunSettings(cat_mode=True))
        path = Path(self._tmp.name) / "enigmars-util" / "fun.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("cat_mode", raw)


if __name__ == "__main__":
    unittest.main()
