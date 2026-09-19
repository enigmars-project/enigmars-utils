#!/usr/bin/env python3
"""Root helper. Allowlisted verbs, argv only, never shell=True."""

from __future__ import annotations

import glob
import json
import os
import pwd
import shutil
import subprocess
import sys
import syslog
from pathlib import Path

from enigmars_util.aur_helpers import spec_for
from enigmars_util.chaotic import (
    CHAOTIC_KEYID,
    CHAOTIC_KEYRING_URL,
    CHAOTIC_KEYSERVER,
    CHAOTIC_MIRRORLIST_URL,
    with_chaotic_include,
)
from enigmars_util.kernel_repos import (
    KERNEL_DROPINS,
    KERNEL_REPOS,
    KERNEL_SETUPS,
    with_kernel_include,
)
from enigmars_util.patches import (
    LTS_CONF,
    OFFLINE_CONF,
    ORG_MIGRATION_CONFS,
    lts_pinned_tag,
    lts_tracks_in,
    migrate_org_in_text,
    org_migration_needed_in,
    retrack_lts_in_text,
)
from enigmars_util.names import (
    validate_aur_helper,
    validate_device,
    validate_package_list,
    validate_service,
    validate_verb,
)
from enigmars_util.extras import (
    EXTRAS_DROPIN,
    EXTRAS_SETUP,
    PACMAN_CONF,
    with_extras_include,
)
from enigmars_util.self_update import (
    BRANCH,
    GIT_PROBE_ENV,
    REPO_HTTPS,
    REPO_SSH,
    UpdateError,
    installed_revision,
    parse_ls_remote,
)
from enigmars_util.paths import ESP_SYNC
from enigmars_util.esp_repair import ROOT_FSTYPES, parse_subvolumes
from enigmars_util.probe import probe_host
from enigmars_util.protocol import RESULT_PREFIX

SAFE_PATH = "/usr/bin:/usr/sbin:/bin:/sbin"


def _die(msg: str, code: int = 1) -> int:
    print(msg, file=sys.stderr)
    _result(False, msg)
    return code


def _result(ok: bool, detail: str) -> None:
    print(RESULT_PREFIX + json.dumps({"ok": ok, "detail": detail}, separators=(",", ":")))


def _syslog(verb: str, detail: str, ok: bool) -> None:
    try:
        syslog.openlog("enigmars-util-helper", syslog.LOG_PID, syslog.LOG_AUTH)
        syslog.syslog(
            syslog.LOG_NOTICE if ok else syslog.LOG_WARNING,
            f"verb={verb} ok={int(ok)} {detail}",
        )
    except OSError:
        pass


def _harden() -> None:
    os.environ["PATH"] = SAFE_PATH
    os.environ.pop("LD_PRELOAD", None)
    os.environ.pop("LD_LIBRARY_PATH", None)
    os.environ.pop("PYTHONPATH", None)
    try:
        os.umask(0o022)
    except OSError:
        pass


def _stream(
    cmd: list[str],
    *,
    user: int | None = None,
    group: int | None = None,
    cwd: str | Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    if user is None:
        env = {**os.environ, "PATH": SAFE_PATH, "DEBIAN_FRONTEND": "noninteractive"}
        if extra_env:
            env.update(extra_env)
    else:
        env = {"PATH": SAFE_PATH, **(extra_env or {})}
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "env": env,
    }
    if user is not None:
        kwargs["user"] = user
    if group is not None:
        kwargs["group"] = group
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[arg-type]
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


_PROFILE = None


def _profile():
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = probe_host()
    return _PROFILE


def _pm() -> str:
    return _profile().native_pm


def _is_enigmars() -> bool:
    return _profile().enigmarsos


def _maybe_sync_esp(names: list[str]) -> int:
    if not _is_enigmars():
        return 0
    if not any(n.startswith("linux") for n in names):
        return 0
    return _sync_esp()


def _sync_esp() -> int:
    if not ESP_SYNC.is_file():
        print(f"ESP sync script missing: {ESP_SYNC}", file=sys.stderr)
        return 1
    return _stream(["/bin/bash", str(ESP_SYNC)])


