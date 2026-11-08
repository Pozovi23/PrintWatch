"""Moonraker (Klipper) REST API adapter."""

import logging
import time
from typing import Any
import requests

from exporter.adapters.base import BaseAdapter, PrinterTelemetry

logger = logging.getLogger(__name__)


class MoonrakerAdapter(BaseAdapter):
    """Adapter for Moonraker REST API (Klipper web API)."""

    def __init__(self, host: str, api_key: str | None = None, timeout: float = 3.5) -> None:
        super().__init__(host, api_key, timeout)
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-Api-Key": self.api_key})
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str) -> tuple[dict[str, Any], float]:
        """Perform a GET request, returning parsed JSON and response time in seconds."""
        url = f"{self.host}{path}"
        start = time.perf_counter()
        resp = self.session.get(url, timeout=self.timeout)
        duration = time.perf_counter() - start
        resp.raise_for_status()
        return resp.json(), duration

    def _determine_state(self, print_stats_state: str, klippy_state: str) -> str:
        """Map Moonraker / Klippy states to standard states:

        idle, printing, paused, error, offline.
        """
        if klippy_state.lower() in ("error", "shutdown"):
            return "error"
        if klippy_state.lower() in ("disconnected", "startup"):
            return "offline"

        state_norm = print_stats_state.lower()
        if state_norm in ("printing",):
            return "printing"
        if state_norm in ("paused",):
            return "paused"
        if state_norm in ("error",):
            return "error"
        if state_norm in ("standby", "complete", "cancelled", ""):
            return "idle"
        return "idle"

    def fetch_telemetry(self) -> PrinterTelemetry:
        """Fetch telemetry from Moonraker: /server/info and /printer/objects/query."""
        telemetry = PrinterTelemetry()

        try:
            # 1. Server info check
            klippy_state = "ready"
            try:
                server_info, lat_srv = self._get("/server/info")
                telemetry.endpoint_latencies["/server/info"] = lat_srv
                result = server_info.get("result", {})
                telemetry.version = str(result.get("moonraker_version", "moonraker"))
                klippy_state = str(result.get("klippy_state", "ready"))
            except requests.exceptions.RequestException:
                pass

            # 2. Query objects
            query_path = "/printer/objects/query?extruder&heater_bed&print_stats&display_status&virtual_sdcard"
            data, lat_query = self._get(query_path)
            telemetry.endpoint_latencies["/printer/objects/query"] = lat_query

            status = data.get("result", {}).get("status", {})

            telemetry.is_up = True

            # Extruder & Bed temperatures
            extruder = status.get("extruder", {})
            bed = status.get("heater_bed", {})

            telemetry.extruder_temp = float(extruder.get("temperature", 0.0) or 0.0)
            telemetry.extruder_target = float(extruder.get("target", 0.0) or 0.0)
            telemetry.bed_temp = float(bed.get("temperature", 0.0) or 0.0)
            telemetry.bed_target = float(bed.get("target", 0.0) or 0.0)

            # Print stats
            print_stats = status.get("print_stats", {})
            raw_state = str(print_stats.get("state", "standby"))
            telemetry.state = self._determine_state(raw_state, klippy_state)
            telemetry.filename = str(print_stats.get("filename", "") or "")
            telemetry.time_elapsed_seconds = float(print_stats.get("print_duration", 0.0) or 0.0)

            # Progress
            display_status = status.get("display_status", {})
            virtual_sdcard = status.get("virtual_sdcard", {})
            progress = display_status.get("progress")
            if progress is None:
                progress = virtual_sdcard.get("progress")

            if progress is not None:
                telemetry.progress_ratio = max(0.0, min(1.0, float(progress)))

            # Estimated time remaining calculation
            if telemetry.state == "printing" and telemetry.progress_ratio > 0.001:
                total_est = telemetry.time_elapsed_seconds / telemetry.progress_ratio
                telemetry.time_left_seconds = max(0.0, total_est - telemetry.time_elapsed_seconds)
            else:
                telemetry.time_left_seconds = 0.0

            return telemetry

        except requests.exceptions.Timeout as e:
            telemetry.is_up = False
            telemetry.state = "offline"
            telemetry.error_type = "timeout"
            telemetry.error_message = f"Timeout querying Moonraker: {e}"
            return telemetry

        except requests.exceptions.ConnectionError as e:
            telemetry.is_up = False
            telemetry.state = "offline"
            telemetry.error_type = "connection_error"
            telemetry.error_message = f"Connection error: {e}"
            return telemetry

        except requests.exceptions.HTTPError as e:
            telemetry.is_up = False
            telemetry.state = "offline"
            status_code = e.response.status_code if e.response is not None else 0
            if status_code >= 500:
                telemetry.error_type = "http_5xx"
            else:
                telemetry.error_type = "http_4xx"
            telemetry.error_message = f"HTTP {status_code} error: {e}"
            return telemetry

        except (ValueError, KeyError, TypeError) as e:
            telemetry.is_up = False
            telemetry.state = "offline"
            telemetry.error_type = "parse_error"
            telemetry.error_message = f"Failed to parse Moonraker response: {e}"
            return telemetry

        except Exception as e:
            telemetry.is_up = False
            telemetry.state = "offline"
            telemetry.error_type = "connection_error"
            telemetry.error_message = f"Unexpected error: {e}"
            return telemetry
