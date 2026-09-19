"""Unprivileged client for the pkexec helper. Streams output via QProcess or subprocess."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from enigmars_util.names import (
    validate_aur_helper,
    validate_device,
    validate_package_list,
    validate_service,
    validate_verb,
)
from enigmars_util.paths import HELPER_PATH


def _appimage_helper() -> Path | None:
    appdir = os.environ.get("APPDIR")
    if not appdir:
        return None
    bundled = Path(appdir) / "usr/libexec/enigmars-util-helper"
    return bundled if bundled.is_file() else None


def helper_executable() -> Path | None:
    if HELPER_PATH.is_file() and os.access(HELPER_PATH, os.X_OK):
        return HELPER_PATH
    env = os.environ.get("ENIGMARS_UTIL_HELPER")
    if env:
        path = Path(env)
        if path.is_file():
            return path
    bundled = _appimage_helper()
    if bundled is not None:
        return bundled
    found = shutil.which("enigmars-util-helper")
    if found:
        return Path(found)
    return None


def pkexec_cmd(verb: str, args: list[str] | None = None) -> list[str]:
    verb = validate_verb(verb)
    args = list(args or [])
    helper = helper_executable()
    if helper is None:
        raise FileNotFoundError(
            "enigmars-util-helper is not available (install the .deb/.rpm "
            "or run from the AppImage so the helper can be registered with polkit)"
        )
    pkexec = shutil.which("pkexec")
    if not pkexec:
        raise FileNotFoundError("pkexec is not installed")
    return [pkexec, str(helper), verb, *args]


def pkg_install_cmd(names: list[str]) -> list[str]:
    names = validate_package_list(names)
    return pkexec_cmd("pkg-install", names)


def pkg_remove_cmd(names: list[str]) -> list[str]:
    names = validate_package_list(names)
    return pkexec_cmd("pkg-remove", names)


def pkg_update_cmd() -> list[str]:
    return pkexec_cmd("pkg-update")


def pkg_refresh_cmd() -> list[str]:
    return pkexec_cmd("pkg-refresh")


def kernel_sync_esp_cmd() -> list[str]:
    return pkexec_cmd("kernel-sync-esp")


def ufw_cmd(enable: bool) -> list[str]:
    return pkexec_cmd("ufw-enable" if enable else "ufw-disable")


def service_cmd(enable: bool, name: str) -> list[str]:
    name = validate_service(name)
    return pkexec_cmd("service-enable" if enable else "service-disable", [name])


def sbctl_enroll_cmd() -> list[str]:
    return pkexec_cmd("sbctl-enroll")


def firmware_reboot_cmd() -> list[str]:
    return pkexec_cmd("firmware-reboot")


def aur_helper_setup_cmd(name: str) -> list[str]:
    name = validate_aur_helper(name)
    return pkexec_cmd("aur-helper-setup", [name])


def self_update_cmd() -> list[str]:
    return pkexec_cmd("self-update")


def extras_repo_setup_cmd() -> list[str]:
    return pkexec_cmd("extras-repo-setup")


def chaotic_repo_setup_cmd() -> list[str]:
    return pkexec_cmd("chaotic-repo-setup")


def kernel_repo_setup_cmd() -> list[str]:
    return pkexec_cmd("kernel-repo-setup")


def kernel_repo_repair_cmd() -> list[str]:
    return pkexec_cmd("repo-repair-kernel")


def esp_repair_cmd(esp: str, root: str) -> list[str]:
    esp = validate_device(esp)
    root = validate_device(root)
    if esp == root:
        raise ValueError("ESP and root must be different partitions")
    return pkexec_cmd("esp-repair", [esp, root])
