"""One-click repair patches. Patch #1: kernel repository repair (Sept 2026).

Three failure modes, one logical patch:

- ``enigmarsos-offline`` shadow: the frozen ISO snapshot drop-in stays
  Included on installed systems, so ``pacman`` resolves
  ``linux-enigmarsos`` from the offline snapshot instead of the rolling
  repo — pinning the kernel forever. Legitimate on the live ISO itself.
- LTS not tracking ``lts``: ``/etc/pacman.d/linux-enigmarsos-lts.conf``
  points at a pinned release tag (or anything other than the stable
  ``releases/download/lts`` URL), so LTS updates stop flowing. The fix
  rewrites the Server URL to the stable ``lts`` tag, which the release
  workflow retargets on every LTS release.
- Org move: pacman drop-ins still point at ``github.com/RishiSpace/*``
  (or ``api.github.com/repos/RishiSpace/*``). The fix rewrites them to
  ``github.com/enigmars-project/*`` so pre-move installs keep tracking
  releases after the transfer.

This module only probes. The fix runs through the privileged helper
(``repo-repair-kernel`` verb); probe helpers are pure/small so tests can
cover them without root.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LTS_CONF = Path("/etc/pacman.d/linux-enigmarsos-lts.conf")
OFFLINE_CONF = Path("/etc/pacman.d/enigmarsos-offline.conf")
OFFLINE_INCLUDE = "Include = /etc/pacman.d/enigmarsos-offline.conf"
PACMAN_CONF = Path("/etc/pacman.conf")

OLD_GITHUB_ORG = "RishiSpace"
NEW_GITHUB_ORG = "enigmars-project"
ORG_MIGRATION_CONFS = (
    Path("/etc/pacman.d/linux-enigmarsos.conf"),
    Path("/etc/pacman.d/linux-enigmarsos-lts.conf"),
    Path("/etc/pacman.d/enigmars-extras.conf"),
)

LIVE_ISO_MARKERS = (Path("/run/archiso"), Path("/etc/enigmarsos/iso-build"))

# Stable tag is `releases/download/lts` with nothing after `lts`. The
# negative lookahead keeps versioned tags such as
# `.../download/linux-enigmarsos-lts-6.18.51` from matching as stable.
_LTS_STABLE_RE = re.compile(r"releases/download/lts(?![-\w])")
# Any other `releases/download/<tag>` is a pinned (frozen) tag.
_LTS_PINNED_RE = re.compile(r"releases/download/(?!lts(?![-\w]))([^\s\"']+)")
_DOWNLOAD_TAG_RE = re.compile(r"releases/download/([^\s\"']+)")

_TIMEOUT = 20


@dataclass(frozen=True)
class KernelRepoPatchStatus:
    offline_shadows: bool  # pacman resolves linux-enigmarsos from enigmarsos-offline
    lts_not_tracking: bool  # lts conf Server does not use the stable releases/download/lts URL
    on_live_iso: bool  # /run/archiso exists or /etc/enigmarsos/iso-build present

    @property
    def needs_patch(self) -> bool:
        if self.on_live_iso:
            return False
        return self.offline_shadows or self.lts_not_tracking


def lts_tracks_in(text: str) -> bool:
    """True when a Server line uses the stable `releases/download/lts` URL."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("=")
        if key.strip().lower() != "server":
            continue
        if _LTS_STABLE_RE.search(rest):
            return True
    return False


def retrack_lts_in_text(text: str) -> str:
    """Rewrite pinned `releases/download/<tag>` URLs to the stable `lts` tag.

    Idempotent: URLs already on the stable tag are left untouched, as is
    every non-Server line (formatting preserved).
    """
    out: list[str] = []
    for raw in text.splitlines(keepends=True):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            key, eq, _ = stripped.partition("=")
            if eq and key.strip().lower() == "server":
                raw = _LTS_PINNED_RE.sub("releases/download/lts", raw)
        out.append(raw)
    return "".join(out)


def lts_pinned_tag(text: str) -> str | None:
    """Versioned tag pinned in the LTS conf Server URL, or None if tracking/stable/missing."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("=")
        if key.strip().lower() != "server":
            continue
        match = _DOWNLOAD_TAG_RE.search(rest)
        if not match:
            continue
        tag = match.group(1).rstrip("/")
        if tag in ("", "lts", "latest"):
            return None
        return tag
    return None


def offline_include_present(text: str) -> bool:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == OFFLINE_INCLUDE:
            return True
    return False


def org_migration_needed_in(text: str) -> bool:
    """True when a Server line still points at the old GitHub org."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("=")
        if key.strip().lower() != "server":
            continue
        if f"github.com/{OLD_GITHUB_ORG}/" in rest:
            return True
        if f"api.github.com/repos/{OLD_GITHUB_ORG}/" in rest:
            return True
    return False


def migrate_org_in_text(text: str) -> str:
    """Rewrite old-org pacman Server URLs to the new org (idempotent)."""
    return text.replace(
        f"github.com/{OLD_GITHUB_ORG}/", f"github.com/{NEW_GITHUB_ORG}/"
    ).replace(
        f"api.github.com/repos/{OLD_GITHUB_ORG}/",
        f"api.github.com/repos/{NEW_GITHUB_ORG}/",
    )


@dataclass(frozen=True)
class OrgMigrationStatus:
    pending: tuple[str, ...]  # conf paths whose Server lines still use the old org

    @property
    def needs_patch(self) -> bool:
        return bool(self.pending)


def probe_org_migration() -> OrgMigrationStatus:
    """Best-effort org-migration status (never raises for missing files)."""
    pending: list[str] = []
    for conf in ORG_MIGRATION_CONFS:
        try:
            if org_migration_needed_in(_read_text(conf)):
                pending.append(str(conf))
        except Exception:  # noqa: BLE001
            continue
    return OrgMigrationStatus(tuple(pending))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _on_live_iso() -> bool:
    try:
        return any(marker.exists() for marker in LIVE_ISO_MARKERS)
    except OSError:
        return False


def _pacman_si_repo(package: str) -> str | None:
    pacman = shutil.which("pacman")
    if not pacman:
        return None
    try:
        proc = subprocess.run(
            [pacman, "-Si", "--", package],
            check=False,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    for line in (proc.stdout or "").splitlines():
        key, _, rest = line.partition(":")
        if key.strip().lower() == "repository":
            return rest.strip() or None
    return None


def _offline_shadows() -> bool:
    # The frozen snapshot is legitimate on the live ISO; never flag there.
    if _on_live_iso():
        return False
    if _pacman_si_repo("linux-enigmarsos") != "enigmarsos-offline":
        return False
    return offline_include_present(_read_text(PACMAN_CONF))


def _lts_not_tracking() -> bool:
    # A missing conf means the repos were never enabled — the Kernel tab owns
    # that flow, not this patch.
    try:
        present = LTS_CONF.is_file()
    except OSError:
        return False
    if not present:
        return False
    return not lts_tracks_in(_read_text(LTS_CONF))


def probe_kernel_repo_patch() -> KernelRepoPatchStatus:
    """Best-effort patch status (never raises for missing tools/files)."""
    try:
        iso = _on_live_iso()
    except Exception:  # noqa: BLE001
        iso = False
    try:
        shadows = _offline_shadows()
    except Exception:  # noqa: BLE001
        shadows = False
    try:
        off_track = _lts_not_tracking()
    except Exception:  # noqa: BLE001
        off_track = False
    return KernelRepoPatchStatus(shadows, off_track, iso)
