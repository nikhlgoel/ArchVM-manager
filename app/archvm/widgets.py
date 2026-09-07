"""Reusable widgets. Every one sets accessible names so screen readers work."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, Property
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QGraphicsDropShadowEffect, QSizePolicy, QLayout,
)


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
