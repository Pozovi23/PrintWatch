"""Integration tests connecting to live physical 3D printers defined in config/printers.yaml.

These tests are marked with @pytest.mark.live and require real network access to the printers.
They can be run locally via:
    pytest -v -m live
or skipped in CI/CD via:
    pytest -v -m "not live"
"""

import pytest
import requests
from exporter.adapters.moonraker import MoonrakerAdapter
from exporter.collector import MultiPrinterCollector
from exporter.config import load_yaml_config, PrinterConfig
from exporter.metrics import PrinterMetrics


def get_live_printers() -> list[PrinterConfig]:
    """Load printers defined in config/printers.yaml."""
    _, printers = load_yaml_config("config/printers.yaml")
    return printers


LIVE_PRINTERS = get_live_printers()


@pytest.mark.live
class TestLivePrinters:
    """Integration test suite against live Moonraker 3D printers."""

    @pytest.fixture(autouse=True)
    def ensure_printers_available(self):
        if not LIVE_PRINTERS:
            pytest.skip("No printers defined in config/printers.yaml")

    @pytest.mark.parametrize("printer", LIVE_PRINTERS, ids=lambda p: p.name)
    def test_live_printer_server_info_reachable(self, printer: PrinterConfig):
        """Verify Moonraker API endpoint /server/info is reachable and returns 200 OK."""
        url = f"{printer.host}/server/info"
        headers = {}
        if printer.api_key:
            headers["X-Api-Key"] = printer.api_key.get_secret_value()

        try:
            resp = requests.get(url, headers=headers, timeout=4.0)
        except requests.exceptions.RequestException as e:
            pytest.fail(
                f"Failed to connect to printer '{printer.name}' at {printer.host}: {e}\n"
                f"HINT: If VPN is running on the host, run 'make vpn-bypass-docker' (sudo ./scripts/vpn-bypass-docker.sh) "
                f"to ensure LAN traffic to {printer.host} bypasses the VPN tunnel!",
            )

        assert resp.status_code == 200, f"Expected 200 OK from {url}, got {resp.status_code}"
        data = resp.json()
        assert "result" in data, f"Missing 'result' block in Moonraker response from {url}"
        result = data["result"]

        assert "klippy_state" in result, "Missing 'klippy_state' in /server/info"
        assert isinstance(result.get("klippy_connected"), bool)
        assert "moonraker_version" in result, "Missing 'moonraker_version' in /server/info"

    @pytest.mark.parametrize("printer", LIVE_PRINTERS, ids=lambda p: p.name)
    def test_live_printer_telemetry_fetch(self, printer: PrinterConfig):
        """Verify MoonrakerAdapter fetches and normalizes live telemetry from the printer."""
        api_key_str = printer.api_key.get_secret_value() if printer.api_key else None
        adapter = MoonrakerAdapter(host=printer.host, api_key=api_key_str, timeout=4.0)

        telemetry = adapter.fetch_telemetry()

        if not telemetry.is_up:
            pytest.fail(
                f"MoonrakerAdapter failed to scrape '{printer.name}' ({printer.host}): "
                f"error_type={telemetry.error_type}, error_message={telemetry.error_message}\n"
                f"HINT: Check if VPN table 2022 is intercepting LAN routes (run 'make vpn-bypass-docker').",
            )

        assert telemetry.is_up is True
        assert telemetry.state in ("idle", "printing", "paused", "error", "offline")
        assert isinstance(telemetry.extruder_temp, (int, float))
        assert telemetry.extruder_temp >= 0.0, f"Extruder temp should be non-negative: {telemetry.extruder_temp}"
        assert isinstance(telemetry.bed_temp, (int, float))
        assert telemetry.bed_temp >= 0.0, f"Bed temp should be non-negative: {telemetry.bed_temp}"
        assert 0.0 <= telemetry.progress_ratio <= 1.0

    def test_live_multi_printer_collector_scrapes_all(self, test_metrics: PrinterMetrics):
        """Verify MultiPrinterCollector scrapes all configured live printers in parallel."""
        collector = MultiPrinterCollector(
            printers=LIVE_PRINTERS,
            metrics=test_metrics,
            poll_interval=5.0,
            timeout_seconds=4.0,
        )

        collector.collect_all_once()

        for p in LIVE_PRINTERS:
            up_val = test_metrics.printer_up.labels(printer=p.name)._value.get()
            assert up_val == 1.0, f"Expected printer_up=1.0 for '{p.name}', got {up_val}"

            ext_temp = test_metrics.printer_temperature_celsius.labels(printer=p.name, tool="extruder")._value.get()
            assert ext_temp >= 0.0

            bed_temp = test_metrics.printer_temperature_celsius.labels(printer=p.name, tool="bed")._value.get()
            assert bed_temp >= 0.0
