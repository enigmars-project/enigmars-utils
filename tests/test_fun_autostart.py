from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from enigmars_util import fun_autostart


class FunAutostartTest(unittest.TestCase):
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

    def test_login_toggle(self) -> None:
        self.assertFalse(fun_autostart.login_enabled())
        fun_autostart.set_login_enabled(True)
        self.assertTrue(fun_autostart.login_enabled())
        path = Path(self._tmp.name) / "autostart" / fun_autostart.LOGIN_NAME
        self.assertIn("--meow-login", path.read_text(encoding="utf-8"))
        fun_autostart.set_login_enabled(False)
        self.assertFalse(fun_autostart.login_enabled())

    def test_exec_prefers_installed_binary(self) -> None:
        with mock.patch("shutil.which", return_value="/usr/bin/enigmars-util"):
            self.assertEqual(
                fun_autostart._exec_args(), ["enigmars-util", "--meow-login"]
            )

    def test_exec_falls_back_to_module(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            args = fun_autostart._exec_args()
            self.assertIn("--meow-login", args)
            self.assertIn("-m", args)


if __name__ == "__main__":
    unittest.main()
