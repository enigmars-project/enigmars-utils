from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from enigmars_util.esp_repair import (
    describe,
    esp_candidates,
    list_partitions,
    root_candidates,
)
from enigmars_util.patches import (
    LTS_CONF,
    KernelRepoPatchStatus,
    lts_pinned_tag,
    probe_kernel_repo_patch,
    probe_org_migration,
)
from enigmars_util.privileged import esp_repair_cmd, kernel_repo_repair_cmd
from enigmars_util.profile import HostProfile
from enigmars_util.ui.jobs import Work
from enigmars_util.ui.widgets import Card, JobPane, button, confirm, warn


def _read_lts_conf() -> str:
    try:
        return LTS_CONF.read_text(encoding="utf-8")
    except OSError:
        return ""


class PatchesPage(QWidget):
    """One-click repair patches. Patch #1 fixes the kernel repos; future
    one-click fixes stack below it as new cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: HostProfile | None = None
        self._patch_work: Work | None = None
        self._patch_gen = 0
        self._show_update_hint = False
        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Patches")
        title.setObjectName("cardTitle")
        root.addWidget(title)
        subtitle = QLabel("One-click fixes for known issues. Each patch probes first and only acts when needed.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self._patch1_card = Card(
            "Kernel repository repair (Sept 2026)",
            "Repairs the EnigmarsOS kernel repos: migrates pacman Server URLs "
            "from RishiSpace to enigmars-project, removes the frozen ISO snapshot "
            "shadow and tracks the LTS download via the stable lts tag.",
        )
        patch_row = QHBoxLayout()
        patch_row.setContentsMargins(0, 4, 0, 4)
        self.patch_status = QLabel("Checking kernel repositories…")
        self.patch_status.setObjectName("muted")
        self.patch_status.setWordWrap(True)
        patch_row.addWidget(self.patch_status, 1)
        self.patch_btn = button("Apply kernel repo fixes", self._apply_kernel_patch)
        self.patch_btn.setToolTip("Remove the offline shadow, track the lts tag, and refresh databases in one step")
        patch_row.addWidget(self.patch_btn)
        self._patch1_card.body.addLayout(patch_row)
        root.addWidget(self._patch1_card)

        self._esp_card = Card(
            "ESP kernel staging repair (ISOs before 07-09-2026)",
            "Only for systems installed from an ISO older than 07-09-2026: "
            "those lack the ESP sync hook, so kernel updates never reach the "
            "ESP. Pick the installed system's ESP and root partitions below "
            "(usually from a live USB), then apply. Newer installs do not "
            "need this.",
        )
        pick_row = QHBoxLayout()
        pick_row.setContentsMargins(0, 4, 0, 4)
        self.esp_combo = QComboBox()
        self.esp_combo.setToolTip("vfat partition holding EFI/")
        self.esp_combo.currentIndexChanged.connect(self._esp_selection_changed)
        self.root_combo = QComboBox()
        self.root_combo.setToolTip("btrfs / ext4 / xfs partition holding the system root")
        self.root_combo.currentIndexChanged.connect(self._esp_selection_changed)
        pick_row.addWidget(QLabel("ESP:"))
        pick_row.addWidget(self.esp_combo, 1)
        pick_row.addWidget(QLabel("Root:"))
        pick_row.addWidget(self.root_combo, 1)
        pick_row.addWidget(button("Rescan", self._esp_rescan))
        self._esp_card.body.addLayout(pick_row)
        self.esp_status = QLabel("Select the ESP and root partitions of the system to repair.")
        self.esp_status.setObjectName("muted")
        self.esp_status.setWordWrap(True)
        self._esp_card.body.addWidget(self.esp_status)
        apply_row = QHBoxLayout()
        apply_row.setContentsMargins(0, 4, 0, 4)
        apply_row.addStretch()
        self.esp_btn = button("Repair ESP staging", self._apply_esp_patch)
        self.esp_btn.setToolTip("Mount, reinstall kernel, install ESP hook, stage to ESP")
        self.esp_btn.setEnabled(False)
        apply_row.addWidget(self.esp_btn)
        self._esp_card.body.addLayout(apply_row)
        root.addWidget(self._esp_card)
        root.addStretch(1)

        self.job = JobPane()
        self.job.finished.connect(self._job_done)
        root.addWidget(self.job)

    def set_profile(self, profile: HostProfile) -> None:
        self._profile = profile
        self._patch1_card.setVisible(profile.native_pm == "pacman")
        self._esp_card.setVisible(profile.native_pm == "pacman")
        self._refresh_patch()
        self._esp_rescan()

    def _refresh_patch(self) -> None:
        self._patch_gen += 1
        gen = self._patch_gen
        profile = self._profile
        if profile is None or profile.native_pm != "pacman":
            self.patch_status.setText("Kernel repo patches need pacman (EnigmarsOS / Arch).")
            self.patch_btn.setEnabled(False)
            return
        self.patch_status.setText("Checking kernel repositories…")
        self.patch_btn.setEnabled(False)

        def work() -> tuple[KernelRepoPatchStatus | Exception, tuple[str, ...]]:
            try:
                status = probe_kernel_repo_patch()
            except Exception as exc:  # noqa: BLE001
                return exc, ()
            try:
                org = probe_org_migration()
            except Exception:  # noqa: BLE001
                org = None
            pending = tuple(org.pending) if org is not None else ()
            return status, pending

        thread = Work(work, self)
        self._patch_work = thread

        def done(obj: object) -> None:
            if gen != self._patch_gen:
                return
            mutate = bool(profile.can_mutate_native)
            if isinstance(obj, Exception):
                self.patch_status.setText(f"Could not check kernel repositories: {obj}")
                self.patch_btn.setEnabled(mutate)
                self._show_update_hint = False
                return
            if not isinstance(obj, tuple) or len(obj) != 2:
                return
            status, pending = obj
            if isinstance(status, Exception):
                self.patch_status.setText(f"Could not check kernel repositories: {status}")
                self.patch_btn.setEnabled(mutate)
                self._show_update_hint = False
                return
            if not isinstance(status, KernelRepoPatchStatus):
                return
            if status.on_live_iso:
                self.patch_status.setText(
                    "Live ISO detected — the frozen snapshot is legitimate here; no patch needed."
                )
                self.patch_btn.setEnabled(False)
            elif not status.needs_patch and not pending:
                text = "Repositories healthy — rolling tracks Latest, LTS tracks lts."
                if self._show_update_hint:
                    text += " Tip: Packages → Update system for a full refresh (pacman -Syyu)."
                self.patch_status.setText(text)
                self.patch_btn.setText("Apply kernel repo fixes")
                self.patch_btn.setEnabled(False)
            else:
                issues = []
                if pending:
                    issues.append(
                        f"pacman Server URLs still point at RishiSpace ({len(pending)} file(s)) — migrate to enigmars-project"
                    )
                if status.offline_shadows:
                    issues.append("frozen offline snapshot shadows the rolling kernel (pins kernel forever)")
                if status.lts_not_tracking:
                    pinned = lts_pinned_tag(_read_lts_conf())
                    if pinned:
                        issues.append(
                            f"LTS Server is pinned to {pinned} instead of tracking lts (freezes updates)"
                        )
                    else:
                        issues.append("LTS Server does not track the stable lts tag")
                self.patch_status.setText("Issues found:\n• " + "\n• ".join(issues))
                self.patch_btn.setText("Apply kernel repo fixes")
                self.patch_btn.setEnabled(mutate)
            self._show_update_hint = False

        thread.result.connect(done)
        thread.start()

    def _apply_kernel_patch(self) -> None:
        if not self._profile or self._profile.native_pm != "pacman":
            warn(self, "Kernel repo repair", "Kernel repo patches need pacman.")
            return
        if not self._profile.can_mutate_native:
            warn(self, "Kernel repo repair", "Package changes are not available on this system.")
            return
        body = (
            "Apply kernel repository fixes in one step?\n\n"
            "1. Migrate pacman Server URLs from RishiSpace to enigmars-project — "
            "pre-move installs keep tracking releases after the org transfer.\n"
            "2. Remove the enigmarsos-offline shadow — the frozen ISO snapshot "
            "pins your kernel forever instead of tracking rolling releases.\n"
            "3. Point the LTS Server URL at the stable lts tag — a pinned "
            "release URL freezes your LTS kernel at that release.\n\n"
            "Then refresh databases (pacman -Sy) and print which repo each "
            "kernel resolves from. No reboot needed — repo changes need none."
        )
        if not confirm(self, "Apply kernel repo fixes", body):
            return
        try:
            self.job.run(kernel_repo_repair_cmd(), "repo-repair-kernel")
        except FileNotFoundError as exc:
            warn(self, "Helper", str(exc))

    def _job_done(self, ok: bool) -> None:
        self._show_update_hint = ok
        self._refresh_patch()

    def _esp_rescan(self) -> None:
        parts = list_partitions()
        esps = esp_candidates(parts)
        roots = root_candidates(parts)
        self.esp_combo.blockSignals(True)
        self.root_combo.blockSignals(True)
        self.esp_combo.clear()
        for part in esps:
            self.esp_combo.addItem(describe(part), part.path)
        self.root_combo.clear()
        for part in roots:
            self.root_combo.addItem(describe(part), part.path)
        self.esp_combo.blockSignals(False)
        self.root_combo.blockSignals(False)
        if not esps or not roots:
            self.esp_status.setText(
                "No candidate partitions found (need a vfat ESP and a "
                "btrfs/ext4/xfs root). Run from a live USB with the target "
                "disk attached."
            )
        self._esp_selection_changed()

    def _esp_selected(self) -> tuple[str, str]:
        esp = self.esp_combo.currentData() or ""
        root = self.root_combo.currentData() or ""
        return str(esp), str(root)

    def _esp_selection_changed(self) -> None:
        esp, root = self._esp_selected()
        mutate = bool(self._profile and self._profile.can_mutate_native)
        ok = bool(esp and root and esp != root)
        self.esp_btn.setEnabled(ok and mutate)
        if esp and root and esp == root:
            self.esp_status.setText("ESP and root must be different partitions.")
        elif ok:
            self.esp_status.setText(f"Will repair:\n• ESP: {esp}\n• Root: {root}")
        elif not mutate and self._profile is not None:
            self.esp_status.setText("Package changes are not available on this system.")

    def _apply_esp_patch(self) -> None:
        esp, root = self._esp_selected()
        if not esp or not root or esp == root:
            warn(self, "ESP repair", "Pick distinct ESP and root partitions first.")
            return
        if not self._profile or self._profile.native_pm != "pacman":
            warn(self, "ESP repair", "ESP repair needs pacman (Arch live USB).")
            return
        body = (
            f"Repair kernel staging on another install?\n\n"
            f"• ESP: {esp}\n"
            f"• Root: {root}\n\n"
            "This mounts both partitions, reinstalls the kernel inside the "
            "target system, installs the ESP sync hook, and stages the "
            "kernel onto the ESP. Double-check the partitions — the wrong "
            "disk means the wrong system gets modified."
        )
        if not confirm(self, "Repair ESP staging", body):
            return
        try:
            self.job.run(esp_repair_cmd(esp, root), "esp-repair")
        except (FileNotFoundError, ValueError) as exc:
            warn(self, "Helper", str(exc))
