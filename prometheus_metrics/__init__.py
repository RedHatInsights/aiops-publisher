"""Metrics interface."""

from .prometheus_metrics import generate_latest_metrics, METRICS

__all__ = ["generate_latest_metrics", "METRICS"]
