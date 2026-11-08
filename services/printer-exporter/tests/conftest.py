"""Pytest fixtures for printer exporter tests."""

import pytest
from exporter.metrics import PrinterMetrics
from prometheus_client import CollectorRegistry


@pytest.fixture
def test_registry():
    """Isolated Prometheus CollectorRegistry for tests."""
    return CollectorRegistry(auto_describe=True)


@pytest.fixture
def test_metrics(test_registry):
    """PrinterMetrics initialized with isolated registry."""
    return PrinterMetrics(registry=test_registry)
