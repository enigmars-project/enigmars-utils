from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from enigmars_util.paths import sound_path
from enigmars_util.sound import external_command, play_meow


class SoundTest(unittest.TestCase):
    def test_sound_resolves_to_bundled_meow(self) -> None:
        path = sound_path()
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.name, "meow.mp3")

    def test_unknown_name_falls_back_to_meow(self) -> None:
        path = sound_path("../../etc/passwd")
        self.assertEqual(path.name, "meow.mp3")

    def test_external_command_rejects_missing_file(self) -> None:
        self.assertIsNone(external_command(Path("/nonexistent/meow.mp3")))

    def test_play_meow_uses_external_fallback_without_qt_app(self) -> None:
        # No QApplication in unit tests: _play_qt bails, Popen is mocked (no noise).
        with mock.patch("subprocess.Popen") as popen:
            self.assertTrue(play_meow(volume=0))
            popen.assert_called_once()

    def test_play_meow_false_when_no_player(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(play_meow(volume=0))


if __name__ == "__main__":
    unittest.main()
