from __future__ import annotations

from PySide6.QtCore import QSize, QThread, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from enigmars_util.ui.layout import clamp_launch_size

from enigmars_util.probe import probe_host
from enigmars_util.profile import HostProfile
from enigmars_util.secureboot import load_resume_phase
from enigmars_util.self_update import UpdateStatus, check_for_update
from enigmars_util.ui.jobs import Work
from enigmars_util.ui.pages.about import AboutPage
from enigmars_util.ui.pages.drivers import DriversPage
from enigmars_util.ui.pages.extras import ExtrasPage
from enigmars_util.ui.pages.fun import FunPage
from enigmars_util.ui.pages.home import HomePage
from enigmars_util.ui.pages.kernel import KernelPage
from enigmars_util.ui.pages.packages import PackagesPage
from enigmars_util.ui.pages.patches import PatchesPage
from enigmars_util.ui.pages.secureboot import SecureBootPage
from enigmars_util.ui.pages.tweaks import TweaksPage


class _ProbeThread(QThread):
    done = Signal(object)

    def run(self) -> None:
        self.done.emit(probe_host())


class MainWindow(QMainWindow):
    def __init__(self, start_page: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Enigmars Utils")
        self.setMinimumSize(720, 520)
        self._profile: HostProfile | None = None
        self._auto_fit = True

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(180)
        nav_l = QVBoxLayout(nav)
        self._nav_btns: dict[str, QPushButton] = {}
        self.stack = QStackedWidget()
        self.home = HomePage(self.show_page, on_update=self._home_update)
        self.tweaks = TweaksPage()
        self.packages = PackagesPage()
        self.extras = ExtrasPage()
        self.kernel = KernelPage()
        self.patches = PatchesPage()
        self.drivers = DriversPage()
        self.secureboot = SecureBootPage()
        self.fun = FunPage()
        self.about = AboutPage()
        pages = (
            ("home", "Home", self.home),
            ("tweaks", "Tweaks", self.tweaks),
            ("packages", "Packages", self.packages),
            ("enigmars-packages", "Enigmars Pkgs", self.extras),
            ("kernel", "Kernel", self.kernel),
            ("patches", "Patches", self.patches),
            ("drivers", "Drivers", self.drivers),
            ("secure-boot", "Secure Boot", self.secureboot),
            ("fun", "Fun", self.fun),
            ("about", "About", self.about),
        )
        for key, label, widget in pages:
            self.stack.addWidget(widget)
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.show_page(k))
            nav_l.addWidget(btn)
            self._nav_btns[key] = btn
        nav_l.addStretch()
        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)
        self._order = [p[0] for p in pages]
        initial = start_page or ("secure-boot" if load_resume_phase() else "home")
        self.show_page(initial if initial in self._order else "home")

        self._probe = _ProbeThread(self)
        self._probe.done.connect(self._on_profile)
        self._probe.start()
        self._update_work: Work | None = None
        self._fit_launch_size()

    def _preferred_size(self) -> QSize:
        home = self.home.unscrolled_size()
        nav_w = 180 + 12
        chrome = 40
        return QSize(home.width() + nav_w + 32, home.height() + chrome)

    def _available_size(self) -> QSize:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(1280, 720)
        geo = screen.availableGeometry()
        return QSize(geo.width(), geo.height())

    def _fit_launch_size(self) -> None:
        if not self._auto_fit:
            return
        size = clamp_launch_size(self._preferred_size(), self._available_size())
        self.setMinimumSize(QSize(min(720, size.width()), min(520, size.height())))
        self.resize(size)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._probe.isRunning():
            self._probe.wait(4000)
        for worker in (
            getattr(self.packages, "_search_work", None),
            getattr(self.extras, "_work", None),
            getattr(self.kernel, "_work", None),
            getattr(self.kernel, "_repo_work", None),
            getattr(self.patches, "_patch_work", None),
            self._update_work,
            getattr(self.about, "_check_work", None),
            getattr(self.home, "_check_work", None),
        ):
            if worker is not None and worker.isRunning():
                worker.wait(4000)
        super().closeEvent(event)

    def _home_update(self) -> None:
        self.show_page("packages")
        self.packages._update()

    def show_page(self, key: str) -> None:
        if key not in self._order:
            return
        self.stack.setCurrentIndex(self._order.index(key))
        for name, btn in self._nav_btns.items():
            btn.setChecked(name == key)
        if key != "fun":
            try:
                from enigmars_util import fun as fun_settings
                from enigmars_util.sound import play_meow

                settings = self.fun.refresh()
                if fun_settings.should_meow_on_nav(settings):
                    play_meow(volume=settings.volume)
            except Exception:  # noqa: BLE001
                pass

    def _on_profile(self, profile: object) -> None:
        if not isinstance(profile, HostProfile):
            return
        self._profile = profile
        self.setWindowTitle("Enigmars Utils")
        for page in (
            self.home,
            self.tweaks,
            self.packages,
            self.extras,
            self.kernel,
            self.patches,
            self.drivers,
            self.secureboot,
            self.fun,
            self.about,
        ):
            page.set_profile(profile)
        self._fit_launch_size()
        self._auto_fit = False
        self._start_update_check()

    def _start_update_check(self) -> None:
        def work() -> UpdateStatus | Exception:
            try:
                return check_for_update()
            except Exception as exc:  # noqa: BLE001
                return exc

        thread = Work(work, self)
        self._update_work = thread

        def done(obj: object) -> None:
            if isinstance(obj, UpdateStatus):
                self.home.set_update_status(obj)
                self.about.set_update_status(obj)
                return
            if isinstance(obj, Exception):
                self.home.set_update_error(str(obj))
                self.about.set_update_error(str(obj))

        thread.result.connect(done)
        thread.start()
