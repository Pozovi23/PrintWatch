"""Base classes and data models for printer API adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PrinterTelemetry:
    """Normalized telemetry data collected from a 3D printer API."""

    is_up: bool = False
    state: str = "offline"  # idle | printing | paused | error | offline
    version: str = "unknown"
    extruder_temp: float = 0.0
    extruder_target: float = 0.0
    bed_temp: float = 0.0
    bed_target: float = 0.0
    progress_ratio: float = 0.0  # 0.0 to 1.0
    time_left_seconds: float = 0.0
    time_elapsed_seconds: float = 0.0
    filename: str = ""
    error_type: Optional[str] = None  # timeout | http_5xx | http_4xx | parse_error | connection_error
    error_message: Optional[str] = None
    endpoint_latencies: dict[str, float] = field(default_factory=dict)


class BaseAdapter(ABC):
    """Abstract interface for printer API adapters."""

    def __init__(self, host: str, api_key: Optional[str] = None, timeout: float = 3.5) -> None:
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    def fetch_telemetry(self) -> PrinterTelemetry:
        """Fetch and normalize telemetry from the printer API.

        Must handle all exceptions and return a valid PrinterTelemetry instance,
        marking is_up=False and setting error_type when failing.
        """
        raise NotImplementedError
