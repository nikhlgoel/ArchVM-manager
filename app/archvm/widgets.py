"""Reusable widgets. Every one sets accessible names so screen readers work."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QFont, QLinearGradient
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


class Stat(QFrame):
    """A big value with icon, caption, and subtle status sub-caption in an elevated tile."""

    def __init__(self, label: str, value: str = "-", icon: str = "", sub: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("StatTile")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        if icon:
            self.icon_lbl = QLabel(icon)
            self.icon_lbl.setObjectName("StatIcon")
            top.addWidget(self.icon_lbl)
        else:
            self.icon_lbl = None

        cap = QLabel(label.upper())
        cap.setObjectName("StatLabel")
        top.addWidget(cap)
        top.addStretch()
        v.addLayout(top)

        self.value = QLabel(value)
        self.value.setObjectName("StatBig")
        v.addWidget(self.value)

        self.sub = QLabel(sub)
        self.sub.setObjectName("StatSub")
        v.addWidget(self.sub)

        self._label = label
        self.setAccessibleName(label)

    def set(self, text: str, sub: str | None = None) -> None:
        self.value.setText(text)
        if sub is not None:
            self.sub.setText(sub)
        self.setAccessibleDescription(f"{self._label}: {text} {self.sub.text()}")


class Toast(QFrame):
    """Transient inline message. Non-modal, so it never blocks the user."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toast")
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


class StatusBadge(QFrame):
    """Semantic status pill with a glowing state indicator."""

    def __init__(self, text: str = "", state: str = "stopped", parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBadge")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(6)

        self.dot = StatusDot()
        self.label = QLabel(text.upper() if text else "STOPPED")
        h.addWidget(self.dot)
        h.addWidget(self.label)

        self._state = state
        self.setText(text or "NOT INSTALLED")

    def setText(self, text: str) -> None:
        """Compatibility with standard label API."""
        txt = text.strip().upper() if text else "NOT INSTALLED"
        self.label.setText(txt)
        state_map = {
            "RUNNING": "running",
            "INSTALLING": "installing",
            "READY": "ready",
            "NOT INSTALLED": "stopped",
            "STOPPED": "stopped",
        }
        st = state_map.get(txt, "stopped")
        self.set_status(st, txt)

    def text(self) -> str:
        return self.label.text()

    def set_status(self, state: str, text: str = "") -> None:
        self._state = state
        txt = text.upper() if text else state.upper()
        self.label.setText(txt)
        self.setObjectName(f"StatusBadge_{state}")
        self.style().unpolish(self)
        self.style().polish(self)

        pal = getattr(self.window(), "_palette", None)
        dot_col = "#64748b"
        pulse = False
        if pal:
            if state == "running":
                dot_col = pal.green
                pulse = True
            elif state == "installing":
                dot_col = pal.amber
                pulse = True
            elif state == "ready":
                dot_col = pal.accent
            else:
                dot_col = pal.muted

        self.dot.set_state(dot_col, txt, pulse=pulse)


class Chip(StatusBadge):
    """A small pill for status words and counts."""
    pass


class MeterBar(QWidget):
    """A sleek labelled usage bar - used for host memory and disk."""

    def __init__(self, label: str, palette, icon: str = "", parent=None):
        super().__init__(parent)
        self._pal = palette
        self._icon = icon
        self._frac = 0.0
        self._text = ""
        self.setFixedHeight(44)
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
        w, h = self.width(), self.height()

        f = QFont(self.font())
        f.setPointSizeF(max(8.5, f.pointSizeF() - 0.5))
        f.setBold(True)
        p.setFont(f)

        # Label with optional icon
        title = f"{self._icon}  {self._label}" if self._icon else self._label
        p.setPen(QColor(pal.text))
        p.drawText(0, 0, w, 18, Qt.AlignLeft | Qt.AlignVCenter, title)

        # Value pill text
        p.setPen(QColor(pal.muted))
        p.drawText(0, 0, w, 18, Qt.AlignRight | Qt.AlignVCenter, self._text)

        # Sunken track
        track = QRectF(0, 24, w, 8)
        p.setPen(Qt.NoPen)
        track_col = QColor(pal.border_soft)
        track_col.setAlpha(180)
        p.setBrush(QBrush(track_col))
        p.drawRoundedRect(track, 4.0, 4.0)

        # Progress fill
        if self._frac > 0:
            fill_w = max(8.0, track.width() * self._frac)
            fill = QRectF(0, 24, fill_w, 8)
            g = QLinearGradient(fill.topLeft(), fill.topRight())

            if self._frac > 0.90:
                g.setColorAt(0.0, QColor(pal.amber))
                g.setColorAt(1.0, QColor(pal.red))
            elif self._frac > 0.75:
                g.setColorAt(0.0, QColor(pal.accent))
                g.setColorAt(1.0, QColor(pal.amber))
            else:
                brand_b = getattr(pal, "brand_b", pal.accent)
                g.setColorAt(0.0, QColor(pal.accent))
                g.setColorAt(1.0, QColor(brand_b))

            p.setBrush(QBrush(g))
            p.drawRoundedRect(fill, 4.0, 4.0)


class CommandSnippet(QFrame):
    """
    A macOS/Linux terminal-styled command card with simulated title bar,
    monospace display, and a 1-click copy button with animated feedback.
    """

    def __init__(self, command: str, title: str = "Live ISO Terminal", parent=None):
        super().__init__(parent)
        self.setObjectName("CommandSnippet")
        self._command = command

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        head = QWidget()
        head.setObjectName("TerminalHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 7, 12, 7)
        hl.setSpacing(8)

        dots = QLabel("●  ●  ●")
        dots.setObjectName("TerminalDots")
        hl.addWidget(dots)

        t = QLabel(title)
        t.setObjectName("TerminalTitle")
        hl.addWidget(t)
        hl.addStretch()

        self.btn_copy = button("Copy", ghost=True)
        self.btn_copy.setFixedWidth(70)
        self.btn_copy.clicked.connect(self._copy_cmd)
        hl.addWidget(self.btn_copy)
        outer.addWidget(head)

        # Command label body
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 12, 14, 14)
        self.cmd_lbl = QLabel(command)
        self.cmd_lbl.setObjectName("Cmd")
        self.cmd_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cmd_lbl.setWordWrap(True)
        bl.addWidget(self.cmd_lbl)
        outer.addWidget(body)

    def set_command(self, command: str) -> None:
        self._command = command
        self.cmd_lbl.setText(command)

    def _copy_cmd(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._command)
        self.btn_copy.setText("✓ Copied!")
        QTimer.singleShot(2000, lambda: self.btn_copy.setText("Copy"))


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
