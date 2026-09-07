"""Reusable widgets. Every one sets accessible names so screen readers work."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QGraphicsDropShadowEffect, QSizePolicy, QLayout,
)

from . import theme


def a11y(widget: QWidget, name: str, description: str = "") -> QWidget:
    """Attach accessibility metadata and a tooltip in one call."""
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
        if not widget.toolTip():
            widget.setToolTip(description)
    return widget


class Card(QFrame):
    """A titled surface. Content goes into `.body`."""

    def __init__(self, title: str = "", hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(11)

        if title:
            t = QLabel(title)
            t.setObjectName("CardTitle")
            t.setAccessibleName(f"{title} section")
            outer.addWidget(t)
        if hint:
            h = QLabel(hint)
            h.setObjectName("CardHint")
            h.setWordWrap(True)
            outer.addWidget(h)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)

    def add(self, w) -> None:
        """Accepts any QWidget or any QLayout."""
        if isinstance(w, QLayout):
            self.body.addLayout(w)
        elif isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            raise TypeError(f"Card.add expects a QWidget or QLayout, got {type(w).__name__}")

    def enable_shadow(self, colour: str = "#000000", enabled: bool = True) -> None:
        if not enabled:
            self.setGraphicsEffect(None)
            return
        try:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(26)
            eff.setXOffset(0)
            eff.setYOffset(4)
            c = QColor(colour)
            c.setAlpha(60)
            eff.setColor(c)
            self.setGraphicsEffect(eff)
        except Exception:
            pass


class StatusDot(QLabel):
    """Small coloured state indicator with an accessible text equivalent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._colour = QColor("#8b93ad")
        self._pulse = False
        self.setAccessibleName("VM status indicator")
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._phase = 0

    def set_state(self, colour: str, label: str, pulse: bool = False) -> None:
        self._colour = QColor(colour)
        self.setAccessibleDescription(label)
        self.setToolTip(label)
        self._pulse = pulse
        if pulse and not self._t.isActive():
            self._t.start(90)
        elif not pulse:
            self._t.stop()
            self._phase = 0
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % 40
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._pulse:
            import math
            halo = abs(math.sin(self._phase / 40 * math.pi))
            c = QColor(self._colour)
            c.setAlpha(int(70 * halo))
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            p.drawEllipse(0, 0, 12, 12)
            p.setBrush(QBrush(self._colour))
            p.drawEllipse(2, 2, 8, 8)
        else:
            p.setBrush(QBrush(self._colour))
            p.setPen(Qt.NoPen)
            p.drawEllipse(1, 1, 10, 10)


