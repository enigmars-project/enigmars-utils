"""Unprivileged check of origin/main vs the installed Enigmars Utils revision."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from enigmars_util.paths import data_root

REPO_HTTPS = "https://github.com/enigmars-project/enigmars-utils.git"
REPO_SSH = "git@github.com:enigmars-project/enigmars-utils.git"
REPO_API = "https://api.github.com/repos/enigmars-project/enigmars-utils/commits/main"
BRANCH = "main"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TIMEOUT = 20

GIT_PROBE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateStatus:
    local: str
    remote: str
    available: bool
    detail: str


def validate_sha(value: str) -> str:
    sha = value.strip().lower()
    if not SHA_RE.fullmatch(sha):
        raise UpdateError(f"invalid git sha: {value!r}")
    return sha


def short_sha(sha: str) -> str:
    sha = sha.strip()
    if len(sha) >= 7 and all(c in "0123456789abcdef" for c in sha[:7].lower()):
        return sha[:7]
    return sha or "unknown"


def parse_ls_remote(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        sha, sep, ref = line.partition("\t")
        if not sep:
            sha, sep, ref = line.partition(" ")
        ref = ref.strip()
        if ref.endswith("/" + BRANCH) or ref == BRANCH or ref == "HEAD":
            return validate_sha(sha.strip())
    raise UpdateError("origin/main not listed by git ls-remote")


def parse_github_commit_json(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UpdateError("GitHub API returned non-JSON") from exc
    if not isinstance(data, dict):
        raise UpdateError("unexpected GitHub API payload")
    sha = data.get("sha")
    if not isinstance(sha, str):
        raise UpdateError("GitHub API payload missing sha")
    return validate_sha(sha)


def revision_file() -> Path:
    return data_root() / "revision"


def installed_revision() -> str:
    path = revision_file()
    if not path.is_file():
        fallback = Path("/usr/share/enigmars-util/revision")
        path = fallback if fallback.is_file() else path
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return ""
    try:
        return validate_sha(raw)
    except UpdateError:
        return ""


def source_revision() -> str:
    root = _source_root()
    if root is None:
        return ""
    git = shutil.which("git")
    if not git:
        return ""
    try:
        proc = subprocess.run(
            [git, "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, **GIT_PROBE_ENV, "GIT_ALLOW_PROTOCOL": "https"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    try:
        return validate_sha((proc.stdout or "").strip())
    except UpdateError:
        return ""


def local_revision() -> str:
    installed = installed_revision()
    if installed:
        return installed
    return source_revision()


def remote_main_sha() -> str:
    errors: list[str] = []
    git = shutil.which("git")
    if git:
        for url, allow in ((REPO_HTTPS, "https"), (REPO_SSH, "ssh:https")):
            try:
                return _ls_remote(git, url, allow)
            except UpdateError as exc:
                errors.append(str(exc))
    try:
        return _github_api_sha()
    except UpdateError as exc:
        errors.append(str(exc))
    raise UpdateError("; ".join(errors) if errors else "could not read origin/main")


def check_for_update() -> UpdateStatus:
    local = local_revision()
    remote = remote_main_sha()
    if local and local == remote:
        return UpdateStatus(local, remote, False, "already on origin/main")
    if not local:
        return UpdateStatus("", remote, True, "no local revision recorded; origin/main is newer or unknown")
    return UpdateStatus(local, remote, True, "origin/main has new commits")


def _source_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "enigmars_util").is_dir() and (parent / ".git").exists():
            return parent
    return None


def _ls_remote(git: str, url: str, allow: str) -> str:
    try:
        proc = subprocess.run(
            [git, "ls-remote", "--", url, f"refs/heads/{BRANCH}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env={**os.environ, **GIT_PROBE_ENV, "GIT_ALLOW_PROTOCOL": allow},
        )
    except subprocess.TimeoutExpired as exc:
        raise UpdateError(f"git ls-remote timed out for {url}") from exc
    except OSError as exc:
        raise UpdateError(f"git ls-remote failed: {exc}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ls-remote failed").strip().splitlines()
        raise UpdateError(err[-1] if err else f"ls-remote failed for {url}")
    return parse_ls_remote(proc.stdout or "")


def _github_api_sha() -> str:
    req = urllib.request.Request(
        REPO_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "enigmars-util",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise UpdateError(f"GitHub API: {exc}") from exc
    except TimeoutError as exc:
        raise UpdateError("GitHub API timed out") from exc
    return parse_github_commit_json(body)
