#!/usr/bin/env python3
"""
Start the application offscreen, build every page, and exit.

Catches the class of breakage that import checks miss - a widget constructed
with the wrong argument, a missing signal, a stylesheet that Qt rejects - without
needing a display or a working QEMU install.

    python app/tools/smoke_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FAILURES: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  ok    {label}")
    except Exception as e:
        FAILURES.append(f"{label}: {type(e).__name__}: {e}")
        print(f"  FAIL  {label}: {type(e).__name__}: {e}")


def main() -> int:
    print("ArchVM smoke test\n")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    app = QApplication.instance() or QApplication([])

    from archvm import icons, paths, theme, hostinfo
    from archvm.config import AppSettings, VMConfig
    from archvm.window import MainWindow

    print(f"  version {paths.APP_VERSION}\n")

    check("host detection", lambda: hostinfo.detect())
    check("settings load", lambda: AppSettings.load())
    check("vm config load", lambda: VMConfig.load())
    check("config validate", lambda: VMConfig.load().validate())
    check("qemu args (run)", lambda: VMConfig.load().build_args(False))
    check("qemu args (install)", lambda: VMConfig.load().build_args(True))
    check("app icon", lambda: icons.app_icon())
    check("tray icons", lambda: [icons.tray_icon(s)
                                 for s in ("stopped", "running")])
    check("mark render", lambda: [icons.mark(s) for s in (16, 32, 64, 256)])

    for mode in ("light", "dark", "auto"):
        check(f"stylesheet ({mode})",
              lambda m=mode: theme.stylesheet(theme.resolve(m)))
        check(f"qpalette ({mode})",
              lambda m=mode: theme.qpalette(theme.resolve(m)))

    win = None

    def build_window():
        nonlocal win
        win = MainWindow(VMConfig.load(), AppSettings.load())
        win.show()

    check("main window", build_window)

    if win is not None:
        stack = getattr(win, "stack", None)
        if stack is not None:
            for i in range(stack.count()):
                check(f"page {i}: {stack.widget(i).objectName() or i}",
                      lambda n=i: stack.setCurrentIndex(n))

    QTimer.singleShot(400, app.quit)
    app.exec()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
