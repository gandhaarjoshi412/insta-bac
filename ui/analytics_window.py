"""Analytics and Telemetry Dashboard Window for NoInsta Laptop Client."""

from datetime import datetime
import logging
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable format (e.g. 2h 15m 30s)."""
    if seconds <= 0:
        return "0s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def format_iso_timestamp(iso_str: Optional[str]) -> str:
    """Format ISO timestamp string into readable local representation."""
    if not iso_str:
        return "Never"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(iso_str)


class AnalyticsFetchWorker(QThread):
    """Worker thread to fetch analytics without blocking the GUI."""
    finished_data = Signal(bool, object, str)

    def __init__(self, fetch_callback: Callable[[], Tuple[bool, Optional[dict], str]]):
        super().__init__()
        self.fetch_callback = fetch_callback

    def run(self):
        try:
            success, data, msg = self.fetch_callback()
            self.finished_data.emit(success, data, msg)
        except Exception as exc:
            logger.error("Error in AnalyticsFetchWorker: %s", exc)
            self.finished_data.emit(False, None, str(exc))


class AnalyticsWindow(QWidget):
    """Analytics dashboard displaying real-time usage stats, trends, and event logs."""

    def __init__(
        self,
        fetch_analytics_callback: Callable[[], Tuple[bool, Optional[dict], str]],
        server_url: str = "https://noinsta.platesight.in",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.fetch_analytics_callback = fetch_analytics_callback
        self.server_url = server_url
        self._worker: Optional[AnalyticsFetchWorker] = None

        self.setWindowTitle("NoInsta - Analytics & Telemetry Dashboard")
        self.resize(880, 640)
        self.setMinimumSize(720, 500)

        self._init_ui()
        self.center_on_screen()
        self.refresh_data()

    def center_on_screen(self) -> None:
        """Center window on primary monitor."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            win_geo = self.frameGeometry()
            win_geo.moveCenter(screen_geo.center())
            self.move(win_geo.topLeft())

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #18181B;
                color: #F4F4F5;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            QFrame#card {
                background-color: #27272A;
                border: 1px solid #3F3F46;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#cardTitle {
                color: #A1A1AA;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QLabel#cardValue {
                color: #FAFAFA;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#cardSub {
                color: #71717A;
                font-size: 11px;
            }
            QTabWidget::pane {
                border: 1px solid #27272A;
                background-color: #18181B;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #27272A;
                color: #A1A1AA;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #3F3F46;
                color: #FAFAFA;
            }
            QTableWidget {
                background-color: #1F1F23;
                gridline-color: #27272A;
                border: none;
                font-size: 12px;
                selection-background-color: #3F3F46;
            }
            QHeaderView::section {
                background-color: #27272A;
                color: #D4D4D8;
                font-weight: 600;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-right: 1px solid #3F3F46;
                border-bottom: 1px solid #3F3F46;
            }
            QPushButton#primaryBtn {
                background-color: #3B82F6;
                color: white;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton#primaryBtn:hover {
                background-color: #2563EB;
            }
            QPushButton#secondaryBtn {
                background-color: #27272A;
                color: #E4E4E7;
                font-size: 12px;
                padding: 6px 14px;
                border-radius: 6px;
                border: 1px solid #3F3F46;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #3F3F46;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)

        title = QLabel("📊 NoInsta Telemetry & Analytics")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header_text_layout.addWidget(title)

        subtitle = QLabel("Live Instagram usage activity and intervention performance across devices")
        subtitle.setStyleSheet("color: #A1A1AA; font-size: 12px;")
        header_text_layout.addWidget(subtitle)
        header_layout.addLayout(header_text_layout)

        header_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setObjectName("primaryBtn")
        self.refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.refresh_btn)

        main_layout.addLayout(header_layout)

        # Summary Metric Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_today_opens, self.val_today_opens, self.sub_today_opens = self._create_card(
            "Today's Opens", "0", "Instagram launches today"
        )
        self.card_today_time, self.val_today_time, self.sub_today_time = self._create_card(
            "Time Spent Today", "0s", "Screen time logged today"
        )
        self.card_today_interventions, self.val_today_interventions, self.sub_today_interventions = self._create_card(
            "Interventions Today", "0", "Dispatched to laptop"
        )
        self.card_all_time, self.val_all_time, self.sub_all_time = self._create_card(
            "All-Time Opens", "0", "Total recorded launches"
        )

        cards_layout.addWidget(self.card_today_opens)
        cards_layout.addWidget(self.card_today_time)
        cards_layout.addWidget(self.card_today_interventions)
        cards_layout.addWidget(self.card_all_time)
        main_layout.addLayout(cards_layout)

        # Tabs for details
        self.tabs = QTabWidget()

        # Tab 1: 7-Day Trend
        self.daily_table = QTableWidget()
        self.daily_table.setColumnCount(4)
        self.daily_table.setHorizontalHeaderLabels(["Date", "Launches", "Time Spent", "Interventions"])
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.daily_table, "📅 7-Day Trend")

        # Tab 2: Recent Events
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(4)
        self.events_table.setHorizontalHeaderLabels(["Timestamp", "Event Type", "Device", "Device Type"])
        self.events_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.events_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.events_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.events_table, "📱 Recent Events")

        # Tab 3: Recent Interventions
        self.interventions_table = QTableWidget()
        self.interventions_table.setColumnCount(4)
        self.interventions_table.setHorizontalHeaderLabels(["Dispatched At", "Status", "Laptop Client", "Ack Time"])
        self.interventions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.interventions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.interventions_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.interventions_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.interventions_table, "⚡ Interventions")

        main_layout.addWidget(self.tabs, stretch=1)

        # Footer Status Bar
        footer_layout = QHBoxLayout()
        self.status_label = QLabel(f"Connected to {self.server_url} | Ready")
        self.status_label.setStyleSheet("color: #71717A; font-size: 11px;")
        footer_layout.addWidget(self.status_label)

        footer_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.hide)
        footer_layout.addWidget(close_btn)

        main_layout.addLayout(footer_layout)

    def _create_card(self, title: str, default_val: str, subtitle: str) -> Tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("cardTitle")
        layout.addWidget(t_lbl)

        v_lbl = QLabel(default_val)
        v_lbl.setObjectName("cardValue")
        layout.addWidget(v_lbl)

        s_lbl = QLabel(subtitle)
        s_lbl.setObjectName("cardSub")
        layout.addWidget(s_lbl)

        return card, v_lbl, s_lbl

    def refresh_data(self) -> None:
        """Trigger background fetching of analytics."""
        if self._worker and self._worker.isRunning():
            return

        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ Loading...")
        self.status_label.setText("Fetching telemetry data from server...")

        self._worker = AnalyticsFetchWorker(self.fetch_analytics_callback)
        self._worker.finished_data.connect(self._on_data_loaded)
        self._worker.start()

    def _on_data_loaded(self, success: bool, data: Optional[dict], message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 Refresh")

        if not success or not data:
            self.status_label.setText(f"Failed to load analytics: {message}")
            self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
            return

        self.status_label.setText(f"Synced with {self.server_url} at {datetime.now().strftime('%H:%M:%S')}")
        self.status_label.setStyleSheet("color: #10B981; font-size: 11px;")

        summary = data.get("summary", {})
        daily = data.get("daily_breakdown", [])
        events = data.get("recent_events", [])
        interventions = data.get("recent_interventions", [])

        # Update cards
        self.val_today_opens.setText(str(summary.get("total_opens_today", 0)))
        time_today = summary.get("total_time_today_seconds", 0)
        self.val_today_time.setText(format_duration(time_today))

        self.val_today_interventions.setText(str(summary.get("total_interventions_today", 0)))
        all_time_opens = summary.get("total_opens_all_time", 0)
        all_time_sessions = summary.get("total_sessions_all_time", 0)
        self.val_all_time.setText(f"{all_time_opens}")
        self.sub_all_time.setText(f"{all_time_sessions} sessions total")

        # Update Daily Breakdown table
        self.daily_table.setRowCount(len(daily))
        for row, item in enumerate(daily):
            self.daily_table.setItem(row, 0, QTableWidgetItem(str(item.get("date"))))
            self.daily_table.setItem(row, 1, QTableWidgetItem(str(item.get("opens"))))
            time_spent = item.get("time_spent_seconds", 0)
            self.daily_table.setItem(row, 2, QTableWidgetItem(format_duration(time_spent)))
            self.daily_table.setItem(row, 3, QTableWidgetItem(str(item.get("interventions"))))

        # Update Recent Events table
        self.events_table.setRowCount(len(events))
        for row, item in enumerate(events):
            occurred_at = format_iso_timestamp(item.get("occurred_at"))
            self.events_table.setItem(row, 0, QTableWidgetItem(occurred_at))
            self.events_table.setItem(row, 1, QTableWidgetItem(str(item.get("event_type"))))
            self.events_table.setItem(row, 2, QTableWidgetItem(str(item.get("device_name"))))
            self.events_table.setItem(row, 3, QTableWidgetItem(str(item.get("device_type"))))

        # Update Recent Interventions table
        self.interventions_table.setRowCount(len(interventions))
        for row, item in enumerate(interventions):
            sent_at = format_iso_timestamp(item.get("sent_at"))
            self.interventions_table.setItem(row, 0, QTableWidgetItem(sent_at))
            self.interventions_table.setItem(row, 1, QTableWidgetItem(str(item.get("status"))))
            self.interventions_table.setItem(row, 2, QTableWidgetItem(str(item.get("laptop_device_name"))))
            ack_sec = item.get("duration_to_ack_seconds")
            ack_text = f"{ack_sec:.2f}s" if ack_sec is not None else "Pending / Timeout"
            self.interventions_table.setItem(row, 3, QTableWidgetItem(ack_text))
