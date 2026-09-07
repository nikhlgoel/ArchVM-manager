"""Application entry point: single instance, high-DPI, tray lifecycle."""
from __future__ import annotations

import sys

from pathlib import Path

from PySide6.QtCore import Qt, QSharedMemory, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import icons, paths
from .config import AppSettings, VMConfig
from .tray import Tray
from .window import MainWindow


def _single_instance_guard() -> "QSharedMemory | None":
    """Prevent a second copy fighting over the same VM. Returns the lock."""
    try:
        mem = QSharedMemory(f"{paths.APP_NAME}-single-instance")
        if mem.attach():
            mem.detach()
            return None
        if mem.create(1):
            return mem
    except Exception:
        pass
    # If shared memory is unavailable, allow the app rather than blocking it.
    return QSharedMemory("noop")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    start_in_tray = "--tray" in argv

    # High-DPI: Qt6 scales by default; make fractional scaling look right.
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass

    app = QApplication([a for a in argv if a != "--tray"])
    app.setApplicationName(paths.APP_NAME)
    app.setApplicationDisplayName(paths.APP_NAME)
    app.setApplicationVersion(paths.APP_VERSION)
    app.setOrganizationName(paths.ORG_NAME)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)      # tray keeps us alive

    lock = _single_instance_guard()
    if lock is None:
        QMessageBox.information(
            None, paths.APP_NAME,
            f"{paths.APP_NAME} is already running.\n\n"
            "Look for it in the system tray (near the clock).")
        return 0

    paths.ensure_dirs()
    settings = AppSettings.load()

    # Splash covers the first-run work: reading the host, building the window.
    splash = None
    if not (start_in_tray or settings.start_minimised):
        try:
            from . import theme
            from .splash import Splash
            splash = Splash(theme.resolve(settings.theme),
                            reduce_motion=settings.reduce_motion)
            splash.start()
        except Exception:
            splash = None

    def stage(text: str, frac: float | None = None) -> None:
        if splash is not None:
            splash.set_status(text, frac)

    stage("Reading your Windows settings…", 0.15)
    try:
        from . import hostinfo
        hostinfo.cached()
    except Exception:
        pass

    stage("Loading configuration…", 0.45)
    cfg = VMConfig.load()

    stage("Preparing the interface…", 0.72)
    win = MainWindow(cfg, settings)
    stage("Ready", 1.0)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(win, settings)
        win.request_quit.connect(
            lambda: tray.notify("Still running in the tray. "
                                "Right-click the icon for options."))
    else:
        # No tray: closing must really quit, or the app becomes unreachable.
        settings.close_to_tray = False
        settings.minimise_to_tray = False
        app.setQuitOnLastWindowClosed(True)

    if not (start_in_tray or settings.start_minimised) or tray is None:
        if splash is not None:
            splash.finish(win)
        else:
            win.show()
    elif splash is not None:
        splash.finish(None)

    # First run, or an incomplete environment, opens the guided setup.
    if not start_in_tray and not settings.start_minimised:
        QTimer.singleShot(300, lambda: _maybe_setup(win, settings))
    elif not paths.qemu_available():
        QTimer.singleShot(600, lambda: win.toast.show_message(
            f"QEMU was not found at {paths.QEMU_DIR}. "
            "Open Settings and run the setup wizard."))

    return app.exec()


def _maybe_setup(win, settings) -> None:
    """Open the wizard on first run, or whenever something essential is absent."""
    from . import deps
    if settings.setup_done:
        # Cheap re-check: only the things that can vanish between runs.
        if paths.qemu_available() and Path(win.cfg.disk).exists():
            return
    try:
        checks = deps.build_checks()
        for c in checks:
            c.run_detect()
        if deps.setup_complete(checks) and settings.setup_done:
            return
    except Exception:
        return
    win.run_setup_wizard()
    settings.setup_done = True
    settings.save()
