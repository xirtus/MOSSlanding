"""Voice Generator Panel — design voices from text instructions."""

import os
import tempfile

import numpy as np
import soundfile as sf

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QSlider,
    QGroupBox, QSpinBox, QProgressBar,
    QMessageBox, QFileDialog, QSplitter,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class ModelLoadWorker(QThread):
    """Loads a model in background so the UI stays responsive."""
    finished = Signal(bool)
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, backend, model_name: str):
        super().__init__()
        self.backend = backend
        self.model_name = model_name

    def run(self):
        try:
            self.backend.set_progress_callback(lambda msg: self.progress.emit(msg))
            self.backend.load_model(self.model_name)
            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class VoiceGenWorker(QThread):
    """Runs voice design inference in background."""
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, backend, **kwargs):
        super().__init__()
        self.backend = backend
        self.kwargs = kwargs

    def run(self):
        try:
            self.progress.emit("Designing voice ...")
            result = self.backend.generate_voice(**self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class VoiceGenPanel(QWidget):
    """Instruction-based voice design panel."""

    status_message = Signal(str)

    EXAMPLE_INSTRUCTIONS = [
        "Warm, gentle female narrator voice with calm pacing and clear articulation.",
        "Deep, authoritative male voice with a dramatic, cinematic tone.",
        "Bright and energetic young female voice, fast-paced and cheerful.",
        "Soft, whispery ASMR voice with slow, deliberate delivery.",
        "Robotic, synthesized voice with a monotone delivery.",
        "Elderly wise man voice, slow and thoughtful with rich timbre.",
        "Child-like innocent voice, high-pitched and playful.",
    ]

    def __init__(self, backend, dark_mode: bool = True):
        super().__init__()
        self._backend = backend
        self._dark = dark_mode
        self._worker: VoiceGenWorker | None = None
        self._loader: ModelLoadWorker | None = None
        self._pending_generation: bool = False
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.8)
        self._last_audio: tuple[int, np.ndarray] | None = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        # -- Left --
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        instr_label = QLabel("Voice Instruction")
        instr_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        self._instr_edit = QTextEdit()
        self._instr_edit.setPlaceholderText(
            "Describe the voice you want...\n"
            "e.g. 'Warm, gentle female narrator voice with calm pacing and clear articulation.'"
        )
        self._instr_edit.setMinimumHeight(90)
        left_layout.addWidget(instr_label)
        left_layout.addWidget(self._instr_edit)

        # Quick examples
        ex_label = QLabel("Quick Presets")
        ex_label.setStyleSheet("font-weight: 600; font-size: 11px; color: rgba(128,128,128,0.8);")
        left_layout.addWidget(ex_label)
        for i, example in enumerate(self.EXAMPLE_INSTRUCTIONS[:5]):
            btn = QPushButton(f"  {example[:80]}...")
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 6px 10px;
                    font-size: 11px;
                    border-radius: 6px;
                }
            """)
            btn.clicked.connect(lambda checked, e=example: self._instr_edit.setText(e))
            left_layout.addWidget(btn)

        # Text to speak
        text_label = QLabel("Text to Speak")
        text_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Enter the text content for the designed voice to read...")
        self._text_edit.setMinimumHeight(120)
        left_layout.addWidget(text_label)
        left_layout.addWidget(self._text_edit, stretch=1)

        splitter.addWidget(left)

        # -- Right --
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Output status
        out_label = QLabel("Output")
        out_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        right_layout.addWidget(out_label)

        self._status = QLabel("Ready — enter instruction and text to design a voice")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("padding: 20px; color: rgba(128,128,128,0.7); font-size: 12px;")
        right_layout.addWidget(self._status)

        # Playback
        pb_row = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setObjectName("accentBtn")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._play)

        self._save_btn = QPushButton("↓ Save")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)

        self._dur_label = QLabel("")
        self._dur_label.setStyleSheet("color: rgba(128,128,128,0.6); font-size: 11px;")

        pb_row.addWidget(self._play_btn)
        pb_row.addWidget(self._save_btn)
        pb_row.addWidget(self._dur_label)
        pb_row.addStretch()
        right_layout.addLayout(pb_row)

        # Settings
        settings = QGroupBox("Generation Settings")
        s_layout = QVBoxLayout(settings)
        s_layout.setSpacing(4)

        for name, key, rng, default in [
            ("Temperature", "temp", (10, 300), 150),
            ("Top-P", "top_p", (10, 100), 60),
            ("Top-K", "top_k", (1, 200), 50),
            ("Rep. Penalty", "rep_pen", (80, 200), 110),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            slider = QSlider(Qt.Horizontal)
            slider.setRange(*rng)
            slider.setValue(default)
            label = QLabel(f"{default/100:.2f}" if rng[1] <= 300 else str(default))
            label.setFixedWidth(36)
            label.setAlignment(Qt.AlignRight)
            slider.valueChanged.connect(lambda v, l=label, r=rng: (
                l.setText(f"{v/100:.2f}") if r[1] <= 300 else l.setText(str(v))
            ))
            row.addWidget(slider)
            row.addWidget(label)
            s_layout.addLayout(row)
            setattr(self, f"_{key}_slider", slider)

        mt_row = QHBoxLayout()
        mt_row.addWidget(QLabel("Max Tokens"))
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 8192)
        self._max_tokens_spin.setValue(2048)
        self._max_tokens_spin.setSingleStep(128)
        mt_row.addWidget(self._max_tokens_spin)
        mt_row.addStretch()
        s_layout.addLayout(mt_row)

        right_layout.addWidget(settings)

        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([440, 380])
        layout.addWidget(splitter)

        # ── Bottom bar: progress + generate (always visible) ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # Generate
        self._gen_btn = QPushButton("✦ Design Voice")
        self._gen_btn.setObjectName("accentBtn")
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.setMinimumHeight(44)
        self._gen_btn.clicked.connect(self._generate)
        layout.addWidget(self._gen_btn)

    def _generate(self):
        text = self._text_edit.toPlainText().strip()
        instruction = self._instr_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Text", "Please enter text.")
            return
        if not instruction:
            QMessageBox.warning(self, "Empty Instruction", "Please enter a voice instruction.")
            return

        if not self._backend.is_loaded:
            reply = QMessageBox.question(
                self, "Model Not Loaded",
                "Voice Generator model is not loaded. Load it now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._do_load_then_generate()
            return

        self._start_inference()

    def _do_load_then_generate(self):
        """Load VoiceGenerator in background, then auto-generate."""
        self._pending_generation = True
        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Loading Voice Generator model …")

        from src.backend import MODEL_VOICE_GEN
        self._loader = ModelLoadWorker(self._backend, MODEL_VOICE_GEN)
        self._loader.progress.connect(lambda msg: self._status.setText(msg))
        self._loader.finished.connect(self._on_load_for_generate_done)
        self._loader.error.connect(self._on_load_for_generate_error)
        self._loader.start()

    def _on_load_for_generate_done(self, success: bool):
        self._loader = None
        if not success:
            self._gen_btn.setEnabled(True)
            self._progress.setVisible(False)
            return
        if self._pending_generation:
            self._pending_generation = False
            self._start_inference()

    def _on_load_for_generate_error(self, error: str):
        self._loader = None
        self._pending_generation = False
        self._gen_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status.setText(f"✗ Load error: {error}")
        QMessageBox.critical(self, "Error", error)

    def _start_inference(self):
        """Launch voice design inference (model must already be loaded)."""
        text = self._text_edit.toPlainText().strip()
        instruction = self._instr_edit.toPlainText().strip()

        kwargs = {
            "text": text,
            "instruction": instruction,
            "temperature": self._temp_slider.value() / 100.0,
            "top_p": self._top_p_slider.value() / 100.0,
            "top_k": self._top_k_slider.value(),
            "repetition_penalty": self._rep_pen_slider.value() / 100.0,
            "max_new_tokens": self._max_tokens_spin.value(),
        }

        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Designing voice …")

        self._worker = VoiceGenWorker(self._backend, **kwargs)
        self._worker.finished.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(lambda m: self._status.setText(m))
        self._worker.start()

    def _on_result(self, result):
        self._gen_btn.setEnabled(True)
        self._progress.setVisible(False)
        if result is None:
            self._status.setText("Generation failed.")
            return

        sr, audio = result
        self._last_audio = (sr, audio)
        dur = len(audio) / sr
        self._dur_label.setText(f"{dur:.1f}s")
        self._status.setText(f"✓ Voice designed — {dur:.1f}s @ {sr}Hz")
        self._play_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._play()

    def _on_error(self, msg):
        self._gen_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status.setText(f"✗ {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _play(self):
        if self._last_audio is None:
            return
        sr, audio = self._last_audio
        tmp = os.path.join(tempfile.gettempdir(), "mosslanding_voice.wav")
        sf.write(tmp, audio, sr)
        self._player.setSource(QUrl.fromLocalFile(tmp))
        self._player.play()

    def _save(self):
        if self._last_audio is None:
            return
        sr, audio = self._last_audio
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Audio",
            os.path.expanduser("~/mosslanding_voice.wav"),
            "WAV Files (*.wav);;FLAC Files (*.flac);;All Files (*)"
        )
        if path:
            sf.write(path, audio, sr)
            self._status.setText(f"Saved to {path}")

    def update_theme(self, dark: bool):
        self._dark = dark
