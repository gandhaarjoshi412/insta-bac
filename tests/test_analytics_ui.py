"""Tests for AnalyticsWindow and analytics client integration."""

import pytest
from PySide6.QtWidgets import QApplication

from ui.analytics_window import AnalyticsWindow, format_duration, format_iso_timestamp


def test_format_duration():
    assert format_duration(0) == "0s"
    assert format_duration(45) == "45s"
    assert format_duration(125) == "2m 5s"
    assert format_duration(3665) == "1h 1m 5s"


def test_format_iso_timestamp():
    assert format_iso_timestamp(None) == "Never"
    assert format_iso_timestamp("") == "Never"
    formatted = format_iso_timestamp("2026-09-20T14:30:00Z")
    assert "2026-09-20" in formatted


def test_analytics_window_initialization(qapp):
    mock_data = {
        "summary": {
            "total_opens_today": 12,
            "total_time_today_seconds": 360,
            "total_interventions_today": 3,
            "total_opens_all_time": 100,
            "total_sessions_all_time": 80,
            "total_interventions_all_time": 25,
            "last_opened_at": "2026-09-20T12:00:00Z",
        },
        "daily_breakdown": [
            {
                "date": "2026-09-20",
                "opens": 12,
                "time_spent_seconds": 360,
                "interventions": 3,
            }
        ],
        "recent_events": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "event_type": "INSTAGRAM_OPEN",
                "occurred_at": "2026-09-20T12:00:00Z",
                "device_id": "22222222-2222-2222-2222-222222222222",
                "device_name": "Pixel 8",
                "device_type": "ANDROID",
            }
        ],
        "recent_interventions": [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "event_id": "11111111-1111-1111-1111-111111111111",
                "sent_at": "2026-09-20T12:00:01Z",
                "acknowledged_at": "2026-09-20T12:00:03Z",
                "status": "ACKNOWLEDGED",
                "laptop_device_id": "44444444-4444-4444-4444-444444444444",
                "laptop_device_name": "Gandhaar Laptop",
                "duration_to_ack_seconds": 2.0,
            }
        ],
    }

    def mock_fetch():
        return True, mock_data, "OK"

    win = AnalyticsWindow(fetch_analytics_callback=mock_fetch)
    if win._worker:
        win._worker.wait(2000)
    qapp.processEvents()

    # Verify UI components populated
    assert win.val_today_opens.text() == "12"
    assert "6m" in win.val_today_time.text()
    assert win.val_today_interventions.text() == "3"
    assert win.val_all_time.text() == "100"
    assert win.daily_table.rowCount() == 1
    assert win.events_table.rowCount() == 1
    assert win.interventions_table.rowCount() == 1
    assert win.cooldown_combo.count() >= 5


def test_analytics_window_cooldown_selection(qapp):
    updated_seconds = []

    def mock_fetch():
        return True, {"summary": {"cooldown_seconds": 300, "cooldown_remaining_seconds": 0}}, "OK"

    def mock_update(sec):
        updated_seconds.append(sec)
        return True, {"cooldown_seconds": sec}, "OK"

    win = AnalyticsWindow(fetch_analytics_callback=mock_fetch, update_cooldown_callback=mock_update)
    if win._worker:
        win._worker.wait(2000)
    qapp.processEvents()

    # Change to 10 minutes (600s)
    idx = win.cooldown_combo.findData(600)
    assert idx >= 0
    win.cooldown_combo.setCurrentIndex(idx)
    qapp.processEvents()
    import time
    time.sleep(0.1)
    assert 600 in updated_seconds
