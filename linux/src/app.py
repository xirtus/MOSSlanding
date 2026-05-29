"""Mosslanding — Main application window with tabbed interface."""

import sys
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStatusBar, QMessageBox, QScrollArea,
)

from src.widgets.glass_window import GlassWindow
from src.widgets.tts_panel import TTSPanel
from src.widgets.voice_gen_panel import VoiceGenPanel
from src.widgets.settings_panel import SettingsPanel
from src.backend import MossTTSBackend, MODEL_TTS


# ── Detect system theme ────────────────────────────────

def detect_dark_mode() -> bool:
    """Check if system is using dark color scheme."""
    try:
        import subprocess
        result = subprocess.run(
            ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
            capture_output=True, text=True
        )
        scheme = result.stdout.strip().lower()
        return "dark" in scheme
    except Exception:
        pass
    return True  # default dark


# ── Main App ───────────────────────────────────────────

class MosslandingApp:
    """Orchestrates the full Mosslanding application."""

    APP_NAME = "Mosslanding"
    APP_VERSION = "1.0.0"

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setApplicationName(self.APP_NAME)
        self._app.setApplicationVersion(self.APP_VERSION)

        # Set application-wide font
        font = QFont("Inter", 10)
        font.setStyleStrategy(QFont.PreferAntialias)
        self._app.setFont(font)

        # Backend
        self._backend = MossTTSBackend()

        # Detect theme
        self._dark = detect_dark_mode()

        # Main window
        self._window = GlassWindow(dark_mode=self._dark)

        # Build UI
        self._build_ui()

        # Set backend progress → status bar
        self._backend.set_progress_callback(self._on_backend_progress)

    def _build_ui(self):
        content = self._window.content_layout()

        # ── Header ──────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 4)

        # App icon + name
        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        app_title = QLabel("Mosslanding")
        app_title.setStyleSheet("""
            font-size: 24px;
            font-weight: 700;
            letter-spacing: -0.3px;
        """)
        app_subtitle = QLabel("MOSS-TTS Voice Synthesis")
        app_subtitle.setStyleSheet("""
            font-size: 12px;
            color: rgba(128,128,128,0.7);
            font-weight: 400;
        """)
        title_layout.addWidget(app_title)
        title_layout.addWidget(app_subtitle)
        header.addLayout(title_layout)
        header.addStretch()

        # Quick status pill
        self._status_pill = QLabel("● GPU Ready")
        self._status_pill.setStyleSheet("""
            QLabel {
                background: rgba(15, 118, 110, 0.15);
                border-radius: 12px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 500;
                color: #0d9488;
            }
        """)
        header.addWidget(self._status_pill)

        content.addLayout(header)

        # ── Tab widget ──────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().setExpanding(True)

        # Helper to wrap a panel in a scroll area
        def wrap_scrollable(panel: QWidget) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidget(panel)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            return scroll

        # TTS Panel
        self._tts_panel = TTSPanel(self._backend, dark_mode=self._dark)
        self._tabs.addTab(wrap_scrollable(self._tts_panel), "🎙 Voice Cloning")

        # Voice Generator Panel
        self._voice_gen_panel = VoiceGenPanel(self._backend, dark_mode=self._dark)
        self._tabs.addTab(wrap_scrollable(self._voice_gen_panel), "✨ Voice Design")

        # Settings Panel
        self._settings_panel = SettingsPanel(self._backend, dark_mode=self._dark)
        self._tabs.addTab(wrap_scrollable(self._settings_panel), "⚙ Settings")

        # Tab styling
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: transparent;
                padding-top: 4px;
            }
            QTabBar::tab {
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
            }
        """)

        content.addWidget(self._tabs, stretch=1)

        # ── Status bar ──────────────────────────────────
        self._status = QLabel("Ready — load a model from Settings to begin")
        self._status.setStyleSheet("""
            QLabel {
                color: rgba(128,128,128,0.6);
                font-size: 11px;
                padding: 4px 8px;
            }
        """)
        content.addWidget(self._status)

        # Connect signals
        self._tts_panel.status_message.connect(self._status.setText)
        self._voice_gen_panel.status_message.connect(self._status.setText)
        self._settings_panel.status_message.connect(self._status.setText)

        # Monitor VRAM periodically
        self._vram_timer = QTimer()
        self._vram_timer.timeout.connect(self._update_status_pill)
        self._vram_timer.start(5000)  # every 5s

    def _on_backend_progress(self, msg: str):
        self._status.setText(msg)

    def _update_status_pill(self):
        import torch
        if torch.cuda.is_available() and self._backend.is_loaded:
            used = torch.cuda.memory_allocated() / (1024**3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            pct = int(used / total * 100)
            self._status_pill.setText(f"● GPU {used:.1f}/{total:.0f}GB ({pct}%)")
            self._status_pill.setStyleSheet("""
                QLabel {
                    background: rgba(15, 118, 110, 0.15);
                    border-radius: 12px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 500;
                    color: #0d9488;
                }
            """)
        elif torch.cuda.is_available():
            self._status_pill.setText("● GPU Idle")
            self._status_pill.setStyleSheet("""
                QLabel {
                    background: rgba(128, 128, 128, 0.10);
                    border-radius: 12px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 500;
                    color: rgba(128,128,128,0.8);
                }
            """)
        else:
            self._status_pill.setText("● CPU")
            self._status_pill.setStyleSheet("""
                QLabel {
                    background: rgba(220, 38, 38, 0.10);
                    border-radius: 12px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: 500;
                    color: #dc2626;
                }
            """)

    def run(self):
        self._window.show()
        return self._app.exec()
