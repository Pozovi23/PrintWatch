"""Prometheus metrics definitions and helper registry."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class PrinterMetrics:
    """Encapsulates all Prometheus metrics for a printer."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)

        self.printer_up = Gauge(
            "printer_up",
            "Indicates whether the printer is reachable and responding to API queries (1=up, 0=down)",
            ["printer"],
            registry=self.registry,
        )

        self.printer_state = Gauge(
            "printer_state",
            "Current operational state of the printer (1 for active state, 0 otherwise)",
            ["printer", "state"],
            registry=self.registry,
        )

        self.printer_temperature_celsius = Gauge(
            "printer_temperature_celsius",
            "Current temperature of printer component in Celsius",
            ["printer", "tool"],
            registry=self.registry,
        )

        self.printer_temperature_target_celsius = Gauge(
            "printer_temperature_target_celsius",
            "Target temperature of printer component in Celsius",
            ["printer", "tool"],
            registry=self.registry,
        )

        self.printer_print_progress_ratio = Gauge(
            "printer_print_progress_ratio",
            "Print progress ratio (0.0 to 1.0)",
            ["printer"],
            registry=self.registry,
        )

        self.printer_print_time_left_seconds = Gauge(
            "printer_print_time_left_seconds",
            "Estimated print time remaining in seconds",
            ["printer"],
            registry=self.registry,
        )

        self.printer_print_time_elapsed_seconds = Gauge(
            "printer_print_time_elapsed_seconds",
            "Print time elapsed in seconds",
            ["printer"],
            registry=self.registry,
        )

        self.printer_api_latency_seconds = Histogram(
            "printer_api_latency_seconds",
            "API request response latency in seconds",
            ["printer", "endpoint"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry,
        )

        self.printer_api_errors_total = Counter(
            "printer_api_errors_total",
            "Total count of printer API errors encountered",
            ["printer", "type"],
            registry=self.registry,
        )

        self.printer_info = Gauge(
            "printer_info",
            "Printer static information and active print job details",
            ["printer", "version", "job_filename"],
            registry=self.registry,
        )
