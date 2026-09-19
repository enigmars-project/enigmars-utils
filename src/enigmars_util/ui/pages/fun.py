from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from enigmars_util import fun as fun_settings
from enigmars_util.profile import HostProfile
from enigmars_util.sound import play_meow
from enigmars_util.ui.widgets import Card, button


class FunPage(QWidget):
    """Make the OS entertaining. Cat Mode meows via bundled sounds."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = fun_settings.load_settings()
        root = QVBoxLayout(self)
        root.addWidget(
            QLabel("Fun controls are user-level only. Turn on Cat Mode to meow.")
        )

        card = Card(
            "Cat Mode",
            "Meows inside this app when you switch tabs. KDE login/logout "
            "sounds are handled natively by Plasma (see below) — no "
            "listeners, no overlays, nothing watching your clicks.",
        )
        self.cat = QCheckBox("Cat Mode (meow on interactions)")
        self.cat.setChecked(self._settings.cat_mode)
        self.cat.toggled.connect(self._save)
        card.body.addWidget(self.cat)

        self.on_nav = QCheckBox("Meow when switching tabs in this app")
        self.on_nav.setChecked(self._settings.meow_on_nav)
        self.on_nav.toggled.connect(self._save)
        card.body.addWidget(self.on_nav)

        self.on_login = QCheckBox("Meow on login (autostart entry; non-Plasma fallback)")
        self.on_login.setChecked(self._settings.meow_on_login)
        self.on_login.toggled.connect(self._save)
        card.body.addWidget(self.on_login)

        vol_row = QWidget()
        vol_l = QVBoxLayout(vol_row)
        vol_l.setContentsMargins(0, 8, 0, 0)
        self.vol_label = QLabel(f"Volume: {self._settings.volume}")
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(self._settings.volume)
        self.vol.valueChanged.connect(self._vol_changed)
        vol_l.addWidget(self.vol_label)
        vol_l.addWidget(self.vol)
        card.body.addWidget(vol_row)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        card.body.addWidget(button("Test Meow", self._test))
        card.body.addWidget(self.status)
        root.addWidget(card)

        kde = Card(
            "KDE login / logout sounds (recommended on Plasma)",
            "Points Plasma's native Login and Logout event sounds at the "
            "bundled meow. Takes effect next login/logout. Enabling this "
            "removes the autostart login entry so login doesn't meow twice.",
        )
        self.kde_status = QLabel("")
        self.kde_status.setObjectName("muted")
        self.kde_status.setWordWrap(True)
        kde.body.addWidget(self.kde_status)
        kde.body.addWidget(button("Enable KDE login/logout meow", self._kde_enable))
        kde.body.addWidget(button("Preview login sound", lambda: self._kde_preview("startkde")))
        kde.body.addWidget(button("Preview logout sound", lambda: self._kde_preview("exitkde")))
        kde.body.addWidget(button("Disable KDE sounds", self._kde_disable))
        root.addWidget(kde)
        root.addStretch()
        self._kde_refresh()

    def _current(self) -> fun_settings.FunSettings:
        return fun_settings.FunSettings(
            cat_mode=self.cat.isChecked(),
            meow_on_nav=self.on_nav.isChecked(),
            meow_on_login=self.on_login.isChecked(),
            kde_sounds=self._settings.kde_sounds,
            volume=self.vol.value(),
        )

    def _save(self) -> None:
        self._settings = self._current()
        fun_settings.save_settings(self._settings)
        self._sync_login_entry()
        self.vol_label.setText(f"Volume: {self._settings.volume}")

    def _vol_changed(self) -> None:
        self._save()

    def _test(self) -> None:
        ok = play_meow(volume=self.vol.value())
        self.status.setText("Meow!" if ok else "No player found (install mpv/ffplay or QtMultimedia).")

    def _sync_login_entry(self) -> None:
        from enigmars_util import fun_autostart

        try:
            fun_autostart.set_login_enabled(
                self._settings.cat_mode
                and self._settings.meow_on_login
                and not self._settings.kde_sounds
            )
        except OSError as exc:
            self.status.setText(f"Could not update login entry: {exc}")

    def _kde_refresh(self) -> None:
        from enigmars_util import fun_theme

        self.kde_status.setText(
            "KDE login/logout meow is ON (next login/logout)."
            if fun_theme.enabled()
            else "KDE sounds off. Only this app meows."
        )

    def _kde_enable(self) -> None:
        from enigmars_util import fun_theme

        if fun_theme.install():
            self._settings = fun_settings.FunSettings(
                cat_mode=self._settings.cat_mode,
                meow_on_nav=self._settings.meow_on_nav,
                meow_on_login=self._settings.meow_on_login,
                kde_sounds=True,
                volume=self._settings.volume,
            )
            fun_settings.save_settings(self._settings)
            self._sync_login_entry()
        else:
            self.kde_status.setText("Could not install KDE sounds (missing audio files?).")
            return
        self._kde_refresh()

    def _kde_disable(self) -> None:
        from enigmars_util import fun_theme

        fun_theme.uninstall()
        self._settings = fun_settings.FunSettings(
            cat_mode=self._settings.cat_mode,
            meow_on_nav=self._settings.meow_on_nav,
            meow_on_login=self._settings.meow_on_login,
            kde_sounds=False,
            volume=self._settings.volume,
        )
        fun_settings.save_settings(self._settings)
        self._sync_login_entry()
        self._kde_refresh()

    def _kde_preview(self, event: str) -> None:
        from enigmars_util import fun_theme

        ok = fun_theme.preview(event)
        self.kde_status.setText("Meow!" if ok else "No player found (install paplay/mpv/ffplay).")

    def refresh(self) -> fun_settings.FunSettings:
        self._settings = fun_settings.load_settings()
        return self._settings

    def set_profile(self, profile: HostProfile) -> None:
        del profile
