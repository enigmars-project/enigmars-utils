"""Validation for untrusted identifiers passed to the privileged helper."""

from __future__ import annotations

import re

PKG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._+-]*$")
MAX_PKG_NAME = 128
MAX_PKGS = 64

ALLOWED_SERVICES = frozenset({"ufw", "docker.socket", "libvirtd"})
ALLOWED_AUR_HELPERS = frozenset({"yay", "paru"})
ALLOWED_VERBS = frozenset(
    {
        "pkg-install",
        "pkg-remove",
        "pkg-update",
        "pkg-refresh",
        "kernel-sync-esp",
        "ufw-enable",
        "ufw-disable",
        "service-enable",
        "service-disable",
        "sbctl-enroll",
        "firmware-reboot",
        "aur-helper-setup",
        "self-update",
        "extras-repo-setup",
        "chaotic-repo-setup",
        "kernel-repo-setup",
        "repo-repair-kernel",
        "esp-repair",
    }
)

_SHELL_META = frozenset(";&|<>`$(){}[]\n\r\t\\*?!~#'\"")


def validate_package_name(name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > MAX_PKG_NAME:
        raise ValueError("invalid package name")
    if ".." in name or "/" in name or any(ch in _SHELL_META for ch in name):
        raise ValueError(f"invalid package name: {name!r}")
    if not PKG_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid package name: {name!r}")
    return name


def validate_package_list(names: list[str]) -> list[str]:
    if len(names) > MAX_PKGS:
        raise ValueError("too many packages")
    out = [validate_package_name(n) for n in names]
    if not out:
        raise ValueError("no packages given")
    return out


def validate_service(name: str) -> str:
    if name not in ALLOWED_SERVICES:
        raise ValueError(f"service not allowed: {name!r}")
    return name


def validate_verb(verb: str) -> str:
    if verb not in ALLOWED_VERBS:
        raise ValueError(f"unknown verb: {verb!r}")
    return verb


DEVICE_RE = re.compile(r"^/dev/[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$")
MAX_DEVICE_LEN = 69


def validate_device(dev: str) -> str:
    """Strict allowlist for block-device args (ESP/root pickers).

    Rejects shell metacharacters, traversal, non-/dev paths. The helper
    additionally stats S_ISBLK and checks fstype before mounting.
    """
    if not isinstance(dev, str) or not dev or len(dev) > MAX_DEVICE_LEN:
        raise ValueError(f"invalid device: {dev!r}")
    if ".." in dev or any(ch in _SHELL_META for ch in dev) or " " in dev:
        raise ValueError(f"invalid device: {dev!r}")
    if not DEVICE_RE.fullmatch(dev):
        raise ValueError(f"invalid device: {dev!r}")
    return dev


def validate_aur_helper(name: str) -> str:
    if name not in ALLOWED_AUR_HELPERS:
        raise ValueError(f"aur helper not allowed: {name!r}")
    return name


def validate_search_query(query: str) -> str:
    q = query.strip()
    if not q or len(q) > 80:
        return ""
    if any(ch in _SHELL_META for ch in q):
        return ""
    return q