def _pkg_cmd(verb: str, names: list[str]) -> list[str]:
    pm = _pm()
    if pm == "pacman":
        pacman = shutil.which("pacman") or "/usr/bin/pacman"
        if verb == "install":
            return [pacman, "-S", "--needed", "--noconfirm", "--", *names]
        if verb == "remove":
            return [pacman, "-R", "--noconfirm", "--", *names]
        if verb == "update":
            return [pacman, "-Syu", "--noconfirm"]
        if verb == "refresh":
            return [pacman, "-Sy", "--noconfirm"]
    if pm == "apt":
        apt = shutil.which("apt-get") or "/usr/bin/apt-get"
        if verb == "install":
            return [apt, "install", "-y", "--", *names]
        if verb == "remove":
            return [apt, "remove", "-y", "--", *names]
        if verb == "update":
            return [apt, "dist-upgrade", "-y"]
        if verb == "refresh":
            return [apt, "update", "-y"]
    if pm == "dnf":
        dnf = shutil.which("dnf5") or shutil.which("dnf") or "/usr/bin/dnf"
        if verb == "install":
            return [dnf, "install", "-y", "--", *names]
        if verb == "remove":
            return [dnf, "remove", "-y", "--", *names]
        if verb == "update":
            return [dnf, "upgrade", "-y"]
        if verb == "refresh":
            return [dnf, "makecache"]
    if pm == "zypper":
        zypper = shutil.which("zypper") or "/usr/bin/zypper"
        if verb == "install":
            return [zypper, "--non-interactive", "install", "--", *names]
        if verb == "remove":
            return [zypper, "--non-interactive", "remove", "--", *names]
        if verb == "update":
            return [zypper, "--non-interactive", "update"]
        if verb == "refresh":
            return [zypper, "--non-interactive", "refresh"]
    raise ValueError(f"unsupported package manager: {pm}")


_SIGN_GLOBS = (
    "/boot/efi/EFI/BOOT/BOOTX64.EFI",
    "/boot/efi/EFI/BOOT/BOOTX64.efi",
    "/boot/efi/EFI/EnigmarsOS/BOOTX64.EFI",
    "/boot/efi/EFI/EnigmarsOS/vmlinuz-*",
    "/boot/vmlinuz-*",
    "/efi/EFI/BOOT/BOOTX64.EFI",
    "/efi/EFI/EnigmarsOS/BOOTX64.EFI",
    "/efi/EFI/EnigmarsOS/vmlinuz-*",
)


def _sbctl_enroll() -> int:
    sbctl = shutil.which("sbctl") or "/usr/bin/sbctl"
    if not Path(sbctl).is_file():
        print("sbctl is not installed", file=sys.stderr)
        return 1
    _stream([sbctl, "setup", "--setup"])
    if not Path("/var/lib/sbctl/keys/db").is_dir():
        rc = _stream([sbctl, "create-keys"])
        if rc != 0:
            return rc
    rc = _stream([sbctl, "enroll-keys", "-m"])
    if rc != 0:
        return rc
    for pattern in _SIGN_GLOBS:
        for path in glob.glob(pattern):
            if Path(path).is_file():
                _stream([sbctl, "sign", "-s", path])
    _stream([sbctl, "sign-all"])
    return 0


def _invoking_user() -> tuple[int, int, str, str]:
    raw = os.environ.get("PKEXEC_UID") or os.environ.get("SUDO_UID")
    if not raw or not raw.isdigit():
        raise ValueError("cannot determine invoking user (PKEXEC_UID); run via pkexec from your session")
    uid = int(raw)
    if uid == 0:
        raise ValueError("refuse to compile as root")
    try:
        pw = pwd.getpwuid(uid)
    except KeyError as exc:
        raise ValueError(f"unknown PKEXEC_UID {uid}") from exc
    return uid, pw.pw_gid, pw.pw_name, pw.pw_dir or f"/tmp/enigmars-build-{uid}"


