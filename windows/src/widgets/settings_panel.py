"""Settings panel — model management, GPU info, model downloader."""

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QProgressBar,
    QMessageBox, QFrame, QComboBox, QLineEdit,
)
import torch

from src.backend import (
    MossTTSBackend, MODEL_TTS, MODEL_VOICE_GEN,
    gpu_info, MODELS_DIR, APP_DIR, get_model_size_gb,
)


class ModelLoadWorker(QThread):
    """Load model in background thread."""
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


class ModelDownloadWorker(QThread):
    """Download model from HuggingFace in background thread."""
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
            ok = self.backend.download_model(self.model_name)
            if ok:
                self.finished.emit(True)
            else:
                self.error.emit("Download failed — check model name and connection.")
                self.finished.emit(False)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class SettingsPanel(QWidget):
    """Settings & model management."""

    status_message = Signal(str)

    def __init__(self, backend: MossTTSBackend, dark_mode: bool = True):
        super().__init__()
        self._backend = backend
        self._dark = dark_mode
        self._worker: ModelLoadWorker | None = None
        self._dl_worker: ModelDownloadWorker | None = None

        self._setup_ui()
        self._refresh_gpu_info()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # ── Model Hub (download any HF model) ─────────────
        hub_group = QGroupBox("Model Hub — Download from HuggingFace")
        hub_layout = QVBoxLayout(hub_group)
        hub_layout.setSpacing(6)

        hint = QLabel("Paste any HuggingFace model ID (e.g. OpenMOSS-Team/MOSS-TTS-v1.5)")
        hint.setStyleSheet("color: rgba(128,128,128,0.7); font-size: 11px;")
        hub_layout.addWidget(hint)

        url_row = QHBoxLayout()
        self._hf_input = QLineEdit()
        self._hf_input.setPlaceholderText("OpenMOSS-Team/MOSS-TTS-v1.5")
        self._hf_input.setClearButtonEnabled(True)
        url_row.addWidget(self._hf_input, stretch=1)

        self._dl_btn = QPushButton("Download Model")
        self._dl_btn.setObjectName("accentBtn")
        self._dl_btn.clicked.connect(self._download_model)
        url_row.addWidget(self._dl_btn)
        hub_layout.addLayout(url_row)

        # Download progress
        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 0)
        self._dl_progress.setVisible(False)
        self._dl_progress.setFixedHeight(4)
        self._dl_progress.setTextVisible(False)
        hub_layout.addWidget(self._dl_progress)

        self._dl_status = QLabel(f"Models stored in: {MODELS_DIR}")
        self._dl_status.setStyleSheet("color: rgba(128,128,128,0.6); font-size: 11px;")
        self._dl_status.setWordWrap(True)
        hub_layout.addWidget(self._dl_status)

        layout.addWidget(hub_group)

        # ── Model Management ───────────────────────────────
        model_group = QGroupBox("Model Management")
        model_layout = QVBoxLayout(model_group)
        model_layout.setSpacing(8)

        # Model selector
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Active Model"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItem("MOSS-TTS v1.5 (Voice Cloning)", MODEL_TTS)
        self._model_combo.addItem("MOSS-VoiceGenerator (Voice Design)", MODEL_VOICE_GEN)
        sel_row.addWidget(self._model_combo, stretch=1)
        model_layout.addLayout(sel_row)

        # Load / Unload buttons
        btn_row = QHBoxLayout()
        self._load_btn = QPushButton("Load Model")
        self._load_btn.setObjectName("accentBtn")
        self._load_btn.clicked.connect(self._load_model)

        self._unload_btn = QPushButton("Unload Model")
        self._unload_btn.clicked.connect(self._unload_model)

        btn_row.addWidget(self._load_btn)
        btn_row.addWidget(self._unload_btn)
        btn_row.addStretch()
        model_layout.addLayout(btn_row)

        # Load progress
        self._load_progress = QProgressBar()
        self._load_progress.setRange(0, 0)
        self._load_progress.setVisible(False)
        self._load_progress.setFixedHeight(4)
        self._load_progress.setTextVisible(False)
        model_layout.addWidget(self._load_progress)

        # Status
        self._model_status = QLabel("No model loaded")
        self._model_status.setStyleSheet("color: rgba(128,128,128,0.7); font-size: 12px;")
        self._model_status.setWordWrap(True)
        model_layout.addWidget(self._model_status)

        layout.addWidget(model_group)

        # ── GPU Info ────────────────────────────────────────
        gpu_group = QGroupBox("GPU Information")
        gpu_layout = QVBoxLayout(gpu_group)
        gpu_layout.setSpacing(4)

        self._gpu_labels = {}
        for key, label_text in [
            ("name", "Device"),
            ("vram", "VRAM"),
            ("compute", "Compute Capability"),
            ("cuda", "CUDA Version"),
            ("driver", "Driver"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            value = QLabel("—")
            value.setStyleSheet("color: rgba(128,128,128,0.8); font-size: 12px;")
            row.addWidget(value, stretch=1)
            gpu_layout.addLayout(row)
            self._gpu_labels[key] = value

        self._refresh_gpu_btn = QPushButton("Refresh")
        self._refresh_gpu_btn.clicked.connect(self._refresh_gpu_info)
        gpu_layout.addWidget(self._refresh_gpu_btn)

        layout.addWidget(gpu_group)

        # ── VRAM Usage ──────────────────────────────────────
        vram_group = QGroupBox("VRAM Monitor")
        vram_layout = QVBoxLayout(vram_group)
        self._vram_bar = QProgressBar()
        self._vram_bar.setRange(0, 100)
        self._vram_bar.setValue(0)
        self._vram_bar.setTextVisible(True)
        self._vram_bar.setFormat("VRAM: %p% used")
        vram_layout.addWidget(self._vram_bar)

        self._vram_detail = QLabel("0 MB / 8192 MB")
        self._vram_detail.setAlignment(Qt.AlignCenter)
        self._vram_detail.setStyleSheet("font-size: 12px;")
        vram_layout.addWidget(self._vram_detail)

        layout.addWidget(vram_group)

        # ── Optimization ────────────────────────────────────
        opt_group = QGroupBox("Optimization")
        opt_layout = QVBoxLayout(opt_group)

        self._attn_combo = QComboBox()
        self._attn_combo.addItems(["auto (Flash Attention 2 if available)", "sdpa", "eager"])
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("Attention Backend"))
        opt_row.addWidget(self._attn_combo, stretch=1)
        opt_layout.addLayout(opt_row)

        self._dtype_combo = QComboBox()
        self._dtype_combo.addItems(["bfloat16 (recommended for RTX 30xx)", "float16"])
        dtype_row = QHBoxLayout()
        dtype_row.addWidget(QLabel("Precision"))
        dtype_row.addWidget(self._dtype_combo, stretch=1)
        opt_layout.addLayout(dtype_row)

        layout.addWidget(opt_group)

        layout.addStretch()

        self._update_model_status()

    # ── GPU Info ────────────────────────────────────────────

    def _refresh_gpu_info(self):
        info = gpu_info()
        if info["cuda"]:
            self._gpu_labels["name"].setText(info["name"])
            self._gpu_labels["vram"].setText(
                f"{info['vram_free_gb']:.1f} GB free / {info['vram_total_gb']:.0f} GB total"
            )
            self._gpu_labels["compute"].setText(info["compute_capability"])
            self._gpu_labels["cuda"].setText(info.get("cuda_version", "—"))

            if torch.cuda.is_available():
                used = torch.cuda.memory_allocated() / (1024**3)
                total = info["vram_total_gb"]
                pct = int(used / total * 100) if total > 0 else 0
                self._vram_bar.setValue(pct)
                self._vram_detail.setText(f"{used:.1f} GB / {total:.0f} GB")
        else:
            for label in self._gpu_labels.values():
                label.setText("No GPU detected")

    # ── Model Download ──────────────────────────────────────

    def _download_model(self):
        model_name = self._hf_input.text().strip()
        if not model_name:
            QMessageBox.warning(self, "Missing Model ID",
                                "Enter a HuggingFace model ID (e.g. OpenMOSS-Team/MOSS-TTS-v1.5)")
            return

        self._dl_btn.setEnabled(False)
        self._dl_progress.setVisible(True)
        self._dl_status.setText(f"Downloading {model_name} …")

        self._dl_worker = ModelDownloadWorker(self._backend, model_name)
        self._dl_worker.progress.connect(lambda msg: self._dl_status.setText(msg))
        self._dl_worker.finished.connect(self._on_download_done)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.start()

    def _on_download_done(self, success: bool):
        self._dl_btn.setEnabled(True)
        self._dl_progress.setVisible(False)
        if success:
            model_name = self._hf_input.text().strip()
            self._dl_status.setText(f"✓ Downloaded: {model_name}")

            # Add to combo if not already present
            found = False
            for i in range(self._model_combo.count()):
                if self._model_combo.itemData(i) == model_name:
                    found = True
                    break
            if not found:
                self._model_combo.addItem(model_name, model_name)
                self._model_combo.setCurrentIndex(self._model_combo.count() - 1)

            # Offer to load
            reply = QMessageBox.question(
                self, "Download Complete",
                f"{model_name} downloaded to:\n{MODELS_DIR}\n\nLoad it now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._load_model()
        else:
            self._dl_status.setText("Download failed — check model name and connection.")

    def _on_download_error(self, error: str):
        self._dl_btn.setEnabled(True)
        self._dl_progress.setVisible(False)
        self._dl_status.setText(f"Error: {error}")
        QMessageBox.critical(self, "Download Error", error)

    # ── Model Load / Unload ─────────────────────────────────

    def _load_model(self):
        model_name = self._model_combo.currentData() or self._model_combo.currentText().strip()
        if not model_name:
            return

        self._load_btn.setEnabled(False)
        self._load_progress.setVisible(True)
        self._model_status.setText(f"Loading {model_name} …")

        self._worker = ModelLoadWorker(self._backend, model_name)
        self._worker.progress.connect(lambda msg: self._model_status.setText(msg))
        self._worker.finished.connect(self._on_load_done)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_load_done(self, success: bool):
        self._load_btn.setEnabled(True)
        self._load_progress.setVisible(False)
        self._update_model_status()
        self._refresh_gpu_info()

    def _on_load_error(self, error: str):
        self._load_btn.setEnabled(True)
        self._load_progress.setVisible(False)
        self._model_status.setText(f"Error: {error}")
        QMessageBox.critical(self, "Load Error", error)

    def _unload_model(self):
        self._backend.unload()
        self._update_model_status()
        self._refresh_gpu_info()
        self._model_status.setText("Model unloaded. GPU memory freed.")

    def _update_model_status(self):
        status = self._backend.status()
        if status["loaded"]:
            self._model_status.setText(f"✓ Loaded: {status['model']} | SR: {status['sample_rate']} Hz")
        else:
            self._model_status.setText("No model loaded — download then load from above")

    def update_theme(self, dark: bool):
        self._dark = dark
