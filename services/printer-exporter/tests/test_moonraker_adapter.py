"""Tests for Moonraker API adapter covering success, timeout, 500, invalid JSON, etc."""

import pytest
import requests
import requests_mock
from exporter.adapters.moonraker import MoonrakerAdapter

HOST = "http://mock-printer.local"


@pytest.fixture
def moonraker_adapter():
    return MoonrakerAdapter(host=HOST, timeout=2.0)


def test_moonraker_success(moonraker_adapter):
    """Test successful telemetry extraction from Moonraker."""
    with requests_mock.Mocker() as m:
        m.get(
            f"{HOST}/server/info",
            json={
                "result": {
                    "klippy_state": "ready",
                    "klippy_connected": True,
                    "moonraker_version": "v0.8.0-123",
                },
            },
        )
        m.get(
            f"{HOST}/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard",
            json={
                "result": {
                    "status": {
                        "extruder": {"temperature": 200.5, "target": 200.0},
                        "heater_bed": {"temperature": 59.8, "target": 60.0},
                        "print_stats": {
                            "filename": "voron_cube.gcode",
                            "state": "printing",
                            "print_duration": 600.0,
                        },
                        "display_status": {"progress": 0.5},
                    },
                },
            },
        )

        telemetry = moonraker_adapter.fetch_telemetry()

        assert telemetry.is_up is True
        assert telemetry.state == "printing"
        assert telemetry.extruder_temp == 200.5
        assert telemetry.extruder_target == 200.0
        assert telemetry.bed_temp == 59.8
        assert telemetry.bed_target == 60.0
        assert telemetry.progress_ratio == 0.5
        assert telemetry.time_elapsed_seconds == 600.0
        assert telemetry.time_left_seconds == 600.0  # 600s for 50% => 600s left
        assert telemetry.filename == "voron_cube.gcode"
        assert telemetry.error_type is None


def test_moonraker_timeout(moonraker_adapter):
    """Test timeout handling in Moonraker."""
    with requests_mock.Mocker() as m:
        m.get(
            f"{HOST}/server/info",
            exc=requests.exceptions.ConnectTimeout("Connect timed out"),
        )
        m.get(
            f"{HOST}/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard",
            exc=requests.exceptions.ConnectTimeout("Connect timed out"),
        )

        telemetry = moonraker_adapter.fetch_telemetry()
        assert telemetry.is_up is False
        assert telemetry.state == "offline"
        assert telemetry.error_type == "timeout"
        assert "Timeout" in (telemetry.error_message or "")


def test_moonraker_500_error(moonraker_adapter):
    """Test 500 internal server error handling in Moonraker."""
    with requests_mock.Mocker() as m:
        m.get(
            f"{HOST}/server/info",
            status_code=500,
            text="Internal Server Error",
        )
        m.get(
            f"{HOST}/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard",
            status_code=500,
            text="Internal Server Error",
        )

        telemetry = moonraker_adapter.fetch_telemetry()
        assert telemetry.is_up is False
        assert telemetry.state == "offline"
        assert telemetry.error_type == "http_5xx"


def test_moonraker_invalid_json(moonraker_adapter):
    """Test invalid / malformed JSON response handling."""
    with requests_mock.Mocker() as m:
        m.get(
            f"{HOST}/server/info",
            text="<html>502 Bad Gateway</html>",
            headers={"Content-Type": "application/json"},
        )
        m.get(
            f"{HOST}/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard",
            text="<html>502 Bad Gateway</html>",
            headers={"Content-Type": "application/json"},
        )

        telemetry = moonraker_adapter.fetch_telemetry()
        assert telemetry.is_up is False
        assert telemetry.state == "offline"
        assert telemetry.error_type == "parse_error"


def test_moonraker_klippy_shutdown(moonraker_adapter):
    """Test state when Klipper is in shutdown state (M112 emergency stop)."""
    with requests_mock.Mocker() as m:
        m.get(
            f"{HOST}/server/info",
            json={
                "result": {
                    "klippy_state": "shutdown",
                    "klippy_connected": False,
                    "moonraker_version": "v0.8.0",
                },
            },
        )
        m.get(
            f"{HOST}/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard",
            json={
                "result": {
                    "status": {
                        "extruder": {"temperature": 23.0, "target": 0.0},
                        "heater_bed": {"temperature": 22.0, "target": 0.0},
                        "print_stats": {"state": "error"},
                    },
                },
            },
        )

        telemetry = moonraker_adapter.fetch_telemetry()
        assert telemetry.is_up is True
        assert telemetry.state == "error"
