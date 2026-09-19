"""ESP / kernel-staging repair (pre-2026-07-09 ISOs). Unprivileged side.

Lists partitions and picks candidates; the actual mount/chroot/pacman work
runs in the privileged helper (``esp-repair`` verb). All parsing here is
pure so tests cover it without root or disks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Partition:
    path: str  # e.g. /dev/nvme0n1p1
    fstype: str  # e.g. vfat, btrfs, ext4 ("" if unknown)
    size: str  # human size from lsblk ("" if unknown)
    mountpoint: str  # "" when unmounted
    label: str


ROOT_FSTYPES = ("btrfs", "ext4", "xfs")


def parse_lsblk(text: str) -> list[Partition]:
    """Parse ``lsblk -J`` output into partitions (type part/disk children)."""
    try:
        doc = json.loads(text)
    except ValueError:
        return []
    if not isinstance(doc, dict):
        return []
    out: list[Partition] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "part":
            name = str(node.get("name") or "")
            path = str(node.get("path") or (f"/dev/{name}" if name else ""))
            if path:
                out.append(
                    Partition(
                        path=path,
                        fstype=str(node.get("fstype") or ""),
                        size=str(node.get("size") or ""),
                        mountpoint=str(node.get("mountpoint") or ""),
                        label=str(node.get("label") or ""),
                    )
                )
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child)

    devices = doc.get("blockdevices")
    if isinstance(devices, list):
        for dev in devices:
            walk(dev)
    return out


def list_partitions() -> list[Partition]:
    lsblk = shutil.which("lsblk")
    if not lsblk:
        return []
    try:
        proc = subprocess.run(
            [lsblk, "-J", "-o", "NAME,PATH,FSTYPE,SIZE,MOUNTPOINT,LABEL"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return parse_lsblk(proc.stdout or "")


def esp_candidates(parts: list[Partition]) -> list[Partition]:
    """vfat partitions are ESP candidates (unmounted preferred, order kept)."""
    cands = [p for p in parts if p.fstype.lower() == "vfat"]
    return sorted(cands, key=lambda p: bool(p.mountpoint))


def root_candidates(parts: list[Partition]) -> list[Partition]:
    """Linux filesystem partitions are root candidates."""
    cands = [p for p in parts if p.fstype.lower() in ROOT_FSTYPES]
    return sorted(cands, key=lambda p: bool(p.mountpoint))


def parse_subvolumes(text: str) -> list[str]:
    """Parse ``btrfs subvolume list`` output into subvolume paths."""
    paths: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "path " not in line:
            continue
        _, _, path = line.partition("path ")
        path = path.strip()
        if path:
            paths.append(path)
    return paths


def describe(part: Partition) -> str:
    bits = [part.path]
    if part.fstype:
        bits.append(part.fstype)
    if part.size:
        bits.append(part.size)
    if part.label:
        bits.append(f"label {part.label}")
    if part.mountpoint:
        bits.append(f"mounted at {part.mountpoint}")
    return " · ".join(bits)
