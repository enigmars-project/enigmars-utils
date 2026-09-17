# Architecture

Enigmars Util is an unprivileged PySide6 app plus a tiny pkexec helper.

## Layers

1. **Probe** (`probe.py`) — read-only `HostProfile` from os-release, XDG, PM databases.
2. **Services** — tweaks, packages, kernels. Queries are unprivileged.
3. **Helper client** (`privileged.py`) — builds `pkexec` argv.
4. **UI** — pages bound to a probed profile.

Family is chosen from `ID` then `ID_LIKE`, then the native package manager is
**confirmed** with binary + database (pacman does not win on Ubuntu just because
it is on `$PATH`).

## Privileged path

`/usr/libexec/enigmars-util-helper <verb> [args]`

Verbs: `pkg-install`, `pkg-remove`, `pkg-update`, `pkg-refresh`,
`kernel-sync-esp`, `ufw-enable`, `ufw-disable`, `service-enable`,
`service-disable` (services: `ufw`, `docker.socket`, `libvirtd` only),
`sbctl-enroll` (create keys if needed, `enroll-keys -m`, sign ESP/boot
kernels), `firmware-reboot` (`systemctl reboot --firmware-setup`),
`aur-helper-setup` (`yay` or `paru` only: pacman if the name is in the
sync db, otherwise clone the upstream GitHub tree and compile as the
pkexec caller, then install `/usr/bin/{yay,paru}`),
`self-update` (compare `/usr/share/enigmars-util/revision` to
`origin/main` on `enigmars-project/enigmars-utils`, clone, `makepkg` on
pacman or `scripts/install.sh` otherwise).

`--page enigmars-packages` lists uninstalled packages from the
`enigmars-extras` pacman repo. If the repo is missing, **Add repo and
refresh** writes the drop-in (`extras-repo-setup`) and runs `pacman -Sy`.
Installs go through `pkg-install`.

`--page secure-boot` (and a one-shot autostart after a firmware reboot)
opens the Secure Boot tab so Setup Mode enrollment can continue after login.

On EnigmarsOS, installing, removing, or updating `linux*` packages runs
`/usr/share/enigmarsos/scripts/sync-esp-boot.sh`. The Qt app does not rewrite
`limine.conf`. Kernel flavors that are neither installed nor in the native
repos are hidden.

## Catalogs

TOML under `data/tweaks`, `data/catalog`, `data/kernels`. Adding a tweak or
kernel flavor is data, not a new widget.

## Non-goals (v1)

General AUR browsing, custom kernel builds, GNOME extensions from the web,
running the GUI as root, Flatpak of this app. `yay`/`paru` bootstrap is
allowlisted and does not execute a downloaded PKGBUILD.

See the implementation plan in the repository session if present; this file is
the in-tree contract.
