"""TTS Voice Cloning Panel — the main synthesis interface."""

import os
import numpy as np
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QComboBox, QSlider,
    QCheckBox, QFileDialog, QGroupBox, QSpinBox,
    QDoubleSpinBox, QProgressBar, QMessageBox,
    QFrame, QSplitter, QSizePolicy, QScrollArea,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "audio"


class InferenceWorker(QThread):
    """Runs TTS inference in a background thread."""
    finished = Signal(object)   # (sample_rate, audio_array) or None on error
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, backend, **kwargs):
        super().__init__()
        self.backend = backend
        self.kwargs = kwargs

    def run(self):
        try:
            self.progress.emit("Starting inference ...")
            result = self.backend.generate_tts(**self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class TTSPanel(QWidget):
    """Voice cloning & TTS synthesis panel."""

    # Signal for status bar updates
    status_message = Signal(str)

    def __init__(self, backend, dark_mode: bool = True):
        super().__init__()
        self._backend = backend
        self._dark = dark_mode
        self._worker: InferenceWorker | None = None
        self._player: QMediaPlayer | None = None
        self._audio_output: QAudioOutput | None = None
        self._last_audio: tuple[int, np.ndarray] | None = None

        self._setup_ui()
        self._setup_player()

    def _setup_player(self):
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Top row: Text input + audio output ──────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # -- Left: Text input --
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Mode selector
        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode")
        mode_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Clone Voice", "Direct Generation", "Continuation", "Continue + Clone"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self._mode_combo, stretch=1)
        left_layout.addLayout(mode_row)

        # Reference audio
        ref_row = QHBoxLayout()
        ref_label = QLabel("Reference")
        ref_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._ref_path_label = QLabel("No file selected")
        self._ref_path_label.setStyleSheet("color: rgba(128,128,128,0.8); font-size: 11px;")
        self._ref_path_label.setWordWrap(True)
        self._ref_browse_btn = QPushButton("Browse")
        self._ref_browse_btn.setFixedWidth(70)
        self._ref_browse_btn.clicked.connect(self._browse_reference)
        ref_row.addWidget(ref_label)
        ref_row.addWidget(self._ref_path_label, stretch=1)
        ref_row.addWidget(self._ref_browse_btn)
        left_layout.addLayout(ref_row)

        self._ref_path: str | None = None

        # Language tag
        lang_row = QHBoxLayout()
        lang_label = QLabel("Language")
        lang_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._lang_combo = QComboBox()
        self._lang_combo.addItems([
            "Auto (detect)", "Chinese", "Cantonese", "English", "Arabic",
            "Czech", "Danish", "Dutch", "Finnish", "French", "German",
            "Greek", "Hebrew", "Hindi", "Hungarian", "Italian",
            "Japanese", "Korean", "Macedonian", "Malay", "Persian (Farsi)",
            "Polish", "Portuguese", "Romanian", "Russian", "Spanish",
            "Swahili", "Swedish", "Tagalog", "Thai", "Turkish", "Vietnamese",
        ])
        lang_row.addWidget(lang_label)
        lang_row.addWidget(self._lang_combo, stretch=1)
        left_layout.addLayout(lang_row)

        # Text input
        text_label = QLabel("Text to Speak")
        text_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Type or paste the text you want to synthesize here...")
        self._text_edit.setMinimumHeight(120)
        self._text_edit.setAcceptRichText(False)
        left_layout.addWidget(text_label)
        left_layout.addWidget(self._text_edit, stretch=1)

        splitter.addWidget(left)

        # -- Right: Output & controls --
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Audio output area
        out_label = QLabel("Output")
        out_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        right_layout.addWidget(out_label)

        self._output_frame = QFrame()
        self._output_frame.setObjectName("outputFrame")
        self._output_frame.setMinimumHeight(80)
        out_frame_layout = QVBoxLayout(self._output_frame)
        out_frame_layout.setAlignment(Qt.AlignCenter)

        self._output_status = QLabel("Ready — generate speech to play here")
        self._output_status.setAlignment(Qt.AlignCenter)
        self._output_status.setStyleSheet("color: rgba(128,128,128,0.7); font-size: 12px;")
        out_frame_layout.addWidget(self._output_status)

        # Playback controls
        pb_row = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setObjectName("accentBtn")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._play_audio)

        self._save_btn = QPushButton("↓ Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_audio)

        self._duration_label = QLabel("")
        self._duration_label.setStyleSheet("color: rgba(128,128,128,0.6); font-size: 11px;")

        pb_row.addWidget(self._play_btn)
        pb_row.addWidget(self._save_btn)
        pb_row.addWidget(self._duration_label)
        pb_row.addStretch()
        out_frame_layout.addLayout(pb_row)

        right_layout.addWidget(self._output_frame)

        # Generation settings
        settings_group = QGroupBox("Generation Settings")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(6)

        # Temperature
        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("Temperature"))
        self._temp_slider = QSlider(Qt.Horizontal)
        self._temp_slider.setRange(10, 300)
        self._temp_slider.setValue(170)
        self._temp_label = QLabel("1.70")
        self._temp_label.setFixedWidth(36)
        self._temp_label.setAlignment(Qt.AlignRight)
        self._temp_slider.valueChanged.connect(lambda v: self._temp_label.setText(f"{v/100:.2f}"))
        t_row.addWidget(self._temp_slider)
        t_row.addWidget(self._temp_label)
        settings_layout.addLayout(t_row)

        # Top-p
        tp_row = QHBoxLayout()
        tp_row.addWidget(QLabel("Top-P"))
        self._top_p_slider = QSlider(Qt.Horizontal)
        self._top_p_slider.setRange(10, 100)
        self._top_p_slider.setValue(80)
        self._top_p_label = QLabel("0.80")
        self._top_p_label.setFixedWidth(36)
        self._top_p_label.setAlignment(Qt.AlignRight)
        self._top_p_slider.valueChanged.connect(lambda v: self._top_p_label.setText(f"{v/100:.2f}"))
        tp_row.addWidget(self._top_p_slider)
        tp_row.addWidget(self._top_p_label)
        settings_layout.addLayout(tp_row)

        # Top-K
        tk_row = QHBoxLayout()
        tk_row.addWidget(QLabel("Top-K"))
        self._top_k_slider = QSlider(Qt.Horizontal)
        self._top_k_slider.setRange(1, 200)
        self._top_k_slider.setValue(25)
        self._top_k_label = QLabel("25")
        self._top_k_label.setFixedWidth(36)
        self._top_k_label.setAlignment(Qt.AlignRight)
        self._top_k_slider.valueChanged.connect(lambda v: self._top_k_label.setText(str(v)))
        tk_row.addWidget(self._top_k_slider)
        tk_row.addWidget(self._top_k_label)
        settings_layout.addLayout(tk_row)

        # Repetition penalty
        rp_row = QHBoxLayout()
        rp_row.addWidget(QLabel("Rep. Penalty"))
        self._rep_pen_slider = QSlider(Qt.Horizontal)
        self._rep_pen_slider.setRange(80, 200)
        self._rep_pen_slider.setValue(100)
        self._rep_pen_label = QLabel("1.00")
        self._rep_pen_label.setFixedWidth(36)
        self._rep_pen_label.setAlignment(Qt.AlignRight)
        self._rep_pen_slider.valueChanged.connect(lambda v: self._rep_pen_label.setText(f"{v/100:.2f}"))
        rp_row.addWidget(self._rep_pen_slider)
        rp_row.addWidget(self._rep_pen_label)
        settings_layout.addLayout(rp_row)

        # Max tokens
        mt_row = QHBoxLayout()
        mt_row.addWidget(QLabel("Max Tokens"))
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 8192)
        self._max_tokens_spin.setValue(4096)
        self._max_tokens_spin.setSingleStep(128)
        mt_row.addWidget(self._max_tokens_spin)
        mt_row.addStretch()
        settings_layout.addLayout(mt_row)

        # Duration control
        self._duration_check = QCheckBox("Enable Duration Control")
        self._duration_check.setChecked(False)
        self._duration_tokens_spin = QSpinBox()
        self._duration_tokens_spin.setRange(1, 8192)
        self._duration_tokens_spin.setValue(256)
        self._duration_tokens_spin.setEnabled(False)
        self._duration_check.toggled.connect(self._duration_tokens_spin.setEnabled)

        dur_row = QHBoxLayout()
        dur_row.addWidget(self._duration_check)
        dur_row.addWidget(QLabel("Tokens"))
        dur_row.addWidget(self._duration_tokens_spin)
        dur_row.addStretch()
        settings_layout.addLayout(dur_row)

        # Quick token presets (~approx duration at 24 kHz)
        preset_row = QHBoxLayout()
        preset_label = QLabel("Quick Presets")
        preset_label.setStyleSheet("font-size: 11px; color: rgba(128,128,128,0.7);")
        preset_row.addWidget(preset_label)
        for t in [256, 512, 1024, 2048, 4096]:
            btn = QPushButton(str(t))
            btn.setFixedWidth(48)
            btn.setFixedHeight(22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, v=t: self._set_duration_token(v))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        settings_layout.addLayout(preset_row)

        right_layout.addWidget(settings_group)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        right_layout.addWidget(self._progress)

        # Generate button
        self._generate_btn = QPushButton("✦ Generate Speech")
        self._generate_btn.setObjectName("accentBtn")
        self._generate_btn.setMinimumHeight(42)
        self._generate_btn.setStyleSheet(self._generate_btn.styleSheet() + """
            QPushButton#accentBtn {
                font-size: 15px;
                font-weight: 600;
                border-radius: 12px;
            }
        """)
        self._generate_btn.clicked.connect(self._on_generate)
        right_layout.addWidget(self._generate_btn)

        # Wrap right side in scroll area for small windows
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        splitter.addWidget(right_scroll)
        splitter.setSizes([420, 400])
        layout.addWidget(splitter)

    # ── Duration preset ──────────────────────────────────

    def _set_duration_token(self, value: int):
        """Quick-set the duration tokens spinbox from a preset button."""
        self._duration_check.setChecked(True)
        self._duration_tokens_spin.setValue(value)

    # ── Mode handling ───────────────────────────────────

    def _on_mode_changed(self, index: int):
        modes_need_ref = {0: True, 2: True, 3: True}  # clone, continue, cont+clone
        needs_ref = modes_need_ref.get(index, False)
        self._ref_browse_btn.setEnabled(needs_ref)
        if not needs_ref:
            self._ref_path = None
            self._ref_path_label.setText("No reference needed")

    def _browse_reference(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Audio",
            str(ASSETS_DIR),
            "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a);;All Files (*)"
        )
        if path:
            self._ref_path = path
            self._ref_path_label.setText(os.path.basename(path))

    # ── Generate ────────────────────────────────────────

    def _on_generate(self):
        text = self._text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Text", "Please enter text to synthesize.")
            return

        if not self._backend.is_loaded:
            reply = QMessageBox.question(
                self, "Model Not Loaded",
                "Model is not loaded yet. Load it now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    self._backend.load_model()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to load model:\n{e}")
                    return
            else:
                return

        mode_idx = self._mode_combo.currentIndex()
        mode_map = {0: "clone", 1: "direct", 2: "continue", 3: "continue_clone"}
        mode = mode_map.get(mode_idx, "clone")

        lang = self._lang_combo.currentText()
        if lang == "Auto (detect)":
            lang = None

        duration_tokens = None
        if self._duration_check.isChecked():
            duration_tokens = self._duration_tokens_spin.value()

        kwargs = {
            "text": text,
            "reference_audio": self._ref_path if mode != "direct" else None,
            "mode": mode,
            "language_tag": lang,
            "duration_tokens": duration_tokens,
            "temperature": self._temp_slider.value() / 100.0,
            "top_p": self._top_p_slider.value() / 100.0,
            "top_k": self._top_k_slider.value(),
            "repetition_penalty": self._rep_pen_slider.value() / 100.0,
            "max_new_tokens": self._max_tokens_spin.value(),
        }

        self._generate_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._output_status.setText("Generating ...")

        self._worker = InferenceWorker(self._backend, **kwargs)
        self._worker.finished.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(lambda msg: self._output_status.setText(msg))
        self._worker.start()

    def _on_result(self, result):
        self._generate_btn.setEnabled(True)
        self._progress.setVisible(False)

        if result is None:
            self._output_status.setText("Generation failed.")
            return

        sr, audio = result
        self._last_audio = (sr, audio)

        duration_s = len(audio) / sr
        self._duration_label.setText(f"{duration_s:.1f}s")
        self._output_status.setText(f"✓ Generated {duration_s:.1f}s of audio @ {sr}Hz")
        self._play_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        # Auto-play
        self._play_audio()

    def _on_error(self, error_msg: str):
        self._generate_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._output_status.setText(f"✗ Error: {error_msg}")
        QMessageBox.critical(self, "Generation Error", error_msg)

    # ── Playback ────────────────────────────────────────

    def _play_audio(self):
        if self._last_audio is None:
            return

        sr, audio = self._last_audio
        # Write to temp file for QMediaPlayer
        import tempfile
        import soundfile as sf

        tmp_path = os.path.join(tempfile.gettempdir(), "mosslanding_output.wav")
        sf.write(tmp_path, audio, sr)

        self._player.setSource(QUrl.fromLocalFile(tmp_path))
        self._player.play()

    def _save_audio(self):
        if self._last_audio is None:
            return

        sr, audio = self._last_audio
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio",
            os.path.expanduser("~/mosslanding_output.wav"),
            "WAV Files (*.wav);;FLAC Files (*.flac);;All Files (*)"
        )
        if path:
            import soundfile as sf
            sf.write(path, audio, sr)
            self._output_status.setText(f"Saved to {path}")

    def update_theme(self, dark: bool):
        self._dark = dark
