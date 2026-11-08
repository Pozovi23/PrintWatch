"""Main entry point for printer-exporter service supporting N printers."""

import http.server
import logging
import signal
import sys
import threading
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pythonjsonlogger import json as jsonlogger

from exporter.collector import MultiPrinterCollector
from exporter.config import Settings
from exporter.metrics import PrinterMetrics


def setup_logging(log_level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def make_http_handler(collector: MultiPrinterCollector, metrics: PrinterMetrics):
    class ExporterRequestHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/metrics":
                data = generate_latest(metrics.registry)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path in ("/healthz", "/health"):
                if collector.is_healthy:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK\n")
                else:
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"UNHEALTHY\n")
            elif self.path == "/":
                html = (
                    b"<html><head><title>3D Printer Prometheus Exporter</title></head>"
                    b"<body><h1>3D Printer Prometheus Exporter</h1>"
                    b"<p><a href='/metrics'>Metrics</a> | <a href='/healthz'>Healthz</a></p>"
                    b"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self.send_response(404)
                self.end_headers()

    return ExporterRequestHandler


def run() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("exporter")

    printers = settings.load_all_printers()
    printers_info = [{"name": p.name, "host": p.host} for p in printers]

    logger.info(
        "Initializing 3D Printer Exporter for N printers",
        extra={
            "printers_count": len(printers),
            "printers": printers_info,
            "poll_interval": settings.poll_interval,
            "port": settings.port,
        },
    )

    metrics = PrinterMetrics()
    collector = MultiPrinterCollector(
        printers=printers,
        metrics=metrics,
        poll_interval=settings.poll_interval,
        timeout_seconds=settings.timeout_seconds,
    )

    # Initial synchronous fetch for all printers
    try:
        collector.collect_all_once()
    except Exception as e:
        logger.warning("Initial collection failed: %s", e)

    collector.start()

    handler_cls = make_http_handler(collector, metrics)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", settings.port), handler_cls)

    def shutdown(signum: int, frame: Any) -> None:
        logger.info("Shutdown signal received, stopping exporter...")
        collector.stop()
        threading.Thread(target=server.shutdown).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("Starting HTTP server on port %s", settings.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        logger.info("Exporter server stopped cleanly.")


if __name__ == "__main__":
    run()