def _chown_tree(path: Path, uid: int, gid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        for name in dirs + files:
            try:
                os.chown(os.path.join(root, name), uid, gid)
            except OSError:
                pass


def _pacman_has(name: str) -> bool:
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    proc = subprocess.run(
        [pacman, "-Si", "--", name],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": SAFE_PATH},
    )
    return proc.returncode == 0


def _setup_aur_helper(name: str) -> int:
    if _pm() != "pacman":
        print("AUR helpers require pacman (Arch / EnigmarsOS).", file=sys.stderr)
        return 1
    spec = spec_for(name)
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    for cand in (Path("/usr/bin") / spec.binary, Path("/usr/local/bin") / spec.binary):
        if cand.is_file() and os.access(cand, os.X_OK):
            print(f"{spec.binary} already installed at {cand}")
            return 0

    if _pacman_has(spec.name):
        print(f"{spec.name} is in the pacman sync db; installing with pacman")
        return _stream([pacman, "-S", "--needed", "--noconfirm", "--", spec.name])

    print(f"{spec.name} is not in official repos; building from {spec.git_url}")
    rc = _stream([pacman, "-S", "--needed", "--noconfirm", "--", *spec.pacman_deps])
    if rc != 0:
        return rc

    git = shutil.which("git") or "/usr/bin/git"
    uid, gid, user, home = _invoking_user()
    cache = Path("/var/cache/enigmars-util")
    cache.mkdir(parents=True, exist_ok=True)
    os.chmod(cache, 0o755)
    workdir = cache / f"build-{spec.name}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(mode=0o700)
    os.chown(workdir, uid, gid)
    for sub in (".gocache", ".gopath", ".gomod", ".cargo", "tmp"):
        p = workdir / sub
        p.mkdir()
        os.chown(p, uid, gid)

    src = workdir / spec.name
    child_env = {
        "HOME": home,
        "USER": user,
        "LOGNAME": user,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "GOCACHE": str(workdir / ".gocache"),
        "GOPATH": str(workdir / ".gopath"),
        "GOMODCACHE": str(workdir / ".gomod"),
        "GOPROXY": "https://proxy.golang.org,direct",
        "CGO_ENABLED": "1",
        "CARGO_HOME": str(workdir / ".cargo"),
        "CARGO_TERM_COLOR": "never",
        "TMPDIR": str(workdir / "tmp"),
    }
    print(f"cloning {spec.git_url}")
    rc = _stream(
        [git, "clone", "--depth", "1", "--", spec.git_url, str(src)],
        extra_env={
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        },
    )
    if rc != 0:
        return rc
    if not (src / spec.marker).is_file():
        print(f"clone missing {spec.marker}", file=sys.stderr)
        return 1
    _chown_tree(workdir, uid, gid)

    if spec.kind == "make":
        make = shutil.which("make") or "/usr/bin/make"
        print(f"compiling {spec.name} (make PREFIX=/usr build)")
        rc = _stream(
            [make, "-C", str(src), "PREFIX=/usr", "build"],
            user=uid,
            group=gid,
            cwd=src,
            extra_env=child_env,
        )
        binary = src / spec.binary
    elif spec.kind == "cargo":
        cargo = shutil.which("cargo") or "/usr/bin/cargo"
        cargo_cmd = [cargo, "build", "--release"]
        if (src / "Cargo.lock").is_file():
            cargo_cmd.append("--locked")
        print(f"compiling {spec.name} (cargo; this can take several minutes)")
        rc = _stream(
            cargo_cmd,
            user=uid,
            group=gid,
            cwd=src,
            extra_env=child_env,
        )
        binary = src / "target" / "release" / spec.binary
    else:
        print(f"unknown build kind {spec.kind}", file=sys.stderr)
        return 1
    if rc != 0:
        return rc
    if not binary.is_file():
        print(f"build did not produce {binary}", file=sys.stderr)
        return 1

    dest = Path("/usr/bin") / spec.binary
    install = shutil.which("install") or "/usr/bin/install"
    print(f"installing {binary} -> {dest}")
    rc = _stream([install, "-Dm755", str(binary), str(dest)])
    if rc != 0:
        return rc
    conf = src / "paru.conf"
    if spec.name == "paru" and conf.is_file() and not Path("/etc/paru.conf").exists():
        _stream([install, "-Dm644", str(conf), "/etc/paru.conf"])
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"{spec.binary} installed at {dest}")
    return 0


def _git_bin() -> str:
    return shutil.which("git") or "/usr/bin/git"


def _remote_main_sha() -> str:
    git = _git_bin()
    last = "ls-remote failed"
    for url, allow in ((REPO_HTTPS, "https"), (REPO_SSH, "ssh:https")):
        proc = subprocess.run(
            [git, "ls-remote", "--", url, f"refs/heads/{BRANCH}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PATH": SAFE_PATH, **GIT_PROBE_ENV, "GIT_ALLOW_PROTOCOL": allow},
        )
        if proc.returncode == 0:
            try:
                return parse_ls_remote(proc.stdout or "")
            except UpdateError as exc:
                last = str(exc)
                continue
        err = (proc.stderr or proc.stdout or "ls-remote failed").strip()
        last = err.splitlines()[-1] if err else last
    raise ValueError(last)


def _clone_self(dest: Path) -> int:
    git = _git_bin()
    extra = {**GIT_PROBE_ENV}
    rc = 1
    for url, allow in ((REPO_HTTPS, "https"), (REPO_SSH, "ssh:https")):
        if dest.exists():
            shutil.rmtree(dest)
        print(f"cloning {url} ({BRANCH})")
        extra["GIT_ALLOW_PROTOCOL"] = allow
        rc = _stream(
            [git, "clone", "--depth", "1", "--branch", BRANCH, "--", url, str(dest)],
            extra_env=extra,
        )
        if rc == 0:
            return 0
    return rc


