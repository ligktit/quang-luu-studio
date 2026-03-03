"""
Main Window — Application window with controls and the waveform visualizer.
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QCheckBox, QFrame,
    QStatusBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor

from audio_capture import AudioCaptureThread
from audio_processor import AudioProcessor
from visualizer_widget import WaveformWidget


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("♪ Waveform Visualizer")
        self.setMinimumSize(900, 550)
        self.resize(1100, 650)

        # Set dark palette
        self._set_dark_palette()

        # Components
        self.audio_processor = AudioProcessor()
        self.capture_thread = None
        self._is_capturing = False

        # Build UI
        self._build_ui()

        # Auto-start capture after event loop kicks in
        QTimer.singleShot(200, self._start_capture)

    def _set_dark_palette(self):
        """Apply a dark theme palette to the application."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(18, 18, 24))
        palette.setColor(QPalette.WindowText, QColor(200, 200, 210))
        palette.setColor(QPalette.Base, QColor(25, 25, 35))
        palette.setColor(QPalette.AlternateBase, QColor(30, 30, 42))
        palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 35))
        palette.setColor(QPalette.ToolTipText, QColor(200, 200, 210))
        palette.setColor(QPalette.Text, QColor(200, 200, 210))
        palette.setColor(QPalette.Button, QColor(35, 35, 50))
        palette.setColor(QPalette.ButtonText, QColor(200, 200, 210))
        palette.setColor(QPalette.Highlight, QColor(0, 180, 220))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

    def _build_ui(self):
        """Build the main UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # --- Top toolbar ---
        toolbar = QFrame()
        toolbar.setFrameShape(QFrame.NoFrame)
        toolbar.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 30, 45, 200),
                    stop:1 rgba(20, 20, 32, 200)
                );
                border-radius: 10px;
                padding: 6px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 6, 12, 6)
        toolbar_layout.setSpacing(12)

        # Title
        title_label = QLabel("♪ Waveform Visualizer")
        title_label.setFont(QFont("Segoe UI Semibold", 11))
        title_label.setStyleSheet("color: #c8c8d2;")
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()

        # Theme selector
        theme_label = QLabel("🎨")
        theme_label.setFont(QFont("Segoe UI", 12))
        toolbar_layout.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.setFont(QFont("Segoe UI", 9))
        for name in WaveformWidget.get_theme_names():
            self.theme_combo.addItem(name)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.theme_combo.setStyleSheet("""
            QComboBox {
                background: rgba(40, 40, 60, 180);
                border: 1px solid rgba(80, 80, 120, 100);
                border-radius: 6px;
                padding: 5px 10px;
                color: #c8c8d2;
                min-width: 120px;
            }
            QComboBox::drop-down { border: none; padding-right: 8px; }
            QComboBox QAbstractItemView {
                background: rgb(30, 30, 45);
                color: #c8c8d2;
                selection-background-color: rgb(0, 180, 220);
            }
        """)
        toolbar_layout.addWidget(self.theme_combo)

        # Mirror toggle
        self.mirror_check = QCheckBox("Mirror")
        self.mirror_check.setChecked(True)
        self.mirror_check.setFont(QFont("Segoe UI", 9))
        self.mirror_check.stateChanged.connect(
            lambda s: self.waveform_widget.set_mirror(s == Qt.Checked)
        )
        self.mirror_check.setStyleSheet("QCheckBox { color: #a0a0b0; }")
        toolbar_layout.addWidget(self.mirror_check)

        # Glow toggle
        self.glow_check = QCheckBox("Glow")
        self.glow_check.setChecked(True)
        self.glow_check.setFont(QFont("Segoe UI", 9))
        self.glow_check.stateChanged.connect(
            lambda s: self.waveform_widget.set_glow(s == Qt.Checked)
        )
        self.glow_check.setStyleSheet("QCheckBox { color: #a0a0b0; }")
        toolbar_layout.addWidget(self.glow_check)

        main_layout.addWidget(toolbar)

        # --- Waveform widget ---
        self.waveform_widget = WaveformWidget()
        self.waveform_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.waveform_widget.setStyleSheet("""
            WaveformWidget {
                border: 1px solid rgba(50, 50, 80, 100);
                border-radius: 12px;
            }
        """)
        main_layout.addWidget(self.waveform_widget, stretch=1)

        # --- Music info bar ---
        info_bar = QFrame()
        info_bar.setFrameShape(QFrame.NoFrame)
        info_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 30, 45, 200),
                    stop:1 rgba(20, 20, 32, 200)
                );
                border-radius: 10px;
                padding: 4px;
            }
        """)
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(16, 8, 16, 8)
        info_layout.setSpacing(24)

        info_label_style = "color: #707088; font-size: 9px; text-transform: uppercase;"
        info_value_style = "color: #e0e0f0; font-size: 16px; font-weight: bold;"

        # Key
        key_group = QVBoxLayout()
        key_group.setSpacing(2)
        key_title = QLabel("KEY")
        key_title.setStyleSheet(info_label_style)
        key_title.setAlignment(Qt.AlignCenter)
        key_group.addWidget(key_title)
        self.key_label = QLabel("--")
        self.key_label.setStyleSheet(info_value_style)
        self.key_label.setAlignment(Qt.AlignCenter)
        self.key_label.setFont(QFont("Consolas", 16, QFont.Bold))
        key_group.addWidget(self.key_label)
        info_layout.addLayout(key_group)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: rgba(80, 80, 120, 80);")
        info_layout.addWidget(sep1)

        # Scale
        scale_group = QVBoxLayout()
        scale_group.setSpacing(2)
        scale_title = QLabel("SCALE")
        scale_title.setStyleSheet(info_label_style)
        scale_title.setAlignment(Qt.AlignCenter)
        scale_group.addWidget(scale_title)
        self.scale_label = QLabel("--")
        self.scale_label.setStyleSheet(info_value_style)
        self.scale_label.setAlignment(Qt.AlignCenter)
        self.scale_label.setFont(QFont("Consolas", 16, QFont.Bold))
        scale_group.addWidget(self.scale_label)
        info_layout.addLayout(scale_group)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: rgba(80, 80, 120, 80);")
        info_layout.addWidget(sep2)

        # Tempo / BPM
        bpm_group = QVBoxLayout()
        bpm_group.setSpacing(2)
        bpm_title = QLabel("TEMPO")
        bpm_title.setStyleSheet(info_label_style)
        bpm_title.setAlignment(Qt.AlignCenter)
        bpm_group.addWidget(bpm_title)
        self.bpm_label = QLabel("-- BPM")
        self.bpm_label.setStyleSheet(info_value_style)
        self.bpm_label.setAlignment(Qt.AlignCenter)
        self.bpm_label.setFont(QFont("Consolas", 16, QFont.Bold))
        bpm_group.addWidget(self.bpm_label)
        info_layout.addLayout(bpm_group)

        info_layout.addStretch()
        main_layout.addWidget(info_bar)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.status_bar.setFont(QFont("Consolas", 8))
        self.status_bar.setStyleSheet("""
            QStatusBar {
                color: #606070;
                background: transparent;
            }
        """)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _start_capture(self):
        """Start capturing audio from the default output device."""
        device_id = AudioCaptureThread.get_default_device_id()
        if device_id is None:
            self.status_bar.showMessage("⚠ No output device found")
            return

        self.audio_processor.reset()
        self.capture_thread = AudioCaptureThread(device_id=device_id)
        self.capture_thread.audio_data.connect(self._on_audio_data)
        self.capture_thread.error_occurred.connect(self._on_capture_error)
        self.capture_thread.start()

        self._is_capturing = True
        self.status_bar.showMessage("🎵 Capturing audio...")

    def _stop_capture(self):
        """Stop capturing audio."""
        if self.capture_thread:
            self.capture_thread.stop()
            self.capture_thread = None

        self._is_capturing = False
        self.waveform_widget.clear_data()
        self.key_label.setText("--")
        self.scale_label.setText("--")
        self.bpm_label.setText("-- BPM")
        self.status_bar.showMessage("Stopped")

    def _on_audio_data(self, audio_buffer):
        """Handle incoming audio data."""
        result = self.audio_processor.process(audio_buffer)
        self.waveform_widget.update_data(
            waveform=result["waveform"],
            rms=result["rms"],
            spectral_centroid=result["spectral_centroid_norm"],
            zcr=result["zcr"],
        )

        # Update music analysis labels
        self.key_label.setText(result["key"])
        self.scale_label.setText(result["scale"])
        bpm = result["bpm"]
        self.bpm_label.setText(f"{bpm:.0f} BPM" if bpm > 0 else "-- BPM")

    def _on_capture_error(self, error_msg):
        """Handle capture errors."""
        self._stop_capture()
        self.status_bar.showMessage(f"⚠ Error: {error_msg}")

    def _on_theme_changed(self, theme_name):
        """Handle theme change."""
        self.waveform_widget.set_theme(theme_name)

    def closeEvent(self, event):
        """Clean up on close."""
        self._stop_capture()
        event.accept()


