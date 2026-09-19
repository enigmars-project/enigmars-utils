# Changelog

## 1.3.0

- Patches: separate ESP kernel staging repair card (ISOs before 07-09-2026) with interactive ESP/root partition pickers; new `esp-repair` helper verb mounts the target, reinstalls the kernel, installs the ESP sync hook, and stages to the ESP

## 1.2.0

- Secure Boot page: sbctl install/enrollment/enabled/Setup Mode status, firmware reboot with instructions, resume into the Secure Boot tab after login, enroll keys including Microsoft (`sbctl enroll-keys -m`)
- Packages page: Set up yay / Set up paru (pacman if present, otherwise clone+compile upstream GitHub)
- Self-update: check origin/main, then recompile and reinstall via pkexec when HEAD has moved
- Enigmars Packages: if the enigmars-extras pacman repo is configured, list packages that are not installed and install selected or all; if missing, add the repo and `pacman -Sy`
- Patches page: one-click fixes, starting with kernel repository repair (migrate Server URLs to enigmars-project, remove enigmarsos-offline shadow, track the stable lts tag) via a single `repo-repair-kernel` privileged call
- Fun page: Cat Mode meows on in-app tab switches, on login (`--meow-login` autostart fallback), and natively on Plasma via KDE Login/Logout event sounds (`data/sounds/meow-login.oga`, `meow-logout.oga`); no listeners or overlays — Start Menu clicks and window switches are deliberately out of scope on Wayland

## 1.0.0

First production release of Enigmars Util.

- Host probe: distro, desktop, family-first package manager, bootloader, GPU, firewall
- Tweaks with preview/confirm/undo, including a Windows-convert pack
- Package catalog, search, install/remove, system update via pkexec helper
- Kernel inventory (installed + repo-available), install/remove with safety checks
- EnigmarsOS kernel transactions restage the ESP on install **and** remove
- Drivers page with NVIDIA install when an NVIDIA GPU is present
- GUI never runs as root