def _self_update() -> int:
    if not shutil.which("git") and _pm() == "pacman":
        pacman = shutil.which("pacman") or "/usr/bin/pacman"
        rc = _stream([pacman, "-S", "--needed", "--noconfirm", "--", "git"])
        if rc != 0:
            return rc
    if not Path(_git_bin()).is_file() and not shutil.which("git"):
        print("git is not installed", file=sys.stderr)
        return 1

    remote = _remote_main_sha()
    local = installed_revision()
    print(f"installed revision: {local or '(none)'}")
    print(f"origin/{BRANCH}: {remote}")
    if local and local == remote:
        print("already on origin/main")
        return 0

    uid, gid, user, home = _invoking_user()
    cache = Path("/var/cache/enigmars-util")
    cache.mkdir(parents=True, exist_ok=True)
    os.chmod(cache, 0o755)
    workdir = cache / "self-update"
    if workdir.exists():
        shutil.rmtree(workdir)
    rc = _clone_self(workdir)
    if rc != 0:
        return rc
    for marker in (
        workdir / "scripts" / "install.sh",
        workdir / "src" / "enigmars_util" / "app.py",
        workdir / "packaging" / "arch" / "PKGBUILD.local",
    ):
        if not marker.is_file():
            print(f"clone missing {marker.name}", file=sys.stderr)
            return 1

    if _pm() == "pacman":
        pacman = shutil.which("pacman") or "/usr/bin/pacman"
        rc = _stream(
            [
                pacman,
                "-S",
                "--needed",
                "--noconfirm",
                "--",
                "git",
                "base-devel",
                "python",
                "pyside6",
                "polkit",
                "qt6-base",
            ]
        )
        if rc != 0:
            return rc
        _chown_tree(workdir, uid, gid)
        archdir = workdir / "packaging" / "arch"
        for old in archdir.glob("enigmars-utils-*.pkg.tar.*"):
            old.unlink()
        makepkg = shutil.which("makepkg") or "/usr/bin/makepkg"
        print("building Arch package (makepkg)")
        rc = _stream(
            [makepkg, "-f", "--noconfirm", "-p", "PKGBUILD.local"],
            user=uid,
            group=gid,
            cwd=archdir,
            extra_env={
                "HOME": home,
                "USER": user,
                "LOGNAME": user,
                "PKGDEST": str(archdir),
            },
        )
        if rc != 0:
            return rc
        pkg = ""
        for f in sorted(archdir.glob("enigmars-utils-*.pkg.tar.zst")):
            pkg = str(f)
            break
        if not pkg:
            print("makepkg did not produce enigmars-utils-*.pkg.tar.zst", file=sys.stderr)
            return 1
        print(f"installing {pkg}")
        rc = _stream([pacman, "-U", "--noconfirm", "--", pkg])
        if rc != 0:
            return rc
    else:
        install = workdir / "scripts" / "install.sh"
        print("installing with scripts/install.sh")
        rc = _stream(["/bin/sh", str(install)])
        if rc != 0:
            return rc

    shutil.rmtree(workdir, ignore_errors=True)
    now = installed_revision()
    print(f"installed revision now: {now or remote}")
    print("restart Enigmars Utils to load the new build")
    return 0


