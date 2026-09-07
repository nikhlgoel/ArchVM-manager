"""System tray icon with a full right-click menu, so the app can run headless."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import icons, paths


class Tray(QObject):
    def __init__(self, window, settings, parent=None):
        super().__init__(parent)
        self.win = window
        self.settings = settings
        self._state = "stopped"

        self.icon = QSystemTrayIcon(icons.tray_icon("stopped"))
        self.icon.setToolTip(f"{paths.APP_NAME} — stopped")
        self.icon.activated.connect(self._activated)

        self._build_menu()
        self.icon.setContextMenu(self.menu)
        self.icon.show()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1500)

    # ------------------------------------------------------------------ #
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _build_menu(self) -> None:
        m = QMenu()
        self.menu = m

        self.act_header = QAction(f"{paths.APP_NAME} {paths.APP_VERSION}", m)
        self.act_header.setEnabled(False)
        m.addAction(self.act_header)

        self.act_state = QAction("VM: stopped", m)
        self.act_state.setEnabled(False)
        m.addAction(self.act_state)
        m.addSeparator()

        self.act_show = QAction("Open ArchVM", m)
        self.act_show.triggered.connect(self.show_window)
        m.addAction(self.act_show)
        m.addSeparator()

        # --- power ---
        self.act_start = QAction("Start VM", m)
        self.act_start.triggered.connect(lambda: self.win._start(False))
        m.addAction(self.act_start)

        self.act_install = QAction("Install Arch…", m)
        self.act_install.triggered.connect(lambda: self.win._start(True))
        m.addAction(self.act_install)

        self.act_shutdown = QAction("Shut down guest", m)
        self.act_shutdown.triggered.connect(self.win._shutdown)
        m.addAction(self.act_shutdown)

        self.act_stop = QAction("Force stop", m)
        self.act_stop.triggered.connect(self.win._force_stop)
        m.addAction(self.act_stop)
        m.addSeparator()

        # --- quick actions ---
        quick = m.addMenu("Quick actions")
        a = QAction("Open SSH session", quick)
        a.triggered.connect(self.win._open_ssh)
        quick.addAction(a)
        a = QAction("Send clipboard to VM", quick)
        a.triggered.connect(self._send_clipboard)
        quick.addAction(a)
        a = QAction("Type installer command", quick)
        a.triggered.connect(self._send_install_cmd)
        quick.addAction(a)
        a = QAction("Manage snapshots…", quick)
        a.triggered.connect(lambda: (self.show_window(), self.win._manage_snapshots()))
        quick.addAction(a)
        quick.addSeparator()
        a = QAction("Open VM folder", quick)
        a.triggered.connect(lambda: self.win._open(paths.ROOT))
        quick.addAction(a)
        a = QAction("Open logs", quick)
        a.triggered.connect(lambda: (self.show_window(), self.win._go(5)))
        quick.addAction(a)

        # --- settings submenu ---
        st = m.addMenu("Settings")

        th = st.addMenu("Theme")
        self._theme_group = QActionGroup(th)
        self._theme_group.setExclusive(True)
        for name in ("auto", "dark", "light"):
            act = QAction(name.capitalize(), th, checkable=True)
            act.setChecked(self.settings.theme == name)
            act.triggered.connect(lambda _c, n=name: self._set_theme(n))
            self._theme_group.addAction(act)
            th.addAction(act)

        self.act_translucent = QAction("Translucent backdrop", st, checkable=True)
        self.act_translucent.setChecked(self.settings.translucency)
        self.act_translucent.triggered.connect(
            lambda c: self._set("translucency", c, self.win.ck_translucent))
        st.addAction(self.act_translucent)

        self.act_gradient = QAction("Gradient surfaces", st, checkable=True)
        self.act_gradient.setChecked(self.settings.gradient)
        self.act_gradient.triggered.connect(
            lambda c: self._set("gradient", c, self.win.ck_gradient))
        st.addAction(self.act_gradient)

        st.addSeparator()

        self.act_close_tray = QAction("Close button minimises to tray", st, checkable=True)
        self.act_close_tray.setChecked(self.settings.close_to_tray)
        self.act_close_tray.triggered.connect(
            lambda c: self._set("close_to_tray", c, self.win.ck_close_tray))
        st.addAction(self.act_close_tray)

        self.act_autostart = QAction("Start with Windows", st, checkable=True)
        self.act_autostart.setChecked(self.settings.autostart)
        self.act_autostart.triggered.connect(self._toggle_autostart)
        st.addAction(self.act_autostart)

        self.act_notify = QAction("Tray notifications", st, checkable=True)
        self.act_notify.setChecked(self.settings.notifications)
        self.act_notify.triggered.connect(
            lambda c: self._set("notifications", c, self.win.ck_notify))
        st.addAction(self.act_notify)

        st.addSeparator()
        a = QAction("All settings…", st)
        a.triggered.connect(lambda: (self.show_window(), self.win._go(4)))
        st.addAction(a)

        m.addSeparator()
        a = QAction("Run setup wizard…", m)
        a.triggered.connect(lambda: (self.show_window(), self.win.run_setup_wizard()))
        m.addAction(a)

        m.addSeparator()
        a = QAction("About", m)
        a.triggered.connect(lambda: (self.show_window(), self.win._about()))
        m.addAction(a)

        self.act_quit = QAction("Quit ArchVM", m)
        self.act_quit.triggered.connect(self.quit)
        m.addAction(self.act_quit)

    # ------------------------------------------------------------------ #
    def _set(self, attr: str, value: bool, mirror_checkbox=None) -> None:
        setattr(self.settings, attr, value)
        self.settings.save()
        if mirror_checkbox is not None:
            mirror_checkbox.blockSignals(True)
            mirror_checkbox.setChecked(value)
            mirror_checkbox.blockSignals(False)
        self.win.apply_theme()

    def _set_theme(self, name: str) -> None:
        self.settings.theme = name
        self.settings.save()
        self.win.cb_theme.blockSignals(True)
        self.win.cb_theme.setCurrentText(name)
        self.win.cb_theme.blockSignals(False)
        self.win.apply_theme()

    def _toggle_autostart(self, checked: bool) -> None:
        if self.win._set_autostart(checked):
            self.settings.autostart = checked
            self.settings.save()
            self.win.ck_autostart.blockSignals(True)
            self.win.ck_autostart.setChecked(checked)
            self.win.ck_autostart.blockSignals(False)
        else:
            self.act_autostart.setChecked(self.settings.autostart)
            self.notify("Could not change the Windows startup entry.")

    def _send_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            self.notify("Clipboard is empty.")
            return
        self.win._send(text)

    def _send_install_cmd(self) -> None:
        self.win._send_install_cmd()

    # ------------------------------------------------------------------ #
    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.win.isVisible() and not self.win.isMinimized():
                self.win.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.win.showNormal()
        self.win.raise_()
        self.win.activateWindow()

    def quit(self) -> None:
        self.win.force_quit()
        self.icon.hide()
        QApplication.instance().quit()

    def notify(self, message: str, title: str = "") -> None:
        if not self.settings.notifications:
            return
        try:
            self.icon.showMessage(title or paths.APP_NAME, message,
                                  icons.tray_icon(self._state), 4000)
        except Exception:
            pass

    def refresh(self) -> None:
        running = self.win.runner.is_running()
        state = "running" if running else "stopped"
        if state != self._state:
            self._state = state
            self.icon.setIcon(icons.tray_icon(state))
            self.icon.setToolTip(f"{paths.APP_NAME} — VM {state}")
            self.notify(f"VM {state}.")
        self.act_state.setText(f"VM: {state}")
        self.act_start.setEnabled(not running)
        self.act_install.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.act_shutdown.setEnabled(running)
