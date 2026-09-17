"""Pairing dialog window for associating the laptop with NoInsta user account."""

import logging
import socket
from typing import Callable, Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class PairingDialog(QDialog):
    """Dialog that requests a pairing code from the server, displays it,

    and polls until the user's Android phone claims it.
    """

    def __init__(
        self,
        request_code_callback: Callable[[Optional[str]], Tuple[bool, Optional[str], str]],
        check_status_callback: Callable[[str], Tuple[bool, bool, Optional[str], str]],
        pair_callback: Optional[Callable[[str, str], Tuple[bool, str]]] = None,
        default_server_url: str = "https://noinsta.platesight.in",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.request_code_callback = request_code_callback
        self.check_status_callback = check_status_callback
        self.pair_callback = pair_callback
        self.default_server_url = default_server_url

        self._current_code: Optional[str] = None
        self._is_claimed = False

        # Status polling timer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1500)
        self._poll_timer.timeout.connect(self._poll_pairing_status)

        self.setWindowTitle("NoInsta - Device Pairing")
        self.setModal(True)
        self.setFixedWidth(440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self._init_ui()
        self.center_on_screen()

        # Request code automatically on launch
        QTimer.singleShot(150, self.generate_new_code)

    def center_on_screen(self) -> None:
        """Center dialog on current primary display screen."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            dialog_geo = self.frameGeometry()
            dialog_geo.moveCenter(screen_geo.center())
            self.move(dialog_geo.topLeft())

    def showEvent(self, event) -> None:
        """Handle window shown event by raising and activating window."""
        super().showEvent(event)
        self.center_on_screen()
        self.raise_()
        self.activateWindow()

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #FFFFFF;
            }
            QLabel {
                color: #E0E0E0;
                font-size: 13px;
            }
            QLabel#TitleLabel {
                color: #FFFFFF;
                font-size: 22px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QLabel#SubtitleLabel {
                color: #B0B0B0;
                font-size: 13px;
            }
            QLabel#InstructionLabel {
                color: #FFA726;
                font-size: 13px;
                font-weight: 500;
            }
            QLabel#CodeDisplay {
                background-color: #121212;
                color: #FF5252;
                border: 2px dashed #E1306C;
                border-radius: 8px;
                padding: 14px 20px;
                font-size: 28px;
                font-weight: bold;
                letter-spacing: 6px;
            }
            QLabel#StatusLabel {
                color: #9E9E9E;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #2C2C2C;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #E1306C;
            }
            QPushButton#ActionBtn {
                background-color: #E1306C;
                color: #FFFFFF;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                border: none;
                font-size: 13px;
            }
            QPushButton#ActionBtn:hover {
                background-color: #C13584;
            }
            QPushButton#SecondaryBtn {
                background-color: #333333;
                color: #E0E0E0;
                padding: 8px 14px;
                border-radius: 6px;
                border: none;
                font-size: 12px;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #444444;
            }
            QPushButton#LinkBtn {
                background: transparent;
                color: #888888;
                border: none;
                font-size: 11px;
                text-decoration: underline;
            }
            QPushButton#LinkBtn:hover {
                color: #CCCCCC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        # Header Title
        title = QLabel("NOINSTA")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Pair this laptop with your Android phone")
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(6)

        # Device Name field
        name_layout = QHBoxLayout()
        name_label = QLabel("Laptop Name:")
        self.name_input = QLineEdit()
        self.name_input.setText(socket.gethostname())
        self.name_input.setPlaceholderText("Enter device name...")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Code Container Frame
        code_frame = QFrame()
        code_frame.setStyleSheet("background-color: #252525; border-radius: 10px; padding: 12px;")
        frame_layout = QVBoxLayout(code_frame)
        frame_layout.setSpacing(10)
        frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        prompt_label = QLabel("Enter this code in your NoInsta Android app:")
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(prompt_label)

        # Large Code Display
        self.code_display = QLabel("••••••")
        self.code_display.setObjectName("CodeDisplay")
        self.code_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.code_display)

        # Copy Code Button
        copy_layout = QHBoxLayout()
        copy_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.copy_btn = QPushButton("📋 Copy Code")
        self.copy_btn.setObjectName("SecondaryBtn")
        self.copy_btn.clicked.connect(self._on_copy_code)
        self.copy_btn.setEnabled(False)
        copy_layout.addWidget(self.copy_btn)

        self.regen_btn = QPushButton("🔄 New Code")
        self.regen_btn.setObjectName("SecondaryBtn")
        self.regen_btn.clicked.connect(self.generate_new_code)
        copy_layout.addWidget(self.regen_btn)
        frame_layout.addLayout(copy_layout)

        layout.addWidget(code_frame)

        # Status indicator
        self.status_label = QLabel("Connecting to server to generate pairing code...")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addSpacing(4)

        # Manual entry widget (collapsible)
        self.manual_widget = QWidget()
        manual_layout = QVBoxLayout(self.manual_widget)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(6)
        manual_label = QLabel("Or enter a code manually:")
        manual_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
        manual_layout.addWidget(manual_label)
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("Enter 6-char code from phone")
        self.manual_input.setMaxLength(32)
        manual_layout.addWidget(self.manual_input)
        self.manual_pair_btn = QPushButton("Submit Manual Code")
        self.manual_pair_btn.setObjectName("SecondaryBtn")
        self.manual_pair_btn.clicked.connect(self._on_manual_pair_clicked)
        manual_layout.addWidget(self.manual_pair_btn)
        self.manual_widget.setVisible(False)
        layout.addWidget(self.manual_widget)

        # Toggle manual entry link
        self.toggle_manual_btn = QPushButton("I want to enter a code manually instead")
        self.toggle_manual_btn.setObjectName("LinkBtn")
        self.toggle_manual_btn.clicked.connect(self._toggle_manual_entry)
        layout.addWidget(self.toggle_manual_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(6)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.done_btn = QPushButton("Done")
        self.done_btn.setObjectName("ActionBtn")
        self.done_btn.clicked.connect(self._on_done_clicked)
        btn_layout.addWidget(self.done_btn)

        layout.addLayout(btn_layout)

    def generate_new_code(self) -> None:
        """Call backend server to generate a fresh pairing code."""
        self._poll_timer.stop()
        self.code_display.setText("••••••")
        self.code_display.setStyleSheet("color: #888888; border: 2px dashed #555555;")
        self.copy_btn.setEnabled(False)
        self.regen_btn.setEnabled(False)
        self.status_label.setStyleSheet("color: #FFA726;")
        self.status_label.setText("⏳ Requesting pairing code from server...")

        device_name = self.name_input.text().strip() or socket.gethostname()

        try:
            success, code, message = self.request_code_callback(device_name)
            if success and code:
                self._current_code = code
                formatted_code = " ".join(code)
                self.code_display.setText(formatted_code)
                self.code_display.setStyleSheet("color: #FF5252; border: 2px dashed #E1306C;")
                self.copy_btn.setEnabled(True)
                self.regen_btn.setEnabled(True)
                self.status_label.setStyleSheet("color: #E0E0E0;")
                self.status_label.setText(
                    f"Code active: {code}\nWaiting for NoInsta Android app to connect..."
                )
                print(f"\n{'='*55}\n  NOINSTA PAIRING CODE: [  {code}  ]\n  Enter this 6-character code in your NoInsta Android app\n{'='*55}\n", flush=True)
                # Start polling for phone claim
                self._poll_timer.start()
            else:
                self.status_label.setStyleSheet("color: #EF5350;")
                self.status_label.setText(f"Failed to generate code: {message}")
                self.regen_btn.setEnabled(True)
        except Exception as exc:
            logger.error("Failed to request pairing code: %s", exc)
            self.status_label.setStyleSheet("color: #EF5350;")
            self.status_label.setText(f"Error connecting to server: {exc}")
            self.regen_btn.setEnabled(True)

    def _poll_pairing_status(self) -> None:
        """Check if Android phone has claimed the active pairing code."""
        if not self._current_code:
            return

        try:
            success, is_claimed, claimed_device_name, msg = self.check_status_callback(self._current_code)
            if success and is_claimed:
                self._is_claimed = True
                self._poll_timer.stop()
                device_label = claimed_device_name or "Android Phone"
                print(f"\n{'='*55}\n  DEVICE PAIRED SUCCESSFULLY WITH {device_label}!\n{'='*55}\n", flush=True)
                self.status_label.setStyleSheet("color: #66BB6A; font-weight: bold;")
                self.status_label.setText(f"✅ Paired successfully with {device_label}!")
                self.code_display.setStyleSheet("color: #66BB6A; border: 2px solid #66BB6A;")
                self.done_btn.setText("Finish")
                # Auto-close dialog after short celebration
                QTimer.singleShot(1400, self.accept)
        except Exception as exc:
            logger.debug("Polling error (ignored): %s", exc)

    def _on_copy_code(self) -> None:
        """Copy pairing code to clipboard."""
        if self._current_code:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText(self._current_code)
            self.copy_btn.setText("✓ Copied!")
            QTimer.singleShot(2000, lambda: self.copy_btn.setText("📋 Copy Code"))

    def _toggle_manual_entry(self) -> None:
        """Toggle visibility of manual pairing code entry form."""
        is_visible = self.manual_widget.isVisible()
        self.manual_widget.setVisible(not is_visible)
        if not is_visible:
            self.toggle_manual_btn.setText("Hide manual code entry")
        else:
            self.toggle_manual_btn.setText("I want to enter a code manually instead")

    def _on_manual_pair_clicked(self) -> None:
        """Handle manual code submission."""
        code = self.manual_input.text().strip().upper()
        if not code:
            self.status_label.setStyleSheet("color: #EF5350;")
            self.status_label.setText("Please enter a pairing code.")
            return

        name = self.name_input.text().strip() or socket.gethostname()
        self.manual_pair_btn.setEnabled(False)
        self.status_label.setStyleSheet("color: #FFA726;")
        self.status_label.setText("Submitting pairing code to server...")

        try:
            if self.pair_callback:
                success, msg = self.pair_callback(code, name)
                if success:
                    self._poll_timer.stop()
                    self.status_label.setStyleSheet("color: #66BB6A; font-weight: bold;")
                    self.status_label.setText(msg or "Device paired successfully!")
                    QTimer.singleShot(1000, self.accept)
                    return
                else:
                    self.status_label.setStyleSheet("color: #EF5350;")
                    self.status_label.setText(msg or "Pairing failed.")
            else:
                self.status_label.setText("Manual pairing not available.")
        except Exception as exc:
            logger.error("Manual pairing error: %s", exc)
            self.status_label.setStyleSheet("color: #EF5350;")
            self.status_label.setText(f"Pairing error: {exc}")
        finally:
            self.manual_pair_btn.setEnabled(True)

    def _on_done_clicked(self) -> None:
        """Handle Done button click."""
        self._poll_timer.stop()
        self.accept()

    def reject(self) -> None:
        """Stop poll timer on dialog close."""
        self._poll_timer.stop()
        super().reject()