def _atomic_write(path: Path, data: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.enigmars-tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _extras_repo_setup() -> int:
    if _pm() != "pacman":
        print("enigmars-extras requires pacman (Arch / EnigmarsOS).", file=sys.stderr)
        return 1
    if not PACMAN_CONF.is_file():
        print(f"missing {PACMAN_CONF}", file=sys.stderr)
        return 1
    body = EXTRAS_SETUP if EXTRAS_SETUP.endswith("\n") else EXTRAS_SETUP + "\n"
    print(f"writing {EXTRAS_DROPIN}")
    _atomic_write(EXTRAS_DROPIN, body, 0o644)
    original = PACMAN_CONF.read_text(encoding="utf-8")
    updated = with_extras_include(original)
    if updated != original:
        print(f"adding Include to {PACMAN_CONF}")
        _atomic_write(PACMAN_CONF, updated, 0o644)
    else:
        print(f"{PACMAN_CONF} already references enigmars-extras")
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    print("refreshing sync databases (pacman -Sy)")
    return _stream([pacman, "-Sy", "--noconfirm"])


def _chaotic_repo_setup() -> int:
    if _pm() != "pacman":
        print("chaotic-aur requires pacman (Arch / EnigmarsOS).", file=sys.stderr)
        return 1
    if not PACMAN_CONF.is_file():
        print(f"missing {PACMAN_CONF}", file=sys.stderr)
        return 1
    pacman_key = shutil.which("pacman-key") or "/usr/bin/pacman-key"
    if not Path(pacman_key).is_file():
        print("pacman-key is not installed", file=sys.stderr)
        return 1
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    print(f"importing Chaotic-AUR key {CHAOTIC_KEYID} from {CHAOTIC_KEYSERVER}")
    rc = _stream([pacman_key, "--recv-key", CHAOTIC_KEYID, "--keyserver", CHAOTIC_KEYSERVER])
    if rc != 0:
        return rc
    print(f"locally signing Chaotic-AUR key {CHAOTIC_KEYID}")
    rc = _stream([pacman_key, "--lsign-key", CHAOTIC_KEYID])
    if rc != 0:
        return rc
    print("installing chaotic-keyring + chaotic-mirrorlist from the CDN")
    rc = _stream([pacman, "-U", "--noconfirm", "--", CHAOTIC_KEYRING_URL, CHAOTIC_MIRRORLIST_URL])
    if rc != 0:
        return rc
    original = PACMAN_CONF.read_text(encoding="utf-8")
    updated = with_chaotic_include(original)
    if updated != original:
        print(f"adding [chaotic-aur] to {PACMAN_CONF}")
        _atomic_write(PACMAN_CONF, updated, 0o644)
    else:
        print(f"{PACMAN_CONF} already references chaotic-aur")
    print("refreshing sync databases (pacman -Sy)")
    return _stream([pacman, "-Sy", "--noconfirm"])


def _kernel_repo_setup() -> int:
    if _pm() != "pacman":
        print("EnigmarsOS kernel repos require pacman (Arch / EnigmarsOS).", file=sys.stderr)
        return 1
    if not PACMAN_CONF.is_file():
        print(f"missing {PACMAN_CONF}", file=sys.stderr)
        return 1
    for repo in KERNEL_REPOS:
        dropin = KERNEL_DROPINS[repo]
        body = KERNEL_SETUPS[repo]
        if not body.endswith("\n"):
            body += "\n"
        print(f"writing {dropin}")
        _atomic_write(dropin, body, 0o644)
    original = PACMAN_CONF.read_text(encoding="utf-8")
    updated = original
    for repo in KERNEL_REPOS:
        updated = with_kernel_include(updated, repo)
    if updated != original:
        print(f"adding EnigmarsOS kernel Includes to {PACMAN_CONF}")
        _atomic_write(PACMAN_CONF, updated, 0o644)
    else:
        print(f"{PACMAN_CONF} already references the EnigmarsOS kernel repos")
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    print("refreshing sync databases (pacman -Sy)")
    return _stream([pacman, "-Sy", "--noconfirm"])


def _repo_repair_kernel() -> int:
    if _pm() != "pacman":
        print("kernel repo repair requires pacman (Arch / EnigmarsOS).", file=sys.stderr)
        return 1
    if not PACMAN_CONF.is_file():
        print(f"missing {PACMAN_CONF}", file=sys.stderr)
        return 1
    # Fix 1: migrate pacman drop-ins from RishiSpace to enigmars-project.
    # Pre-move installs keep working via redirect, but pacman should track
    # the canonical org URLs.
    print("fix 1/3: migrating pacman Server URLs to enigmars-project")
    migrated = 0
    for conf in ORG_MIGRATION_CONFS:
        if not conf.is_file():
            continue
        try:
            conf_text = conf.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {conf}: {exc}", file=sys.stderr)
            return 1
        if org_migration_needed_in(conf_text):
            print(f"rewriting {conf} to enigmars-project")
            _atomic_write(conf, migrate_org_in_text(conf_text), 0o644)
            migrated += 1
    if not migrated:
        print("pacman Server URLs already on enigmars-project")
    # Fix 2: stop the frozen ISO snapshot from shadowing the rolling repo.
    # Post-install owns /usr/share/enigmarsos/offline-repo itself; the patch
    # only removes the shadowing (never deletes the 230 MB payload).
    print("fix 2/3: removing enigmarsos-offline shadow")
    original = PACMAN_CONF.read_text(encoding="utf-8")
    updated = "".join(
        line for line in original.splitlines(keepends=True) if "enigmarsos-offline.conf" not in line
    )
    if updated != original:
        print(f"removing enigmarsos-offline Include from {PACMAN_CONF}")
        _atomic_write(PACMAN_CONF, updated, 0o644)
    else:
        print(f"{PACMAN_CONF} has no enigmarsos-offline Include")
    try:
        OFFLINE_CONF.unlink()
        print(f"removed {OFFLINE_CONF}")
    except FileNotFoundError:
        print(f"{OFFLINE_CONF} already absent")
    except OSError as exc:
        print(f"cannot remove {OFFLINE_CONF}: {exc}", file=sys.stderr)
        return 1
    # Fix 3: track the stable `lts` tag for linux-enigmarsos-lts. Pinned
    # release URLs freeze LTS updates at that release; the release workflow
    # retargets `lts` on every LTS release so one stable URL keeps flowing.
    print("fix 3/3: tracking the stable lts tag for linux-enigmarsos-lts")
    if not LTS_CONF.is_file():
        print(f"missing {LTS_CONF} — enable the kernel repos first", file=sys.stderr)
        return 1
    conf_text = LTS_CONF.read_text(encoding="utf-8")
    if not lts_tracks_in(conf_text):
        old_tag = lts_pinned_tag(conf_text)
        print(
            "rewriting LTS Server to releases/download/lts"
            + (f" (was pinned to {old_tag})" if old_tag else "")
        )
        _atomic_write(LTS_CONF, retrack_lts_in_text(conf_text), 0o644)
    else:
        print(f"{LTS_CONF} already tracks the stable lts tag")
    pacman = shutil.which("pacman") or "/usr/bin/pacman"
    print("refreshing sync databases (pacman -Sy)")
    rc = _stream([pacman, "-Sy", "--noconfirm"])
    if rc != 0:
        return rc
    print("receipt: which repo each kernel resolves from")
    proc = subprocess.run(
        [pacman, "-Si", "--", "linux-enigmarsos", "linux-enigmarsos-lts"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": SAFE_PATH},
        timeout=60,
    )
    for line in (proc.stdout or "").splitlines():
        if line.startswith("Repository") or line.startswith("Version"):
            print(f"    {line.strip()}")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "pacman -Si failed").strip()
        print(err.splitlines()[-1] if err else "pacman -Si failed", file=sys.stderr)
        return 1
    return 0


# Fixed upstream sources for the ESP-sync hook (pre-2026-07-09 ISOs lack them).
ESP_SYNC_SCRIPT_URL = (
    "https://raw.githubusercontent.com/RishiSpace/EnigmarsOS/main"
    "/scripts/install/sync-esp-boot.sh"
)
ESP_HOOK_URL = (
    "https://raw.githubusercontent.com/RishiSpace/EnigmarsOS/main"
    "/archiso/airootfs/usr/share/libalpm/hooks/90-enigmarsos-sync-esp.hook"
)
ESP_HOOK_SCRIPT_URL = (
    "https://raw.githubusercontent.com/RishiSpace/EnigmarsOS/main"
    "/archiso/airootfs/usr/share/libalpm/scripts/enigmarsos-sync-esp"
)

_ESP_REPAIR_BASE = Path("/run/enigmars-esp-repair")


def _blkid_fstype(dev: str) -> str | None:
    blkid = shutil.which("blkid") or "/usr/sbin/blkid"
    try:
        proc = subprocess.run(
            [blkid, "-s", "TYPE", "-o", "value", "--", dev],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "PATH": SAFE_PATH},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip().lower() or None


def _mounted_devices() -> set[str]:
    mounted: set[str] = set()
    try:
        text = Path("/proc/mounts").read_text(encoding="utf-8")
    except OSError:
        return mounted
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            mounted.add(os.path.realpath(fields[0]))
        except OSError:
            continue
    return mounted


def _check_repair_device(dev: str, *, want: tuple[str, ...], role: str) -> str:
    """Validate a repair target device; return its real path or raise."""
    validate_device(dev)
    real = os.path.realpath(dev)
    try:
        st = os.stat(real)
    except OSError as exc:
        raise ValueError(f"{role} device not found: {dev}") from exc
    import stat as statmod

    if not statmod.S_ISBLK(st.st_mode):
        raise ValueError(f"{role} is not a block device: {dev}")
    if real in _mounted_devices():
        raise ValueError(f"{role} {dev} is already mounted; unmount it first")
    fstype = _blkid_fstype(real)
    if fstype not in want:
        raise ValueError(f"{role} {dev} has fstype {fstype or 'unknown'}, want {want}")
    return real


def _mount(args: list[str], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    mount = shutil.which("mount") or "/usr/bin/mount"
    proc = subprocess.run(
        [mount, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": SAFE_PATH},
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "mount failed").strip().splitlines()
        raise ValueError(f"mount failed: {err[-1] if err else 'mount failed'}")


def _umount_all(base: Path) -> None:
    umount = shutil.which("umount") or "/usr/bin/umount"
    try:
        subprocess.run(
            [umount, "-R", str(base)],
            check=False,
            capture_output=True,
            timeout=60,
            env={**os.environ, "PATH": SAFE_PATH},
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _curl_to(url: str, dest: Path, *, marker: str) -> None:
    curl = shutil.which("curl") or "/usr/bin/curl"
    if not Path(curl).is_file():
        raise ValueError("curl is not installed (needed to fetch the ESP hook)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [curl, "-fsSL", "--proto", "=https", "--max-time", "60", "--", url, "-o", str(dest)],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
        env={**os.environ, "PATH": SAFE_PATH},
    )
    if proc.returncode != 0:
        raise ValueError(f"download failed: {url}")
    try:
        body = dest.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read download: {exc}") from exc
    if marker not in body:
        raise ValueError(f"downloaded file failed sanity check: {url}")
    os.chmod(dest, 0o644)


def _esp_repair(esp: str, root: str) -> int:
    if _pm() != "pacman":
        print("ESP repair requires pacman (run from an Arch live USB).", file=sys.stderr)
        return 1
    arch_chroot = shutil.which("arch-chroot") or "/usr/bin/arch-chroot"
    if not Path(arch_chroot).is_file():
        print("arch-chroot is not installed (run from an Arch live USB).", file=sys.stderr)
        return 1
    try:
        esp_dev = _check_repair_device(esp, want=("vfat",), role="ESP")
        root_dev = _check_repair_device(root, want=ROOT_FSTYPES, role="root")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    mnt = _ESP_REPAIR_BASE / "mnt"
    if mnt.exists():
        print(f"{mnt} already exists; another repair may be running", file=sys.stderr)
        return 1
    try:
        root_fs = _blkid_fstype(root_dev) or ""
        print(f"mounting root {root_dev} ({root_fs})")
        if root_fs == "btrfs":
            mounted = False
            for opts in ("subvol=/@", "subvol=@"):
                try:
                    _mount(["-o", opts, "--", root_dev, str(mnt)], mnt)
                    mounted = True
                    print(f"mounted with {opts}")
                    break
                except ValueError:
                    continue
            if not mounted:
                print("probing btrfs subvolumes")
                _mount(["-o", "subvolid=5", "--", root_dev, str(mnt)], mnt)
                try:
                    btrfs = shutil.which("btrfs") or "/usr/bin/btrfs"
                    proc = subprocess.run(
                        [btrfs, "subvolume", "list", str(mnt)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env={**os.environ, "PATH": SAFE_PATH},
                    )
                    subvols = parse_subvolumes(proc.stdout or "")
                finally:
                    _umount_all(mnt)
                print(f"found subvolumes: {', '.join(subvols) or '(none)'}")
                if "@" not in subvols:
                    print("no @ subvolume; mount the system root manually", file=sys.stderr)
                    return 1
                _mount(["-o", "subvol=/@", "--", root_dev, str(mnt)], mnt)
        else:
            _mount(["--", root_dev, str(mnt)], mnt)
        if not (mnt / "etc").is_dir() or not (mnt / "usr").is_dir():
            print("etc/ or usr/ missing: this is not the system root", file=sys.stderr)
            return 1
        print("root verified (etc + usr present)")
        try:
            print((mnt / "etc" / "os-release").read_text(encoding="utf-8").splitlines()[0])
        except OSError:
            pass
        efi = mnt / "boot" / "efi"
        print(f"mounting ESP {esp_dev} at /boot/efi")
        _mount(["--", esp_dev, str(efi)], efi)
        if not (efi / "EFI").is_dir():
            print("warning: no EFI/ dir on the ESP; continuing", file=sys.stderr)
        print("installing ESP sync hook into the target system")
        _curl_to(ESP_SYNC_SCRIPT_URL, mnt / "usr/share/enigmarsos/scripts/sync-esp-boot.sh",
                 marker="sync-esp-boot")
        _curl_to(ESP_HOOK_URL, mnt / "usr/share/libalpm/hooks/90-enigmarsos-sync-esp.hook",
                 marker="[Trigger]")
        _curl_to(ESP_HOOK_SCRIPT_URL, mnt / "usr/share/libalpm/scripts/enigmarsos-sync-esp",
                 marker="#!")
        os.chmod(mnt / "usr/share/enigmarsos/scripts/sync-esp-boot.sh", 0o755)
        os.chmod(mnt / "usr/share/libalpm/scripts/enigmarsos-sync-esp", 0o755)
        pacman = shutil.which("pacman") or "/usr/bin/pacman"
        print("updating target system kernel (pacman -Syu linux)")
        rc = _stream([arch_chroot, str(mnt), pacman, "-Syu", "--noconfirm", "--", "linux"])
        if rc != 0:
            return rc
        print("staging current kernel onto the ESP")
        return _stream([arch_chroot, str(mnt), "/bin/bash",
                        "/usr/share/enigmarsos/scripts/sync-esp-boot.sh"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        _umount_all(mnt)
        try:
            shutil.rmtree(_ESP_REPAIR_BASE, ignore_errors=True)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    _harden()
    if not argv:
        return _die("usage: enigmars-util-helper <verb> [args]", 2)
    try:
        verb = validate_verb(argv[0])
        extra = argv[1:]
        if verb in {"pkg-install", "pkg-remove"}:
            extra = validate_package_list(extra)
        elif verb in {"service-enable", "service-disable"}:
            if len(extra) != 1:
                raise ValueError("service name required")
            extra = [validate_service(extra[0])]
        elif verb == "aur-helper-setup":
            if len(extra) != 1:
                raise ValueError("aur-helper-setup accepts exactly one of: yay, paru")
            extra = [validate_aur_helper(extra[0])]
        elif extra:
            raise ValueError("unexpected arguments")
    except ValueError as exc:
        return _die(str(exc), 2)
    if os.geteuid() != 0:
        return _die("helper must run as root via pkexec", 2)
    rc = 0
    detail = verb
    try:
        if verb in {"pkg-install", "pkg-remove"}:
            names = validate_package_list(extra)
            detail = f"{verb} {' '.join(names)}"
            action = "install" if verb == "pkg-install" else "remove"
            rc = _stream(_pkg_cmd(action, names))
            if rc == 0:
                rc = _maybe_sync_esp(names)
        elif verb in {"pkg-update", "pkg-refresh"}:
            action = "update" if verb == "pkg-update" else "refresh"
            rc = _stream(_pkg_cmd(action, []))
            if rc == 0 and verb == "pkg-update" and _is_enigmars():
                rc = _sync_esp()
        elif verb == "kernel-sync-esp":
            rc = _sync_esp()
        elif verb == "ufw-enable":
            ufw = shutil.which("ufw") or "/usr/sbin/ufw"
            rc = _stream([ufw, "--force", "enable"])
        elif verb == "ufw-disable":
            ufw = shutil.which("ufw") or "/usr/sbin/ufw"
            rc = _stream([ufw, "disable"])
        elif verb in {"service-enable", "service-disable"}:
            if len(extra) != 1:
                raise ValueError("service name required")
            name = validate_service(extra[0])
            detail = f"{verb} {name}"
            systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
            action = "enable" if verb == "service-enable" else "disable"
            rc = _stream([systemctl, action, "--now", "--", name])
        elif verb == "sbctl-enroll":
            rc = _sbctl_enroll()
        elif verb == "firmware-reboot":
            systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
            print("Rebooting into firmware setup…")
            rc = _stream([systemctl, "reboot", "--firmware-setup"])
        elif verb == "aur-helper-setup":
            name = validate_aur_helper(extra[0])
            detail = f"{verb} {name}"
            rc = _setup_aur_helper(name)
        elif verb == "self-update":
            rc = _self_update()
        elif verb == "extras-repo-setup":
            rc = _extras_repo_setup()
        elif verb == "chaotic-repo-setup":
            rc = _chaotic_repo_setup()
        elif verb == "kernel-repo-setup":
            rc = _kernel_repo_setup()
        elif verb == "repo-repair-kernel":
            rc = _repo_repair_kernel()
        elif verb == "esp-repair":
            if len(extra) != 2:
                raise ValueError("esp-repair needs ESP and root partitions")
            esp = validate_device(extra[0])
            root = validate_device(extra[1])
            if esp == root:
                raise ValueError("ESP and root must be different partitions")
            detail = f"{verb} {esp} {root}"
            rc = _esp_repair(esp, root)
        else:
            raise ValueError(f"unhandled verb {verb}")
    except ValueError as exc:
        _syslog(verb, str(exc), False)
        return _die(str(exc), 2)
    except OSError as exc:
        _syslog(verb, str(exc), False)
        return _die(str(exc), 1)

    ok = rc == 0
    _syslog(verb, detail, ok)
    _result(ok, detail if ok else f"{detail} rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
