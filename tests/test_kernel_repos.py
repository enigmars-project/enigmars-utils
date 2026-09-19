from __future__ import annotations

import shutil
import unittest
from unittest import mock

from enigmars_util.kernel_repos import (
    KERNEL_DROPINS,
    KERNEL_INCLUDES,
    KERNEL_REPOS,
    kernel_include_present,
    kernel_repo_present,
    probe_kernel_repos,
    with_kernel_include,
)


class KernelReposConfTest(unittest.TestCase):
    def test_detect_repo_and_include(self) -> None:
        text = (
            "[core]\n"
            "Include = /etc/pacman.d/mirrorlist\n"
            "[linux-enigmarsos]\n"
            "SigLevel = Optional TrustAll\n"
            "Server = https://github.com/enigmars-project/linux-enigmarsos/releases/latest/download\n"
        )
        self.assertTrue(kernel_repo_present(text, "linux-enigmarsos"))
        self.assertFalse(kernel_repo_present(text, "linux-enigmarsos-lts"))
        self.assertFalse(kernel_include_present(text, "linux-enigmarsos"))
        commented = "# [linux-enigmarsos]\n# Include = /etc/pacman.d/linux-enigmarsos.conf\n"
        self.assertFalse(kernel_repo_present(commented, "linux-enigmarsos"))
        self.assertFalse(kernel_include_present(commented, "linux-enigmarsos"))

    def test_include_matches_dropin_path(self) -> None:
        for repo in KERNEL_REPOS:
            self.assertEqual(KERNEL_INCLUDES[repo], f"Include = {KERNEL_DROPINS[repo]}")

    def test_include_is_idempotent(self) -> None:
        base = "[options]\nHoldPkg = pacman\n[core]\nInclude = /etc/pacman.d/mirrorlist\n"
        for repo in KERNEL_REPOS:
            once = with_kernel_include(base, repo)
            self.assertIn(KERNEL_INCLUDES[repo], once)
            self.assertEqual(with_kernel_include(once, repo), once)
        inline = "[core]\n[linux-enigmarsos]\nServer = https://example.invalid\n"
        self.assertEqual(with_kernel_include(inline, "linux-enigmarsos"), inline)

    def test_probe_without_pacman_is_safe(self) -> None:
        with mock.patch.object(shutil, "which", return_value=None):
            status = probe_kernel_repos()
        self.assertEqual(status.configured, ())
        self.assertEqual(status.missing, KERNEL_REPOS)
        self.assertIn("pacman", status.detail.lower())

    def test_probe_repo_lists(self) -> None:
        # Hermetic: CI runners (ubuntu) have no pacman; the explicit repo
        # list must be evaluated regardless of host tooling.
        with mock.patch.object(shutil, "which", return_value="/usr/bin/pacman"):
            full = probe_kernel_repos(["core", *KERNEL_REPOS])
            self.assertEqual(full.configured, KERNEL_REPOS)
            self.assertEqual(full.missing, ())
            partial = probe_kernel_repos(["core", "linux-enigmarsos"])
            self.assertEqual(partial.configured, ("linux-enigmarsos",))
            self.assertEqual(partial.missing, ("linux-enigmarsos-lts",))
            empty = probe_kernel_repos(["core", "extra"])
            self.assertEqual(empty.configured, ())


if __name__ == "__main__":
    unittest.main()
