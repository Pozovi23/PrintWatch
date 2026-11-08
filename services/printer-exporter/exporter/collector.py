"""Telemetry collector orchestrating API queries and Prometheus metric updates for N printers."""

import logging
import threading
import time
from exporter.adapters.base import BaseAdapter, PrinterTelemetry
from exporter.adapters import get_adapter
from exporter.config import PrinterConfig
from exporter.metrics import PrinterMetrics

logger = logging.getLogger(__name__)

ALL_STATES = ("idle", "printing", "paused", "error", "offline")


class TelemetryCollector:
    """Periodically scrapes telemetry for a single printer."""

    def __init__(
        self,
        adapter: BaseAdapter,
        metrics: PrinterMetrics,
        printer_name: str,
        poll_interval: float = 5.0,
    ) -> None:
        self.adapter = adapter
        self.metrics = metrics
        self.printer_name = printer_name
        self.poll_interval = poll_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._last_successful_scrape: float = 0.0
        self._consecutive_failures: int = 0

    @property
    def is_healthy(self) -> bool:
        return self._running and (self._consecutive_failures < 12)

    def collect_once(self) -> PrinterTelemetry:
        telemetry = self.adapter.fetch_telemetry()

        # 1. Доступность
        self.metrics.printer_up.labels(
            printer=self.printer_name,
        ).set(1 if telemetry.is_up else 0)

        # 2. Статус (взаимоисключающие лейблы)
        active_state = telemetry.state if telemetry.state in ALL_STATES else "offline"
        for st in ALL_STATES:
            self.metrics.printer_state.labels(printer=self.printer_name, state=st).set(
                1 if st == active_state else 0,
            )

        # 3. Температуры (поддержка динамически обнаруженных датчиков и обратная совместимость)
        if telemetry.temperatures:
            for tool_name, temp_val in telemetry.temperatures.items():
                self.metrics.printer_temperature_celsius.labels(
                    printer=self.printer_name,
                    tool=tool_name,
                ).set(temp_val)
        else:
            self.metrics.printer_temperature_celsius.labels(
                printer=self.printer_name,
                tool="extruder",
            ).set(telemetry.extruder_temp)
            self.metrics.printer_temperature_celsius.labels(
                printer=self.printer_name,
                tool="bed",
            ).set(telemetry.bed_temp)

        if telemetry.temperature_targets:
            for tool_name, target_val in telemetry.temperature_targets.items():
                self.metrics.printer_temperature_target_celsius.labels(
                    printer=self.printer_name,
                    tool=tool_name,
                ).set(target_val)
        else:
            self.metrics.printer_temperature_target_celsius.labels(
                printer=self.printer_name,
                tool="extruder",
            ).set(telemetry.extruder_target)
            self.metrics.printer_temperature_target_celsius.labels(
                printer=self.printer_name,
                tool="bed",
            ).set(telemetry.bed_target)

        # 4. Прогресс и время печати
        self.metrics.printer_print_progress_ratio.labels(
            printer=self.printer_name,
        ).set(telemetry.progress_ratio)
        self.metrics.printer_print_time_left_seconds.labels(
            printer=self.printer_name,
        ).set(telemetry.time_left_seconds)
        self.metrics.printer_print_time_elapsed_seconds.labels(
            printer=self.printer_name,
        ).set(telemetry.time_elapsed_seconds)

        # 5. Гистограмма задержек
        for endpoint, duration in telemetry.endpoint_latencies.items():
            self.metrics.printer_api_latency_seconds.labels(
                printer=self.printer_name,
                endpoint=endpoint,
            ).observe(duration)

        # 6. Ошибки API
        if telemetry.error_type:
            self.metrics.printer_api_errors_total.labels(
                printer=self.printer_name,
                type=telemetry.error_type,
            ).inc()
            self._consecutive_failures += 1
            logger.warning(
                "Telemetry collection error",
                extra={
                    "printer": self.printer_name,
                    "error_type": telemetry.error_type,
                    "error_message": telemetry.error_message,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
        else:
            self._last_successful_scrape = time.time()
            self._consecutive_failures = 0
            logger.info(
                "Telemetry collected",
                extra={
                    "printer": self.printer_name,
                    "state": telemetry.state,
                    "extruder_temp": telemetry.extruder_temp,
                    "bed_temp": telemetry.bed_temp,
                    "progress_pct": round(telemetry.progress_ratio * 100, 1),
                },
            )

        # 7. Метаданные
        try:
            self.metrics.printer_info.labels(
                printer=self.printer_name,
                version=telemetry.version,
                job_filename=telemetry.filename,
            ).set(1)
        except Exception:
            pass

        return telemetry

    def _loop(self) -> None:
        while self._running:
            start_time = time.time()
            try:
                self.collect_once()
            except Exception as e:
                logger.exception("Unexpected exception in collector loop [%s]: %s", self.printer_name, e)

            elapsed = time.time() - start_time
            sleep_duration = max(0.5, self.poll_interval - elapsed)
            sleep_end = time.time() + sleep_duration
            while self._running and time.time() < sleep_end:
                time.sleep(0.2)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name=f"collector-{self.printer_name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)


class MultiPrinterCollector:
    """Manages independent background collectors for N printers."""

    def __init__(
        self,
        printers: list[PrinterConfig],
        metrics: PrinterMetrics,
        poll_interval: float = 5.0,
        timeout_seconds: float = 3.5,
    ) -> None:
        self.metrics = metrics
        self.poll_interval = poll_interval
        self.collectors: list[TelemetryCollector] = []

        for p in printers:
            api_key_str = p.api_key.get_secret_value() if p.api_key else None
            adapter = get_adapter(
                host=p.host,
                api_key=api_key_str,
                timeout=timeout_seconds,
            )
            collector = TelemetryCollector(
                adapter=adapter,
                metrics=metrics,
                printer_name=p.name,
                poll_interval=poll_interval,
            )
            self.collectors.append(collector)

    @property
    def is_healthy(self) -> bool:
        # Healthy if all active collectors are running
        return any(c.is_healthy for c in self.collectors) if self.collectors else True

    def collect_all_once(self) -> None:
        """Execute one immediate scrape cycle for all printers."""
        for c in self.collectors:
            try:
                c.collect_once()
            except Exception as e:
                logger.warning("Scrape error on %s: %s", c.printer_name, e)

    def start(self) -> None:
        """Start isolated collector threads for all N printers."""
        for c in self.collectors:
            c.start()
        logger.info("Multi-printer collector started for %d printers", len(self.collectors))

    def stop(self) -> None:
        """Stop all collector threads."""
        for c in self.collectors:
            c.stop()
        logger.info("Multi-printer collector stopped")
