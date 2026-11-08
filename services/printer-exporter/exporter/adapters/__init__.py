"""Adapter exports for Moonraker / Klipper API."""

from typing import Optional
from exporter.adapters.base import BaseAdapter, PrinterTelemetry
from exporter.adapters.moonraker import MoonrakerAdapter


def get_adapter(
    host: str,
    api_key: Optional[str] = None,
    timeout: float = 3.5,
) -> MoonrakerAdapter:
    """Factory creating the Moonraker API adapter."""
    return MoonrakerAdapter(host=host, api_key=api_key, timeout=timeout)


__all__ = ["BaseAdapter", "PrinterTelemetry", "MoonrakerAdapter", "get_adapter"]
