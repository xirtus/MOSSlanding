"""Solid, readable window with KDE Breeze Dark aesthetics and Apple-inspired layout."""

from typing import Optional

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QApplication,
)


def _kde_rgb_to_hex(rgb_str: str) -> str:
    """Convert KDE 'R,G,B' format to '#RRGGBB' hex."""
    try:
        parts = [int(x.strip()) for x in rgb_str.split(",")]
        if len(parts) == 3:
            return f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
    except (ValueError, AttributeError):
        pass
    return rgb_str  # return as-is if already hex or unparseable


def read_kde_color(group: str, key: str, fallback: str) -> str:
    """Read a color from KDE config, return fallback on failure."""
    try:
        import subprocess
        r = subprocess.run(
            ["kreadconfig6", "--group", group, "--key", key],
            capture_output=True, text=True, timeout=2,
        )
        val = r.stdout.strip()
        if val:
            return _kde_rgb_to_hex(val)
    except Exception:
        pass
    return fallback


def detect_kde_colors() -> dict:
    """Extract KDE's current color scheme."""
    return {
        "window_bg": read_kde_color("Colors:Window", "BackgroundNormal", "#1b1b1e"),
        "window_fg": read_kde_color("Colors:Window", "ForegroundNormal", "#eff0f1"),
        "view_bg":   read_kde_color("Colors:View",  "BackgroundNormal", "#252528"),
        "view_fg":   read_kde_color("Colors:View",  "ForegroundNormal", "#eff0f1"),
        "button_bg": read_kde_color("Colors:Button","BackgroundNormal", "#313135"),
        "button_fg": read_kde_color("Colors:Button","ForegroundNormal", "#eff0f1"),
        "accent":    read_kde_color("Colors:Selection","BackgroundNormal", "#0d9488"),
        "accent_fg": read_kde_color("Colors:Selection","ForegroundNormal", "#ffffff"),
        "hover_bg":  read_kde_color("Colors:Window", "DecorationHover", "#3d3d42"),
    }


