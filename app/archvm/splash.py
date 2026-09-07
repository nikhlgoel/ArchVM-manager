"""
Startup splash.

Frameless, rounded, painted with the same backdrop as the main window so the
app feels continuous from the first frame. The mark is drawn in perspective
with a cast shadow and reflection, which is where the sense of depth comes
from — a flat logo on a gradient reads as a loading screen, not a product.
"""
from __future__ import annotations

from PySide6.QtCore import (Qt, QTimer, QRectF, QPointF, QPropertyAnimation,
                            QEasingCurve, QElapsedTimer)
from PySide6.QtGui import (QPainter, QColor, QFont, QPainterPath,
                           QLinearGradient, QTransform, QBrush, QPen)
from PySide6.QtWidgets import QWidget, QApplication

from . import icons, paths, theme


class Splash(QWidget):
    """Shown while the first window and the environment scan are prepared."""

    #: The splash is worth seeing, and on a warm start the work behind it takes
    #: barely 200 ms - so hold it on screen long enough to read, then leave.
    MIN_VISIBLE_MS = 1500
    INTRO_MS = 520

    def __init__(self, palette, *, reduce_motion: bool = False):
        super().__init__(None,
                         Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._pal = palette
        self._reduce = reduce_motion
        self._status = "Starting…"
        self._spin = 0.0

        # Progress eases toward a target rather than snapping to it, so the
        # four startup stages read as one continuous fill.
        self._progress = 0.0
        self._target = 0.0

        self._clock = QElapsedTimer()
        self._closing = False

        self.resize(560, 340)
        self._centre()

        self._mark = icons.app_icon().pixmap(150, 150)

        if not reduce_motion:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(16)          # 60 fps

        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(300)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _ease_out(t: float) -> float:
        """Cubic ease-out, clamped. Fast to start, settles gently."""
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        return 1.0 - (1.0 - t) ** 3

    @property
    def _intro(self) -> float:
        """0 → 1 over INTRO_MS: the mark rising and the text settling in."""
        if self._reduce or not self._clock.isValid():
            return 1.0
        return self._ease_out(self._clock.elapsed() / self.INTRO_MS)

    # ------------------------------------------------------------------ #
    def _centre(self) -> None:
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.move(g.center().x() - self.width() // 2,
                      g.center().y() - self.height() // 2)
        except Exception:
            pass

    def start(self) -> None:
        self._clock.start()
        self.show()
        self._fade.start()
        QApplication.processEvents()

    def set_status(self, text: str, progress: float | None = None) -> None:
        """
        Update the caption, and set where the bar should travel to.

        The bar is not moved directly: _tick eases it toward the target, so
        four discrete stages still read as one continuous fill.
        """
        self._status = text
        if progress is not None:
            self._target = max(0.0, min(1.0, progress))
            if self._reduce:
                self._progress = self._target
        self.update()
        QApplication.processEvents()

    def set_progress(self, progress: float) -> None:
        """Move the bar without touching the caption."""
        self._target = max(0.0, min(1.0, progress))
        if self._reduce:
            self._progress = self._target
        self.update()

    def remaining_ms(self) -> int:
        """How much longer the splash owes the user before it may close."""
        if self._reduce or not self._clock.isValid():
            return 0
        return max(0, self.MIN_VISIBLE_MS - int(self._clock.elapsed()))

    def finish(self, window=None) -> int:
        """
        Close the splash and reveal `window`.

        Startup work can finish in a couple of hundred milliseconds on a warm
        run, which is not long enough to see anything. Rather than block, the
        close is deferred to MIN_VISIBLE_MS - the event loop keeps running, so
        the bar finishes travelling and the fade stays smooth.

        Returns the delay in ms after which the main window appears, so the
        caller can schedule follow-on work (the setup wizard) behind it.
        """
        self._target = 1.0
        wait = self.remaining_ms()
        QTimer.singleShot(wait, lambda: self._close_out(window))
        return wait + 140

    def _close_out(self, window=None) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            out = QPropertyAnimation(self, b"windowOpacity", self)
            out.setDuration(260)
            out.setStartValue(self.windowOpacity())
            out.setEndValue(0.0)
            out.setEasingCurve(QEasingCurve.InCubic)
            out.finished.connect(self._stop_and_close)
            out.start()
            self._out = out            # keep a reference alive
            if window is not None:
                # Overlap slightly: the window is up before the splash is gone,
                # so the eye never crosses an empty desktop.
                QTimer.singleShot(140, window.show)
        except Exception:
            self._stop_and_close()
            if window is not None:
                window.show()

    def _stop_and_close(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.close()

    def _tick(self) -> None:
        self._spin = (self._spin + 0.014) % 1.0
        # Exponential approach, with a floor on the step. Easing alone spends
        # the last few percent almost stationary, which reads as a stall; the
        # floor keeps it visibly moving all the way to the end.
        gap = self._target - self._progress
        if gap > 0:
            self._progress = min(self._target,
                                 self._progress + max(gap * 0.10, 0.006))
        elif gap < 0:
            self._progress = self._target
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
        # The intro drops the mark in from slightly above and behind, and lets
        # the shadow tighten under it as it lands.
        k = self._intro
        cx, cy = r.width() * 0.30, r.height() * 0.44
        cy -= (1.0 - k) * 18.0
        scale = 0.92 + 0.08 * k
        mark = self._mark
        mw = mark.width()

        # cast shadow: squashed ellipse under the mark
        p.save()
        sh = QColor(pal.shadow)
        sh.setAlpha(int((70 if pal.name == "light" else 120) * (0.35 + 0.65 * k)))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sh))
        # wider and softer while the mark is still high, tightening as it lands
        spread = 1.0 + (1.0 - k) * 0.30
        p.drawEllipse(QPointF(cx, r.height() * 0.44 + mw * 0.62),
                      mw * 0.44 * spread, mw * 0.10)
        p.restore()

        # the mark itself, tilted very slightly
        p.save()
        p.setOpacity(k)
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(-8 - (1.0 - k) * 6, Qt.YAxis)
        t.rotate(-2)
        t.scale(scale, scale)
        t.translate(-mw / 2, -mw / 2)
        p.setTransform(t, True)
        p.drawPixmap(0, 0, mark)
        p.restore()

        # reflection, fading out
        p.save()
        p.setOpacity(0.16 * k)
        t2 = QTransform()
        t2.translate(cx - mw * scale / 2, cy + mw * 0.52)
        t2.scale(scale, -0.42 * scale)
        p.setTransform(t2, True)
        p.drawPixmap(0, 0, mark)
        p.restore()

        # --- wordmark ---
        # The three lines slide in from the right on a short stagger, each one
        # a little behind the last, so the block assembles rather than appears.
        ty = r.height() * 0.44
        tx = r.width() * 0.50
        tw = r.width() - tx - 34

        def line(delay: float) -> tuple[float, float]:
            """Offset and opacity for a text line starting `delay` into the intro."""
            if self._reduce or not self._clock.isValid():
                return 0.0, 1.0
            e = self._ease_out(
                (self._clock.elapsed() - delay * self.INTRO_MS) / self.INTRO_MS)
            return (1.0 - e) * 22.0, e

        dx, op = line(0.10)
        p.setOpacity(op)
        p.setPen(QColor(pal.text))
        f = QFont("Segoe UI Variable Display", 25)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(tx + dx, ty - 46, tw, 40),
                   Qt.AlignLeft | Qt.AlignVCenter, paths.APP_NAME)

        p.setPen(QColor(pal.muted))
        f2 = QFont("Segoe UI", 10)
        p.setFont(f2)

        dx, op = line(0.26)
        p.setOpacity(op)
        p.drawText(QRectF(tx + dx, ty - 8, tw, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   "Arch Linux · Hyprland · QEMU")

        dx, op = line(0.38)
        p.setOpacity(op)
        p.drawText(QRectF(tx + dx, ty + 12, tw, 20),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"version {paths.APP_VERSION}")
        p.setOpacity(1.0)

        # --- progress rail ---
        rail = QRectF(tx, r.height() - 86, tw, 5)
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
        p.drawText(QRectF(tx, r.height() - 74, tw, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, self._status)

        # hairline edge
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        edge = QColor(pal.border)
        edge.setAlpha(190)
        p.setPen(QPen(edge, 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
