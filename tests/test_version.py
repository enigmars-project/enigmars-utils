"""All version pins must agree (pyproject, package, PKGBUILDs, debian control)."""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_version() -> str:
    from enigmars_util import __version__

    return __version__


class VersionPinsTest(unittest.TestCase):
    def test_pins_agree(self) -> None:
        version = _read_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")

        with (ROOT / "pyproject.toml").open("rb") as fh:
            self.assertEqual(tomllib.load(fh)["project"]["version"], version)

        control = (ROOT / "packaging" / "debian" / "control").read_text(encoding="utf-8")
        self.assertIn(f"Version: {version}", control.splitlines())

        for name in ("PKGBUILD.local", "PKGBUILD"):
            text = (ROOT / "packaging" / "arch" / name).read_text(encoding="utf-8")
            self.assertIn(f"pkgver={version}", text.splitlines())

        changelog = (ROOT / "packaging" / "debian" / "changelog").read_text(encoding="utf-8")
        self.assertTrue(changelog.startswith(f"enigmars-utils ({version})"))

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(version, readme)

        top_changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(top_changelog, re.compile(rf"^## {re.escape(version)}$", re.M))


if __name__ == "__main__":
    unittest.main()
