from __future__ import annotations

import json
import unittest

from enigmars_util.esp_repair import (
    ROOT_FSTYPES,
    describe,
    esp_candidates,
    parse_lsblk,
    parse_subvolumes,
    root_candidates,
)

LSBLK = {
    "blockdevices": [
        {
            "name": "nvme0n1",
            "type": "disk",
            "children": [
                {
                    "name": "nvme0n1p1",
                    "path": "/dev/nvme0n1p1",
                    "type": "part",
                    "fstype": "vfat",
                    "size": "1G",
                    "mountpoint": None,
                    "label": "ESP",
                },
                {
                    "name": "nvme0n1p2",
                    "path": "/dev/nvme0n1p2",
                    "type": "part",
                    "fstype": "btrfs",
                    "size": "100G",
                    "mountpoint": "/",
                    "label": None,
                },
            ],
        },
        {
            "name": "sda",
            "type": "disk",
            "children": [
                {
                    "name": "sda1",
                    "path": "/dev/sda1",
                    "type": "part",
                    "fstype": "ext4",
                    "size": "50G",
                    "mountpoint": None,
                    "label": "oldroot",
                }
            ],
        },
    ]
}


class EspRepairParseTest(unittest.TestCase):
    def test_parse_lsblk(self) -> None:
        parts = parse_lsblk(json.dumps(LSBLK))
        self.assertEqual([p.path for p in parts], ["/dev/nvme0n1p1", "/dev/nvme0n1p2", "/dev/sda1"])
        self.assertEqual(parts[0].fstype, "vfat")
        self.assertEqual(parts[1].mountpoint, "/")
        self.assertEqual(parts[2].label, "oldroot")

    def test_parse_lsblk_rejects_garbage(self) -> None:
        self.assertEqual(parse_lsblk("not json"), [])
        self.assertEqual(parse_lsblk(json.dumps({"nope": 1})), [])
        self.assertEqual(parse_lsblk(json.dumps([1, 2])), [])

    def test_esp_candidates(self) -> None:
        parts = parse_lsblk(json.dumps(LSBLK))
        self.assertEqual([p.path for p in esp_candidates(parts)], ["/dev/nvme0n1p1"])

    def test_root_candidates(self) -> None:
        parts = parse_lsblk(json.dumps(LSBLK))
        roots = root_candidates(parts)
        self.assertEqual([p.path for p in roots], ["/dev/sda1", "/dev/nvme0n1p2"])
        for fstype in ("btrfs", "ext4", "xfs"):
            self.assertIn(fstype, ROOT_FSTYPES)

    def test_root_candidates_skip_foreign(self) -> None:
        parts = parse_lsblk(
            json.dumps(
                {
                    "blockdevices": [
                        {
                            "name": "sdb",
                            "type": "disk",
                            "children": [
                                {
                                    "name": "sdb1",
                                    "path": "/dev/sdb1",
                                    "type": "part",
                                    "fstype": "ntfs",
                                    "size": "10G",
                                    "mountpoint": None,
                                    "label": None,
                                }
                            ],
                        }
                    ]
                }
            )
        )
        self.assertEqual(root_candidates(parts), [])
        self.assertEqual(esp_candidates(parts), [])

    def test_parse_subvolumes(self) -> None:
        text = (
            "ID 256 gen 42 top level 5 path @\n"
            "ID 257 gen 42 top level 5 path @home\n"
            "ID 258 gen 42 top level 5 path @snapshots/root\n"
        )
        self.assertEqual(parse_subvolumes(text), ["@", "@home", "@snapshots/root"])
        self.assertEqual(parse_subvolumes("garbage\n"), [])

    def test_describe(self) -> None:
        parts = parse_lsblk(json.dumps(LSBLK))
        text = describe(parts[0])
        self.assertIn("/dev/nvme0n1p1", text)
        self.assertIn("vfat", text)


if __name__ == "__main__":
    unittest.main()
