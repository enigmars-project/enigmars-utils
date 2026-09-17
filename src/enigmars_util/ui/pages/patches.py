from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from enigmars_util.patches import (
    LTS_CONF,
    KernelRepoPatchStatus,
    lts_pinned_tag,
    probe_kernel_repo_patch,
    probe_org_migration,
)
from enigmars_util.privileged import kernel_repo_repair_cmd
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
            "shadow and pins the LTS download URL to a real release.",
        )
        patch_row = QHBoxLayout()
        patch_row.setContentsMargins(0, 4, 0, 4)
        self.patch_status = QLabel("Checking kernel repositories…")
        self.patch_status.setObjectName("muted")
        self.patch_status.setWordWrap(True)
        patch_row.addWidget(self.patch_status, 1)
        self.patch_btn = button("Apply kernel repo fixes", self._apply_kernel_patch)
        self.patch_btn.setToolTip("Remove the offline shadow, pin the LTS URL, and refresh databases in one step")
        patch_row.addWidget(self.patch_btn)
        self._patch1_card.body.addLayout(patch_row)
        root.addWidget(self._patch1_card)
        root.addStretch(1)

        self.job = JobPane()
        self.job.finished.connect(self._job_done)
        root.addWidget(self.job)

    def set_profile(self, profile: HostProfile) -> None:
        self._profile = profile
        self._patch1_card.setVisible(profile.native_pm == "pacman")
        self._refresh_patch()

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
                tag = lts_pinned_tag(_read_lts_conf())
                text = "Repositories healthy — rolling tracks Latest"
                text += f", LTS tracks {tag}." if tag else "."
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
                if status.lts_unpinned:
                    issues.append("LTS Server is an unpinned placeholder URL (does not resolve)")
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
            "3. Pin the LTS Server URL to a real release tag — the "
            "releases/download/lts placeholder does not resolve.\n\n"
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