class Stat(QWidget):
    """A big value with a small caption."""

    def __init__(self, label: str, value: str = "-", parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.value = QLabel(value)
        self.value.setObjectName("StatBig")
        cap = QLabel(label.upper())
        cap.setObjectName("StatLabel")
        v.addWidget(self.value)
        v.addWidget(cap)
        self._label = label
        self.setAccessibleName(label)

    def set(self, text: str) -> None:
        self.value.setText(text)
        self.setAccessibleDescription(f"{self._label}: {text}")


class Toast(QFrame):
    """Transient inline message. Non-modal, so it never blocks the user."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setVisible(False)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 10, 10)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setAccessibleName("Notification")
        close = QPushButton("Dismiss")
        close.setObjectName("Ghost")
        close.setFixedWidth(88)
        close.clicked.connect(lambda: self.setVisible(False))
        h.addWidget(self.label, 1)
        h.addWidget(close)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.setVisible(False))

    def show_message(self, text: str, msec: int = 6000) -> None:
        self.label.setText(text)
        self.setVisible(True)
        if msec:
            self._timer.start(msec)


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("Sep")
    f.setFrameShape(QFrame.HLine)
    return f


def button(text: str, *, primary: bool = False, danger: bool = False,
           ghost: bool = False, tip: str = "", shortcut: str = "") -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("Primary")
    elif danger:
        b.setObjectName("Danger")
    elif ghost:
        b.setObjectName("Ghost")
    label = text
    if shortcut:
        b.setShortcut(shortcut)
        label = f"{text} ({shortcut})"
    a11y(b, text, tip or label)
    b.setCursor(Qt.PointingHandCursor)
    return b


class Backdrop(QWidget):
    """
    The painted background: layered blooms, grain and a vignette.

    Kept as its own widget so the whole window does not repaint when a child
    changes, and so the effect can be switched off wholesale for high contrast
    or reduced-motion preferences.
    """

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.setObjectName("Backdrop")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._pal = palette
        self._depth = True
        self._grain = True

    def set_palette_(self, palette, depth: bool = True, grain: bool = True) -> None:
        self._pal = palette
        self._depth = depth
        self._grain = grain
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        theme.paint_backdrop(p, QRectF(self.rect()), self._pal,
                             depth=self._depth, grain=self._grain)


class Chip(QLabel):
    """A small pill for status words and counts."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setAlignment(Qt.AlignCenter)


class MeterBar(QWidget):
    """A slim labelled usage bar - used for host memory and disk."""

    def __init__(self, label: str, palette, parent=None):
        super().__init__(parent)
        self._pal = palette
        self._frac = 0.0
        self._text = ""
        self.setFixedHeight(38)
        self._label = label
        self.setAccessibleName(label)

    def set_palette_(self, palette) -> None:
        self._pal = palette
        self.update()

    def set_value(self, fraction: float, text: str) -> None:
        self._frac = max(0.0, min(1.0, fraction))
        self._text = text
        self.setAccessibleDescription(f"{self._label}: {text}")
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self._pal
        f = QFont(self.font()); f.setPointSizeF(max(7.5, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(QColor(pal.muted))
        p.drawText(0, 0, self.width(), 15, Qt.AlignLeft | Qt.AlignVCenter, self._label)
        p.drawText(0, 0, self.width(), 15, Qt.AlignRight | Qt.AlignVCenter, self._text)

        track = QRectF(0, 21, self.width(), 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(pal.border_soft)))
        p.drawRoundedRect(track, 3.5, 3.5)

        if self._frac > 0:
            fill = QRectF(track)
            fill.setWidth(track.width() * self._frac)
            colour = pal.accent
            if self._frac > 0.9:
                colour = pal.red
            elif self._frac > 0.75:
                colour = pal.amber
            p.setBrush(QBrush(QColor(colour)))
            p.drawRoundedRect(fill, 3.5, 3.5)


def elevate(widget: QWidget, palette, *, blur: int = 30, y: int = 6,
            alpha: int = 44, enabled: bool = True) -> None:
    """Soft drop shadow. Silently skipped if effects are unavailable."""
    if not enabled:
        widget.setGraphicsEffect(None)
        return
    try:
        eff = QGraphicsDropShadowEffect(widget)
        eff.setBlurRadius(blur)
        eff.setXOffset(0)
        eff.setYOffset(y)
        c = QColor(palette.shadow)
        c.setAlpha(alpha)
        eff.setColor(c)
        widget.setGraphicsEffect(eff)
    except Exception:
        pass


class AlertBar(QFrame):
    """
    Full-width status strip pinned above the content, as in the reference
    layout. Used for connection and process failures that deserve more than a
    toast but should not steal focus with a modal.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AlertBar")
        self.setVisible(False)
        self.setFixedHeight(42)
        self._action_slot = None
        h = QHBoxLayout(self)
        h.setContentsMargins(20, 0, 12, 0)
        h.setSpacing(10)

        self.label = QLabel("")
        self.label.setAccessibleName("Alert")
        self.label.setWordWrap(False)
        h.addWidget(self.label, 1)

        self.action = QPushButton("")
        self.action.setVisible(False)
        self.action.setCursor(Qt.PointingHandCursor)
        h.addWidget(self.action)

        close = QPushButton("Dismiss")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(lambda: self.setVisible(False))
        h.addWidget(close)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.setVisible(False))

    def show_alert(self, text: str, *, kind: str = "error", msec: int = 0,
                   action: str = "", on_action=None) -> None:
        self.setObjectName({"error": "AlertBar",
                            "ok": "AlertBarOk",
                            "warn": "AlertBarWarn"}.get(kind, "AlertBar"))
        self.style().unpolish(self)
        self.style().polish(self)
        self.label.setText(text)
        self.label.setAccessibleDescription(text)

        if self._action_slot is not None:
            try:
                self.action.clicked.disconnect(self._action_slot)
            except (TypeError, RuntimeError):
                pass
            self._action_slot = None
        if action and on_action:
            self.action.setText(action)
            self.action.setVisible(True)
            self._action_slot = lambda: (self.setVisible(False), on_action())
            self.action.clicked.connect(self._action_slot)
        else:
            self.action.setVisible(False)

        self.setVisible(True)
        if msec:
            self._timer.start(msec)
