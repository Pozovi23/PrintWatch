"""Moonraker (Klipper) REST API adapter."""

import logging
import time
from typing import Any
from urllib.parse import quote
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
        self._temperature_objects: list[str] = []
        self._last_discovery_time: float = 0.0

    def discover_temperature_sensors(self) -> list[str]:
        """Discover all temperature-capable objects from Klipper /printer/objects/list."""
        try:
            data, _ = self._get("/printer/objects/list")
            all_objects = data.get("result", {}).get("objects", [])

            sensors = []
            for obj in all_objects:
                lower_obj = obj.lower()
                if (
                    lower_obj.startswith("extruder")
                    or lower_obj == "heater_bed"
                    or lower_obj.startswith("heater_generic ")
                    or lower_obj.startswith("temperature_sensor ")
                    or lower_obj.startswith("temperature_fan ")
                ):
                    sensors.append(obj)

            if sensors:
                self._temperature_objects = sensors
                self._last_discovery_time = time.time()
                logger.info("Discovered %d temperature sensors for %s: %s", len(sensors), self.host, sensors)
                return sensors
        except Exception as exc:
            logger.debug("Sensor discovery failed for %s: %s, using defaults", self.host, exc)

        if not self._temperature_objects:
            self._temperature_objects = ["extruder", "heater_bed"]
        return self._temperature_objects

    @staticmethod
    def _format_tool_name(obj: str) -> str:
        """Convert Klipper object name to a clean, readable tool label."""
        if obj.startswith("temperature_sensor "):
            return obj[len("temperature_sensor ") :].strip()
        if obj.startswith("heater_generic "):
            return obj[len("heater_generic ") :].strip()
        if obj.startswith("temperature_fan "):
            return obj[len("temperature_fan ") :].strip()
        if obj == "heater_bed":
            return "bed"
        return obj

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

            # 2. Query objects (with dynamic discovery of temperature sensors)
            if not self._temperature_objects or (time.time() - self._last_discovery_time) > 600:
                self.discover_temperature_sensors()

            query_objects = list(self._temperature_objects)
            for std_obj in ("print_stats", "display_status", "virtual_sdcard"):
                if std_obj not in query_objects:
                    query_objects.append(std_obj)

            query_path = "/printer/objects/query?" + "&".join(quote(s) for s in query_objects)
            data, lat_query = self._get(query_path)
            telemetry.endpoint_latencies["/printer/objects/query"] = lat_query

            status = data.get("result", {}).get("status", {})

            telemetry.is_up = True

            # Parse all discovered temperature sensors
            for obj in self._temperature_objects:
                obj_status = status.get(obj)
                if not isinstance(obj_status, dict):
                    continue
                tool_name = self._format_tool_name(obj)
                temp_val = obj_status.get("temperature")
                if temp_val is not None:
                    try:
                        telemetry.temperatures[tool_name] = float(temp_val)
                    except (ValueError, TypeError):
                        pass
                target_val = obj_status.get("target")
                if target_val is not None:
                    try:
                        telemetry.temperature_targets[tool_name] = float(target_val)
                    except (ValueError, TypeError):
                        pass

            # Backwards compatibility fields for extruder & bed
            telemetry.extruder_temp = telemetry.temperatures.get("extruder", 0.0)
            telemetry.extruder_target = telemetry.temperature_targets.get("extruder", 0.0)
            telemetry.bed_temp = telemetry.temperatures.get("bed", 0.0)
            telemetry.bed_target = telemetry.temperature_targets.get("bed", 0.0)

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
