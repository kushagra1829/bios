"""Deterministic business-data answering over the synthetic Product_Market_Monthly records."""
from backend.app.analytics.data_query import DataQueryEngine, parse_periods, resolve_measures

__all__ = ["DataQueryEngine", "parse_periods", "resolve_measures"]
