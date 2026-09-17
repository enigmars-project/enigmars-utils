"""Detect the EnigmarsOS kernel pacman repos.

On EnigmarsOS the kernels ship in two repos (see the EnigmarsOS tree at
``archiso/airootfs/etc/pacman.d/``), each delivered as a drop-in that
``/etc/pacman.conf`` Includes:

- ``[linux-enigmarsos]`` (rolling kernel + headers) from the
  ``linux-enigmarsos`` GitHub ``latest`` release download,
- ``[linux-enigmarsos-lts]`` (LTS kernel + headers) from the
  ``linux-enigmarsos`` GitHub ``lts`` release download.

Both use ``SigLevel = Optional TrustAll``. Mutations run through the
privileged helper (``kernel-repo-setup`` verb); this module only reads
state and edits pacman.conf *text* (pure functions).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

KERNEL_REPOS = ("linux-enigmarsos", "linux-enigmarsos-lts")

PACMAN_CONF = Path("/etc/pacman.conf")
PACMAN_D = Path("/etc/pacman.d")

KERNEL_DROPINS: dict[str, Path] = {
    "linux-enigmarsos": PACMAN_D / "linux-enigmarsos.conf",
    "linux-enigmarsos-lts": PACMAN_D / "linux-enigmarsos-lts.conf",
}

KERNEL_SETUPS: dict[str, str] = {
    "linux-enigmarsos": """\
[linux-enigmarsos]
SigLevel = Optional TrustAll
Server = https://github.com/enigmars-project/linux-enigmarsos/releases/latest/download
""",
    "linux-enigmarsos-lts": """\
[linux-enigmarsos-lts]
SigLevel = Optional TrustAll
Server = https://github.com/enigmars-project/linux-enigmarsos/releases/download/lts
""",
}

KERNEL_INCLUDES: dict[str, str] = {
    repo: f"Include = {path}" for repo, path in KERNEL_DROPINS.items()
}


@dataclass(frozen=True)
class KernelRepoStatus:
    configured: tuple[str, ...]
    missing: tuple[str, ...]
    detail: str


class KernelRepoError(Exception):
    pass


def kernel_include_present(text: str, repo: str) -> bool:
    want = KERNEL_INCLUDES[repo]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == want:
            return True
    return False


def kernel_repo_present(text: str, repo: str) -> bool:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]") and len(line) > 2:
            if line[1:-1].strip() == repo:
                return True
    return False


def with_kernel_include(text: str, repo: str) -> str:
    """Return pacman.conf text that Includes the repo drop-in, without duplicating."""
    if kernel_include_present(text, repo) or kernel_repo_present(text, repo):
        return text
    body = text
    if body and not body.endswith("\n"):
        body += "\n"
    return body + f"\n# {repo} (enigmars-util)\n" + KERNEL_INCLUDES[repo] + "\n"


def probe_kernel_repos(repos: list[str] | None = None) -> KernelRepoStatus:
    """Best-effort status of the EnigmarsOS kernel repos (never raises for missing tools)."""
    if not shutil.which("pacman"):
        return KernelRepoStatus((), KERNEL_REPOS, "EnigmarsOS kernels need pacman (EnigmarsOS / Arch).")
    if repos is None:
        try:
            from enigmars_util.extras import configured_repos
        except Exception:  # noqa: BLE001
            names: list[str] = []
        else:
            try:
                names = configured_repos()
            except Exception:  # noqa: BLE001
                names = []
    else:
        names = repos
    configured = tuple(r for r in KERNEL_REPOS if r in names)
    missing = tuple(r for r in KERNEL_REPOS if r not in names)
    if not missing:
        detail = "linux-enigmarsos and linux-enigmarsos-lts repos are enabled."
    elif not configured:
        detail = "EnigmarsOS kernel repos are not configured."
    else:
        detail = f"{', '.join(configured)} enabled; {', '.join(missing)} missing."
    return KernelRepoStatus(configured, missing, detail)
