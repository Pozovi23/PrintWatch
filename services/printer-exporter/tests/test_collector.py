"""Tests for TelemetryCollector and MultiPrinterCollector."""

from unittest.mock import MagicMock
from exporter.adapters.base import BaseAdapter, PrinterTelemetry
from exporter.collector import MultiPrinterCollector, TelemetryCollector
from exporter.config import PrinterConfig


def test_collector_updates_metrics_on_success(test_metrics):
    """Ensure all Prometheus metrics are accurately updated when telemetry succeeds."""
    mock_adapter = MagicMock(spec=BaseAdapter)
    mock_adapter.fetch_telemetry.return_value = PrinterTelemetry(
        is_up=True,
        state="printing",
        version="v0.8.0",
        extruder_temp=210.0,
        extruder_target=215.0,
        bed_temp=60.0,
        bed_target=60.0,
        progress_ratio=0.75,
        time_left_seconds=900.0,
        time_elapsed_seconds=2700.0,
        filename="calicat.gcode",
        endpoint_latencies={"/printer/objects/query": 0.042},
    )

    collector = TelemetryCollector(
        adapter=mock_adapter,
        metrics=test_metrics,
        printer_name="printer-1",
    )

    collector.collect_once()

    # Verify printer_up
    assert test_metrics.printer_up.labels(printer="printer-1")._value.get() == 1.0

    # Verify printer_state mutual exclusivity
    assert test_metrics.printer_state.labels(printer="printer-1", state="printing")._value.get() == 1.0
    assert test_metrics.printer_state.labels(printer="printer-1", state="idle")._value.get() == 0.0
    assert test_metrics.printer_state.labels(printer="printer-1", state="offline")._value.get() == 0.0

    # Verify temperatures
    assert test_metrics.printer_temperature_celsius.labels(printer="printer-1", tool="extruder")._value.get() == 210.0
    assert (
        test_metrics.printer_temperature_target_celsius.labels(printer="printer-1", tool="extruder")._value.get()
        == 215.0
    )
    assert test_metrics.printer_temperature_celsius.labels(printer="printer-1", tool="bed")._value.get() == 60.0
    assert test_metrics.printer_temperature_target_celsius.labels(printer="printer-1", tool="bed")._value.get() == 60.0

    # Verify progress and ETA
    assert test_metrics.printer_print_progress_ratio.labels(printer="printer-1")._value.get() == 0.75
    assert test_metrics.printer_print_time_left_seconds.labels(printer="printer-1")._value.get() == 900.0
    assert test_metrics.printer_print_time_elapsed_seconds.labels(printer="printer-1")._value.get() == 2700.0


def test_collector_increments_error_counter(test_metrics):
    """Ensure error counters and offline state are set on failures."""
    mock_adapter = MagicMock(spec=BaseAdapter)
    mock_adapter.fetch_telemetry.return_value = PrinterTelemetry(
        is_up=False,
        state="offline",
        error_type="timeout",
        error_message="Timed out connecting to host",
    )

    collector = TelemetryCollector(
        adapter=mock_adapter,
        metrics=test_metrics,
        printer_name="printer-1",
    )

    collector.collect_once()

    assert test_metrics.printer_up.labels(printer="printer-1")._value.get() == 0.0
    assert test_metrics.printer_state.labels(printer="printer-1", state="offline")._value.get() == 1.0
    assert test_metrics.printer_state.labels(printer="printer-1", state="printing")._value.get() == 0.0
    assert test_metrics.printer_api_errors_total.labels(printer="printer-1", type="timeout")._value.get() == 1.0


def test_multi_printer_collector_handles_n_printers(test_metrics, monkeypatch):
    """Ensure MultiPrinterCollector collects metrics for N distinct printers independently."""
    printers = [
        PrinterConfig(name="printer-1", host="http://mock-printer-1.local"),
        PrinterConfig(name="printer-2", host="http://mock-printer-2.local"),
        PrinterConfig(name="printer-3", host="http://mock-printer-3.local"),
    ]

    multi_collector = MultiPrinterCollector(
        printers=printers,
        metrics=test_metrics,
        poll_interval=5.0,
    )

    assert len(multi_collector.collectors) == 3

    # Mock each collector's adapter
    multi_collector.collectors[0].adapter.fetch_telemetry = MagicMock(
        return_value=PrinterTelemetry(is_up=True, state="printing", extruder_temp=210.0, progress_ratio=0.8),
    )
    multi_collector.collectors[1].adapter.fetch_telemetry = MagicMock(
        return_value=PrinterTelemetry(is_up=True, state="idle", extruder_temp=25.0, progress_ratio=0.0),
    )
    multi_collector.collectors[2].adapter.fetch_telemetry = MagicMock(
        return_value=PrinterTelemetry(is_up=False, state="offline", error_type="timeout"),
    )

    multi_collector.collect_all_once()

    # Check printer-1
    assert test_metrics.printer_up.labels(printer="printer-1")._value.get() == 1.0
    assert test_metrics.printer_state.labels(printer="printer-1", state="printing")._value.get() == 1.0
    assert test_metrics.printer_temperature_celsius.labels(printer="printer-1", tool="extruder")._value.get() == 210.0

    # Check printer-2
    assert test_metrics.printer_up.labels(printer="printer-2")._value.get() == 1.0
    assert test_metrics.printer_state.labels(printer="printer-2", state="idle")._value.get() == 1.0
    assert test_metrics.printer_temperature_celsius.labels(printer="printer-2", tool="extruder")._value.get() == 25.0

    # Check printer-3
    assert test_metrics.printer_up.labels(printer="printer-3")._value.get() == 0.0
    assert test_metrics.printer_state.labels(printer="printer-3", state="offline")._value.get() == 1.0