class GlassWindow(QMainWindow):
    """Solid, readable frameless window with Apple-inspired layout.

    Uses either detected KDE Breeze colors or a built-in dark palette
    that's highly readable — no translucency gimmicks.
    """

    MIN_WIDTH = 900
    MIN_HEIGHT = 650
    DEFAULT_WIDTH = 960
    DEFAULT_HEIGHT = 720

    def __init__(self, dark_mode: bool = True):
        super().__init__()

        self._dark = dark_mode
        self._old_pos: Optional[QPoint] = None

        # Read KDE colors or use built-in dark palette
        self._colors = detect_kde_colors() if dark_mode else {
            "window_bg": "#e8e8ec",
            "window_fg": "#1b1b1e",
            "view_bg":   "#f4f4f8",
            "view_fg":   "#1b1b1e",
            "button_bg": "#e0e0e5",
            "button_fg": "#1b1b1e",
            "accent":    "#0d9488",
            "accent_fg": "#ffffff",
            "hover_bg":  "#d4d4d9",
        }

        self.setWindowTitle("Mosslanding")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        # Frameless but SOLID background
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
        )

        # CRITICAL: solid window, no translucency
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)

        # Apply system palette
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(self._colors["window_bg"]))
        pal.setColor(QPalette.WindowText, QColor(self._colors["window_fg"]))
        pal.setColor(QPalette.Base, QColor(self._colors["view_bg"]))
        pal.setColor(QPalette.Text, QColor(self._colors["view_fg"]))
        pal.setColor(QPalette.Button, QColor(self._colors["button_bg"]))
        pal.setColor(QPalette.ButtonText, QColor(self._colors["button_fg"]))
        pal.setColor(QPalette.Highlight, QColor(self._colors["accent"]))
        pal.setColor(QPalette.HighlightedText, QColor(self._colors["accent_fg"]))
        self.setPalette(pal)

        # Central widget (solid)
        self._central = QWidget()
        self._central.setObjectName("glassRoot")
        self._central.setAutoFillBackground(True)
        self.setCentralWidget(self._central)

        self._root_layout = QVBoxLayout(self._central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Title bar
        self._titlebar = self._create_titlebar()
        self._root_layout.addWidget(self._titlebar)

        # Content area
        self._content = QWidget()
        self._content.setObjectName("contentArea")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 8, 16, 16)
        self._content_layout.setSpacing(10)
        self._root_layout.addWidget(self._content, stretch=1)

        self._apply_stylesheet()

    # ── Title bar ───────────────────────────────────────

    def _create_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titlebar")
        bar.setFixedHeight(36)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(6)

        for color, slot in [
            ("#ed6a5e", self.close),
            ("#f5bd4f", self.showMinimized),
            ("#61c454", self._toggle_maximize),
        ]:
            btn = QPushButton()
            btn.setFixedSize(13, 13)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    border: none;
                    border-radius: 7px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    border: 2px solid rgba(0,0,0,0.18);
                }}
            """)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addSpacing(8)

        title = QLabel("Mosslanding")
        title.setObjectName("titlebarTitle")
        layout.addWidget(title)
        layout.addStretch()

        theme_btn = QPushButton("☀" if self._dark else "\U0001F319")
        theme_btn.setObjectName("tb_theme")
        theme_btn.setFixedSize(26, 26)
        theme_btn.setCursor(Qt.PointingHandCursor)
        theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(theme_btn)

        return bar

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── Mouse dragging ──────────────────────────────────

    def mousePressEvent(self, event):
        if event.position().y() < 36:
            self._old_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._old_pos is not None:
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.pos() + delta)
            self._old_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._old_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.position().y() < 36:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    # ── Theme ───────────────────────────────────────────

    def toggle_theme(self):
        self._dark = not self._dark
        self._colors = detect_kde_colors() if self._dark else {
            "window_bg": "#e8e8ec",
            "window_fg": "#1b1b1e",
            "view_bg":   "#f4f4f8",
            "view_fg":   "#1b1b1e",
            "button_bg": "#e0e0e5",
            "button_fg": "#1b1b1e",
            "accent":    "#0d9488",
            "accent_fg": "#ffffff",
            "hover_bg":  "#d4d4d9",
        }
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(self._colors["window_bg"]))
        pal.setColor(QPalette.WindowText, QColor(self._colors["window_fg"]))
        pal.setColor(QPalette.Base, QColor(self._colors["view_bg"]))
        pal.setColor(QPalette.Text, QColor(self._colors["view_fg"]))
        pal.setColor(QPalette.Button, QColor(self._colors["button_bg"]))
        pal.setColor(QPalette.ButtonText, QColor(self._colors["button_fg"]))
        pal.setColor(QPalette.Highlight, QColor(self._colors["accent"]))
        pal.setColor(QPalette.HighlightedText, QColor(self._colors["accent_fg"]))
        self.setPalette(pal)
        self._apply_stylesheet()

    @property
    def is_dark(self) -> bool:
        return self._dark

    def _apply_stylesheet(self):
        c = self._colors
        bg = c["window_bg"]
        fg = c["window_fg"]
        vbg = c["view_bg"]
        bbg = c["button_bg"]
        bfg = c["button_fg"]
        accent = c["accent"]
        afg = c["accent_fg"]
        hover = c["hover_bg"]

        # Derive border + muted from bg/fg
        border = QColor(bg).lighter(120).name() if self._dark else QColor(bg).darker(115).name()
        mc = QColor(fg)
        mc.setAlpha(140)
        muted_str = f"rgba({mc.red()},{mc.green()},{mc.blue()},0.55)"

        card_bg = QColor(bg).lighter(108).name() if self._dark else QColor(bg).darker(103).name()
        input_bg = vbg

        self._central.setStyleSheet(f"""
            #glassRoot {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            #titlebar {{
                background-color: transparent;
            }}
            #titlebarTitle {{
                color: {muted_str};
                font-size: 12px;
                font-weight: 500;
            }}
            #contentArea {{
                background-color: transparent;
            }}
            QWidget {{
                color: {fg};
                font-family: "SF Pro Display", "Inter", "Noto Sans", sans-serif;
                font-size: 13px;
            }}
            QLabel {{
                color: {fg};
                background: transparent;
            }}
            QPushButton {{
                background-color: {bbg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px 18px;
                color: {bfg};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {bbg};
            }}
            QPushButton#accentBtn {{
                background-color: {accent};
                border: none;
                color: {afg};
                font-weight: 600;
            }}
            QPushButton#accentBtn:hover {{
                background-color: {QColor(accent).darker(108).name()};
            }}
            QPushButton#accentBtn:disabled {{
                background-color: {QColor(accent).darker(140).name()};
                color: {QColor(afg).darker(130).name()};
            }}
            QTextEdit, QPlainTextEdit, QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 10px 14px;
                color: {fg};
                selection-background-color: {accent};
            }}
            QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {{
                border: 1px solid {accent};
            }}
            QComboBox {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px 12px;
                color: {fg};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 8px;
                selection-background-color: {accent};
                selection-color: {afg};
            }}
            QSlider::groove:horizontal {{
                height: 5px;
                background-color: {card_bg};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                height: 16px;
                margin: -6px 0;
                background-color: {accent};
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background-color: {accent};
                border-radius: 3px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {muted_str};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {muted_str};
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QTabWidget::pane {{
                background: transparent;
                border: none;
            }}
            QTabBar::tab {{
                background: transparent;
                border: none;
                padding: 10px 20px;
                color: {muted_str};
                font-weight: 500;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                color: {fg};
                border-bottom: 2px solid {accent};
            }}
            QCheckBox {{
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1.5px solid {border};
                background-color: {input_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
            QGroupBox {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 12px;
                margin-top: 8px;
                padding: 16px 12px 12px 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: {muted_str};
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {fg};
            }}
            QProgressBar {{
                background-color: {card_bg};
                border: none;
                border-radius: 2px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 2px;
            }}
            QSplitter::handle {{
                background-color: {border};
                width: 1px;
            }}
        """)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout
