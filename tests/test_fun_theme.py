from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from enigmars_util import fun_theme


class FunThemeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_data = os.environ.get("ENIGMARS_UTIL_DATA")
        self._old_config = os.environ.get("XDG_CONFIG_HOME")
        self._old_share = os.environ.get("XDG_DATA_HOME")
        repo_data = Path(__file__).resolve().parents[1] / "data"
        os.environ["ENIGMARS_UTIL_DATA"] = str(repo_data)
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        os.environ["XDG_DATA_HOME"] = self._tmp.name

    def tearDown(self) -> None:
        for key, old in (
            ("ENIGMARS_UTIL_DATA", self._old_data),
            ("XDG_CONFIG_HOME", self._old_config),
            ("XDG_DATA_HOME", self._old_share),
        ):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self._tmp.cleanup()

    def test_install_enable_uninstall(self) -> None:
        self.assertFalse(fun_theme.enabled())
        self.assertTrue(fun_theme.install())
        self.assertTrue(fun_theme.enabled())
        for source in fun_theme.EVENTS.values():
            self.assertTrue((fun_theme.sounds_dir() / source).is_file())
        self.assertTrue(fun_theme.notify_path().is_file())
        self.assertTrue(fun_theme.uninstall())
        self.assertFalse(fun_theme.enabled())
        self.assertFalse(fun_theme.sounds_dir().exists())

    def test_uninstall_preserves_other_events(self) -> None:
        self.assertTrue(fun_theme.install())
        cfg_path = fun_theme.notify_path()
        with cfg_path.open("a", encoding="utf-8") as fh:
            fh.write("[Event/other]\nSound=something-else\n")
        self.assertTrue(fun_theme.uninstall())
        self.assertIn("something-else", cfg_path.read_text(encoding="utf-8"))

    def test_preview_rejects_unknown_event(self) -> None:
        self.assertFalse(fun_theme.preview("nope"))


if __name__ == "__main__":
    unittest.main()
