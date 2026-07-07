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
        gpu_layout.setSpacing(6)

        self._gpu_labels = {}
        self._gpu_container = QWidget()
        self._gpu_container_layout = QVBoxLayout(self._gpu_container)
        self._gpu_container_layout.setContentsMargins(0, 0, 0, 0)
        self._gpu_container_layout.setSpacing(8)
        gpu_layout.addWidget(self._gpu_container)

        self._cuda_version_label = QLabel("—")
        self._cuda_version_label.setStyleSheet("color: rgba(128,128,128,0.8); font-size: 11px;")
        cuda_row = QHBoxLayout()
        cuda_row.addWidget(QLabel("CUDA Version"))
        cuda_row.addWidget(self._cuda_version_label, stretch=1)
        gpu_layout.addLayout(cuda_row)

        self._refresh_gpu_btn = QPushButton("Refresh")
        self._refresh_gpu_btn.clicked.connect(self._refresh_gpu_info)
        gpu_layout.addWidget(self._refresh_gpu_btn)

        layout.addWidget(gpu_group)

        # ── VRAM Usage (per-GPU) ────────────────────────────
        self._vram_group = QGroupBox("VRAM Monitor")
        self._vram_layout = QVBoxLayout(self._vram_group)
        self._vram_layout.setSpacing(6)
        self._vram_bars: list[tuple[QLabel, QProgressBar, QLabel]] = []
        layout.addWidget(self._vram_group)

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
        # Clear previous GPU widgets
        while self._gpu_container_layout.count():
            item = self._gpu_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear VRAM bars
        while self._vram_layout.count():
            item = self._vram_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._vram_bars.clear()

        info = gpu_info()
        if info["cuda"]:
            self._cuda_version_label.setText(info.get("cuda_version", "—"))

            for gpu in info.get("gpus", []):
                idx = gpu["index"]
                gpu_frame = QFrame()
                gpu_frame.setFrameShape(QFrame.StyledPanel)
                gpu_frame.setStyleSheet("QFrame { border: 1px solid rgba(128,128,128,0.15); border-radius: 6px; padding: 6px; }")
                gpu_box = QVBoxLayout(gpu_frame)
                gpu_box.setSpacing(2)

                name_row = QHBoxLayout()
                name_label = QLabel(f"GPU {idx}: {gpu['name']}")
                name_label.setStyleSheet("font-weight: 600; font-size: 12px;")
                name_row.addWidget(name_label)
                name_row.addStretch()
                gpu_box.addLayout(name_row)

                vram_label = QLabel(
                    f"VRAM: {gpu['vram_free_gb']:.1f} GB free / {gpu['vram_total_gb']:.0f} GB total"
                )
                vram_label.setStyleSheet("color: rgba(128,128,128,0.8); font-size: 11px;")
                gpu_box.addWidget(vram_label)

                cc_label = QLabel(f"Compute: {gpu['compute_capability']}")
                cc_label.setStyleSheet("color: rgba(128,128,128,0.7); font-size: 11px;")
                gpu_box.addWidget(cc_label)

                self._gpu_container_layout.addWidget(gpu_frame)

            # Per-GPU VRAM bars
            for gpu in info.get("gpus", []):
                idx = gpu["index"]
                gpu_vram_row = QHBoxLayout()

                gpu_label = QLabel(f"GPU {idx}")
                gpu_label.setStyleSheet("font-size: 11px; font-weight: 600;")
                gpu_label.setFixedWidth(48)
                gpu_vram_row.addWidget(gpu_label)

                bar = QProgressBar()
                bar.setRange(0, 100)
                allocated = gpu.get("vram_allocated_gb", 0)
                total = gpu["vram_total_gb"]
                pct = int(allocated / total * 100) if total > 0 else 0
                bar.setValue(pct)
                bar.setTextVisible(True)
                bar.setFormat(f"{allocated:.1f}/{total:.0f} GB (%p%)")
                gpu_vram_row.addWidget(bar, stretch=1)

                detail_label = QLabel("")
                detail_label.setStyleSheet("font-size: 10px; color: rgba(128,128,128,0.6);")
                detail_label.setFixedWidth(60)
                gpu_vram_row.addWidget(detail_label)

                self._vram_layout.addLayout(gpu_vram_row)
                self._vram_bars.append((gpu_label, bar, detail_label))

            # Legacy compat — keep _gpu_labels functioning for any old code
            self._gpu_labels["name"] = QLabel(info.get("name", ""))
            # Hide these since we show them in the per-GPU frames
        else:
            no_gpu = QLabel("No GPU detected — running on CPU")
            no_gpu.setStyleSheet("color: rgba(220,38,38,0.8); font-size: 12px;")
            self._gpu_container_layout.addWidget(no_gpu)
            self._cuda_version_label.setText("—")

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
