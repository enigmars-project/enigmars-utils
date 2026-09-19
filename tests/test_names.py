from __future__ import annotations

import unittest

from enigmars_util.names import (
    validate_aur_helper,
    validate_device,
    validate_package_list,
    validate_package_name,
    validate_search_query,
    validate_service,
    validate_verb,
)


class NamesTest(unittest.TestCase):
    def test_good_package(self) -> None:
        self.assertEqual(validate_package_name("linux-lts"), "linux-lts")
        self.assertEqual(validate_package_name("lib32-mesa"), "lib32-mesa")
        self.assertEqual(validate_package_name("foo@bar"), "foo@bar")

    def test_bad_package(self) -> None:
        for bad in ("", "-oops", "../etc", "foo;rm", "foo bar", "a/b", "x" * 200, "$(id)"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_package_name(bad)

    def test_list_limit(self) -> None:
        with self.assertRaises(ValueError):
            validate_package_list([])
        with self.assertRaises(ValueError):
            validate_package_list(["a"] * 65)

    def test_verb_and_service(self) -> None:
        self.assertEqual(validate_verb("pkg-install"), "pkg-install")
        self.assertEqual(validate_verb("aur-helper-setup"), "aur-helper-setup")
        self.assertEqual(validate_verb("self-update"), "self-update")
        self.assertEqual(validate_verb("extras-repo-setup"), "extras-repo-setup")
        self.assertEqual(validate_verb("chaotic-repo-setup"), "chaotic-repo-setup")
        self.assertEqual(validate_verb("kernel-repo-setup"), "kernel-repo-setup")
        self.assertEqual(validate_verb("repo-repair-kernel"), "repo-repair-kernel")
        with self.assertRaises(ValueError):
            validate_verb("rm")
        self.assertEqual(validate_service("ufw"), "ufw")
        with self.assertRaises(ValueError):
            validate_service("sshd")
        self.assertEqual(validate_aur_helper("yay"), "yay")
        self.assertEqual(validate_aur_helper("paru"), "paru")
        with self.assertRaises(ValueError):
            validate_aur_helper("pikaur")
        with self.assertRaises(ValueError):
            validate_aur_helper("yay;id")

    def test_search_query(self) -> None:
        self.assertEqual(validate_search_query(" firefox "), "firefox")
        self.assertEqual(validate_search_query("foo;bar"), "")
        self.assertEqual(validate_search_query(""), "")

    def test_good_device(self) -> None:
        for good in ("/dev/nvme0n1p1", "/dev/sda2", "/dev/mmcblk0p1", "/dev/mapper/vg-root", "/dev/dm-0"):
            with self.subTest(dev=good):
                self.assertEqual(validate_device(good), good)

    def test_bad_device(self) -> None:
        for bad in (
            "",
            "/dev/",
            "sda1",
            "/etc/passwd",
            "/dev/../etc/passwd",
            "/dev/sda1;reboot",
            "/dev/sda1|id",
            "/dev/sda 1",
            "/dev/$(id)",
            "/dev/sda1\nreboot",
            "/dev/" + "a" * 70,
        ):
            with self.subTest(dev=bad):
                with self.assertRaises(ValueError):
                    validate_device(bad)

    def test_esp_repair_verb_known(self) -> None:
        self.assertEqual(validate_verb("esp-repair"), "esp-repair")


if __name__ == "__main__":
    unittest.main()
