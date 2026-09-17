from __future__ import annotations

import tomllib
import webbrowser

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from enigmars_util import __version__
from enigmars_util.paths import data_root
from enigmars_util.privileged import self_update_cmd
from enigmars_util.profile import HostProfile
from enigmars_util.self_update import (
    UpdateStatus,
    check_for_update,
    local_revision,
    short_sha,
)
from enigmars_util.ui.jobs import Work
from enigmars_util.ui.widgets import Card, JobPane, button, confirm, info, warn


def _links(enigmarsos: bool) -> dict[str, str]:
    name = "enigmarsos.toml" if enigmarsos else "generic.toml"
    path = data_root() / "branding" / name
    if not path.is_file():
        return {
            "Documentation": "https://enigmarsos.rishispace.dev/docs",
            "Website": "https://enigmarsos.rishispace.dev",
            "GitHub": "https://github.com/enigmars-project/enigmars-utils",
        }
    with path.open("rb") as fh:
        doc = tomllib.load(fh)
    links = doc.get("links") or {}
    out = {str(k): str(v) for k, v in links.items()}
    out.setdefault("Utils source", "https://github.com/enigmars-project/enigmars-utils")
    return out


class AboutPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: HostProfile | None = None
        self._status: UpdateStatus | None = None
        self._check_work: Work | None = None
        root = QVBoxLayout(self)

        self._card = Card("About", "")
        self.summary = QLabel("Enigmars Utils")
        self.summary.setWordWrap(True)
        self.update_label = QLabel("Checking origin/main…")
        self.update_label.setObjectName("muted")
        self.update_label.setWordWrap(True)
        self._card.body.addWidget(self.summary)
        self._card.body.addWidget(self.update_label)
        row = QHBoxLayout()
        self.check_btn = button("Check for updates", self._check)
        self.update_btn = button("Install update", self._install)
        self.update_btn.setEnabled(False)
        row.addWidget(self.check_btn)
        row.addWidget(self.update_btn)
        self._card.body.addLayout(row)
        self._links_host = QWidget()
        self._links_layout = QVBoxLayout(self._links_host)
        self._links_layout.setContentsMargins(0, 0, 0, 0)
        self._card.body.addWidget(self._links_host)
        root.addWidget(self._card)

        self.job = JobPane()
        self.job.finished.connect(self._job_done)
        root.addWidget(self.job)
        root.addStretch()

    def set_profile(self, profile: HostProfile) -> None:
        self._profile = profile
        local = short_sha(local_revision())
        self.summary.setText(
            f"{profile.pretty_name}\nEnigmars Utils {__version__} ({local})\nNo telemetry."
        )
        while self._links_layout.count():
            item = self._links_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for label, url in _links(profile.enigmarsos).items():
            self._links_layout.addWidget(button(f"Open {label}", lambda u=url: webbrowser.open(u)))

    def set_update_status(self, status: UpdateStatus) -> None:
        self._status = status
        local = short_sha(status.local)
        remote = short_sha(status.remote)
        if status.available:
            self.update_label.setText(
                f"Update available: {local} → origin/main {remote}. {status.detail}"
            )
            self.update_btn.setEnabled(True)
        else:
            self.update_label.setText(f"Up to date on origin/main ({remote}). {status.detail}")
            self.update_btn.setEnabled(False)

    def set_update_error(self, message: str) -> None:
        self.update_label.setText(f"Could not check origin/main: {message}")
        self.update_btn.setEnabled(False)

    def _check(self) -> None:
        self.update_label.setText("Checking origin/main…")
        self.check_btn.setEnabled(False)

        def work() -> UpdateStatus | Exception:
            try:
                return check_for_update()
            except Exception as exc:  # noqa: BLE001
                return exc

        thread = Work(work, self)
        self._check_work = thread

        def done(obj: object) -> None:
            self.check_btn.setEnabled(True)
            if isinstance(obj, UpdateStatus):
                self.set_update_status(obj)
                return
            if isinstance(obj, Exception):
                self.set_update_error(str(obj))
                warn(self, "Update check", str(obj))

        thread.result.connect(done)
        thread.start()

    def _install(self) -> None:
        status = self._status
        if status is None or not status.available:
            warn(self, "Update", "No update available. Check origin/main first.")
            return
        body = (
            f"Installed: {short_sha(status.local)}\n"
            f"origin/main: {short_sha(status.remote)}\n\n"
            "Clone main, compile, and reinstall Enigmars Utils? "
            "Restart the app after it finishes."
        )
        if not confirm(self, "Update Enigmars Utils", body):
            return
        try:
            self.job.run(self_update_cmd(), "self-update")
        except FileNotFoundError as exc:
            warn(self, "Helper", str(exc))

    def _job_done(self, ok: bool) -> None:
        if ok:
            info(
                self,
                "Update",
                "Enigmars Utils was reinstalled. Restart the app to load the new build.",
            )
            self._check()
        else:
            warn(self, "Update", "Self-update failed. See the log above.")
