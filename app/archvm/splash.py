"""
Startup splash.

Frameless, rounded, painted with the same backdrop as the main window so the
app feels continuous from the first frame. The mark is drawn in perspective
with a cast shadow and reflection, which is where the sense of depth comes
from — a flat logo on a gradient reads as a loading screen, not a product.
"""
from __future__ import annotations

from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation,
                            QEasingCurve, Property, Signal, QObject)
from PySide6.QtGui import (QPainter, QColor, QPixmap, QFont, QPainterPath,
                           QLinearGradient, QTransform, QBrush, QPen)
from PySide6.QtWidgets import QWidget, QApplication

from . import icons, paths, theme


class Splash(QWidget):
    """Shown while the first window and the environment scan are prepared."""

    def __init__(self, palette, *, reduce_motion: bool = False):
        super().__init__(None,
                         Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._pal = palette
        self._reduce = reduce_motion
        self._status = "Starting…"
        self._progress = 0.0
        self._spin = 0.0

        self.resize(560, 340)
        self._centre()

        self._mark = icons.app_icon().pixmap(150, 150)

        if not reduce_motion:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(33)

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(260)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------ #
    def _centre(self) -> None:
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.move(g.center().x() - self.width() // 2,
                      g.center().y() - self.height() // 2)
        except Exception:
            pass

    def start(self) -> None:
        self.show()
        self._fade.start()
        QApplication.processEvents()

    def set_status(self, text: str, progress: float | None = None) -> None:
        self._status = text
        if progress is not None:
            self._progress = max(0.0, min(1.0, progress))
        self.update()
        QApplication.processEvents()

    def finish(self, window=None) -> None:
        try:
            if hasattr(self, "_timer"):
                self._timer.stop()
            out = QPropertyAnimation(self, b"windowOpacity", self)
            out.setDuration(200)
            out.setStartValue(self.windowOpacity())
            out.setEndValue(0.0)
            out.setEasingCurve(QEasingCurve.InCubic)
            out.finished.connect(self.close)
            out.start()
            self._out = out            # keep a reference alive
            if window is not None:
                QTimer.singleShot(120, window.show)
        except Exception:
            self.close()
            if window is not None:
                window.show()

    def _tick(self) -> None:
        self._spin = (self._spin + 0.022) % 1.0
        self.update()

    # ------------------------------------------------------------------ #
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        pal = self._pal
        r = QRectF(self.rect())

        # rounded card with the shared backdrop inside it
        clip = QPainterPath()
        clip.addRoundedRect(r.adjusted(1, 1, -1, -1), 18, 18)
        p.setClipPath(clip)
        theme.paint_backdrop(p, r, pal, depth=True, grain=not self._reduce)

        # --- mark, in perspective with a cast shadow and reflection ---
        cx, cy = r.width() * 0.30, r.height() * 0.44
        mark = self._mark
        mw = mark.width()

        # cast shadow: squashed ellipse under the mark
        p.save()
        sh = QColor(pal.shadow)
        sh.setAlpha(70 if pal.name == "light" else 120)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sh))
        p.drawEllipse(QPointF(cx, cy + mw * 0.62), mw * 0.44, mw * 0.10)
        p.restore()

        # the mark itself, tilted very slightly
        p.save()
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(-8, Qt.YAxis)
        t.rotate(-2)
        t.translate(-mw / 2, -mw / 2)
        p.setTransform(t, True)
        p.drawPixmap(0, 0, mark)
        p.restore()

        # reflection, fading out
        p.save()
        p.setOpacity(0.16)
        t2 = QTransform()
        t2.translate(cx - mw / 2, cy + mw * 0.52)
        t2.scale(1.0, -0.42)
        p.setTransform(t2, True)
        p.drawPixmap(0, 0, mark)
        p.restore()

        # --- wordmark ---
        tx = r.width() * 0.50
        p.setPen(QColor(pal.text))
        f = QFont("Segoe UI Variable Display", 25)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(tx, cy - 46, r.width() - tx - 34, 40),
                   Qt.AlignLeft | Qt.AlignVCenter, paths.APP_NAME)

        p.setPen(QColor(pal.muted))
        f2 = QFont("Segoe UI", 10)
        p.setFont(f2)
        p.drawText(QRectF(tx, cy - 8, r.width() - tx - 34, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "Arch Linux · Hyprland · QEMU")
        p.drawText(QRectF(tx, cy + 12, r.width() - tx - 34, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"version {paths.APP_VERSION}")

        # --- progress rail ---
        rail = QRectF(tx, r.height() - 86, r.width() - tx - 34, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(pal.border_soft)))
        p.drawRoundedRect(rail, 2.5, 2.5)

        if self._progress > 0:
            fill = QRectF(rail)
            fill.setWidth(rail.width() * self._progress)
            g = QLinearGradient(fill.topLeft(), fill.topRight())
            g.setColorAt(0.0, QColor(theme.BRAND_A))
            g.setColorAt(1.0, QColor(pal.accent))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(fill, 2.5, 2.5)
        elif not self._reduce:
            # indeterminate: a short sweep travelling the rail
            w = rail.width() * 0.28
            x = rail.left() + (rail.width() + w) * self._spin - w
            seg = QRectF(max(rail.left(), x), rail.top(),
                         min(w, rail.right() - max(rail.left(), x)), rail.height())
            if seg.width() > 0:
                g = QLinearGradient(seg.topLeft(), seg.topRight())
                g.setColorAt(0.0, QColor(theme.BRAND_A))
                g.setColorAt(1.0, QColor(pal.accent))
                p.setBrush(QBrush(g))
                p.drawRoundedRect(seg, 2.5, 2.5)

        p.setPen(QColor(pal.muted))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(tx, r.height() - 74, r.width() - tx - 34, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, self._status)

        # hairline edge
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        edge = QColor(pal.border)
        edge.setAlpha(190)
        p.setPen(QPen(edge, 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
