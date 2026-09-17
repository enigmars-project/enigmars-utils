# Enigmars Util

Qt landing hub for Linux. Detects the distro, desktop, and package manager, then
offers Windows-convert tweaks, package actions, and kernel management.

Version **1.1.2**. EnigmarsOS is first-class (Plasma 6, pacman, Limine, ESP
kernel staging). The same binary works on other families by probing the host.

The GUI never runs as root. Package, kernel, and firewall changes go through
`pkexec /usr/libexec/enigmars-util-helper`.

## Run from a checkout (UI only)

```bash
make run
make test
```

Privileged buttons need the helper installed.

## Packages (.deb and Arch/AUR)

```bash
make deb        # dist/enigmars-utils_*.deb
make rpm        # dist/enigmars-utils-*.noarch.rpm
make appimage   # dist/Enigmars_Utils-*-x86_64.AppImage
make pkg-arch   # packaging/arch/enigmars-utils-*.pkg.tar.zst
```

Pushes to `main` also build `.deb`, `.rpm`, and `.AppImage` on GitHub Actions
and attach them to the **Latest** release. See [docs/PACKAGING.md](docs/PACKAGING.md).

## Install (Arch / EnigmarsOS)

On EnigmarsOS, clone, build, and install in one step:

```bash
curl -fsSL https://enigmarsos.rishispace.dev/utils | sh
```

From this repo:

```bash
sudo ./scripts/install.sh
# or
cd packaging/arch && makepkg -si -p PKGBUILD.local
```

Then launch **Enigmars Util** from the app menu, or `enigmars-util`.

## Enigmars Packages

If pacman has the `[enigmars-extras]` repo (see
[enigmars-extras](https://github.com/enigmars-project/enigmars-extras)), the
**Enigmars Pkgs** tab lists packages from that repo that are not installed
and can install selected ones or all of them. If the repo is missing, **Add
repo and refresh** writes `/etc/pacman.d/enigmars-extras.conf`, Includes it
from `pacman.conf`, and runs `pacman -Sy`.

Enable “Show on login” on the Home page if you want it as a welcome screen.
This package does not force autostart.

On EnigmarsOS, point `enigmarsos-welcome` at `enigmars-util` (wrapper or
`Depends: enigmars-util`).

## Security

- No `shell=True`
- Package names validated before they reach the helper
- Catalogs cannot run shell
- Helper refuses non-root, unknown verbs, and extra arguments
- yay/paru setup is allowlisted (`aur-helper-setup yay|paru`); no general AUR
- Self-update clones the hardcoded GitHub URL on `main` only (`self-update`)
- EnigmarsOS kernel install/remove restages the ESP via `sync-esp-boot.sh`
