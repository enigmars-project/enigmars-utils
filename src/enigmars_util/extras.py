"""Detect the enigmars-extras pacman repo and list packages that are not installed."""

from __future__ import annotations

import glob
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from enigmars_util.names import validate_package_name
from enigmars_util.packages import Pkg

EXTRAS_REPO = "enigmars-extras"
PACMAN_CONF = Path("/etc/pacman.conf")
EXTRAS_DROPIN = Path("/etc/pacman.d/enigmars-extras.conf")
EXTRAS_INCLUDE = "Include = /etc/pacman.d/enigmars-extras.conf"
_TIMEOUT = 20

EXTRAS_SETUP = """\
[enigmars-extras]
SigLevel = Optional TrustAll
Server = https://github.com/enigmars-project/enigmars-extras/releases/latest/download
"""


@dataclass(frozen=True)
class ExtrasStatus:
    configured: bool
    packages: tuple[Pkg, ...]
    missing: tuple[Pkg, ...]
    installed: tuple[Pkg, ...]
    detail: str


class ExtrasError(Exception):
    pass


def parse_pacman_conf_repos(text: str) -> list[str]:
    repos: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]") and len(line) > 2:
            name = line[1:-1].strip()
            if name and name != "options":
                repos.append(name)
    return repos


def extras_include_present(text: str) -> bool:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, eq, rest = line.partition("=")
        if eq and key.strip().lower() == "include" and rest.strip() == str(EXTRAS_DROPIN):
            return True
    return False


def with_extras_include(text: str) -> str:
    """Return pacman.conf text that Includes the extras drop-in, without duplicating."""
    if extras_include_present(text) or EXTRAS_REPO in parse_pacman_conf_repos(text):
        return text
    body = text
    if body and not body.endswith("\n"):
        body += "\n"
    return body + "\n# enigmars-extras (enigmars-util)\n" + EXTRAS_INCLUDE + "\n"


def parse_pacman_conf_includes(text: str) -> list[str]:
    paths: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("include"):
            _, _, rest = line.partition("=")
            rest = rest.strip()
            if rest:
                paths.append(rest)
    return paths


def parse_repo_list(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def parse_pacman_sl(text: str, repo: str = EXTRAS_REPO) -> list[Pkg]:
    pkgs: list[Pkg] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[0] != repo:
            continue
        name = parts[1]
        try:
            name = validate_package_name(name)
        except ValueError:
            continue
        version = ""
        if len(parts) >= 3 and not parts[2].startswith("["):
            version = parts[2]
        installed = "[installed]" in line
        pkgs.append(Pkg(name, version, "", repo, installed))
    return pkgs


def configured_repos(
    *,
    conf: Path = PACMAN_CONF,
    pacman_conf_bin: str | None = None,
    read_text=None,
) -> list[str]:
    """Repos pacman knows about (pacman-conf, else pacman.conf + Include)."""
    exe = pacman_conf_bin if pacman_conf_bin is not None else shutil.which("pacman-conf")
    if exe:
        proc = subprocess.run(
            [exe, "--repo-list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return parse_repo_list(proc.stdout)
    reader = read_text or _read_text
    return _walk_pacman_conf(conf, reader)


def extras_configured(repos: list[str] | None = None) -> bool:
    names = repos if repos is not None else configured_repos()
    return EXTRAS_REPO in names


def extras_packages() -> list[Pkg]:
    pacman = shutil.which("pacman")
    if not pacman:
        raise ExtrasError("pacman is not installed")
    proc = subprocess.run(
        [pacman, "-Sl", EXTRAS_REPO],
        check=False,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "pacman -Sl failed").strip()
        raise ExtrasError(err.splitlines()[-1] if err else "pacman -Sl failed")
    return parse_pacman_sl(proc.stdout or "")


def probe_extras() -> ExtrasStatus:
    if not shutil.which("pacman"):
        return ExtrasStatus(False, (), (), (), "Enigmars Packages needs pacman (EnigmarsOS / Arch).")
    repos = configured_repos()
    present = EXTRAS_REPO in repos
    try:
        pkgs = extras_packages()
    except ExtrasError as exc:
        if present:
            return ExtrasStatus(
                True,
                (),
                (),
                (),
                f"{EXTRAS_REPO} is in pacman.conf but the sync db is empty. "
                f"Run a system update (pacman -Sy). ({exc})",
            )
        return ExtrasStatus(
            False,
            (),
            (),
            (),
            f"The {EXTRAS_REPO} repo is not configured.",
        )
    if not present and pkgs:
        present = True
    installed = tuple(p for p in pkgs if p.installed)
    missing = tuple(p for p in pkgs if not p.installed)
    if not pkgs:
        detail = f"{EXTRAS_REPO} is configured but lists no packages."
    elif not missing:
        detail = f"All {len(installed)} package(s) from {EXTRAS_REPO} are installed."
    else:
        detail = (
            f"{len(missing)} not installed, {len(installed)} already installed "
            f"in {EXTRAS_REPO}."
        )
    return ExtrasStatus(present, tuple(pkgs), missing, installed, detail)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _walk_pacman_conf(conf: Path, read_text) -> list[str]:
    repos: list[str] = []
    seen_files: set[Path] = set()

    def walk(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen_files:
            return
        seen_files.add(resolved)
        text = read_text(path)
        if not text:
            return
        for name in parse_pacman_conf_repos(text):
            if name not in repos:
                repos.append(name)
        for raw in parse_pacman_conf_includes(text):
            for match in glob.glob(raw) or [raw]:
                walk(Path(match))

    walk(conf)
    return repos
