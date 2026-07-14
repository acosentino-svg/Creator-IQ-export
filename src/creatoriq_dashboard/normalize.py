"""Maps raw CreatorIQ API records onto the dashboard's normalized schema.

The mapping itself lives in config/field_mappings.yaml so it can be adjusted
per-account without touching this code.
"""
from __future__ import annotations

from typing import Any

from .api_client import get_path


def normalize_record(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Apply a {normalized_field: raw_dotted_path} mapping to one raw record."""
    return {normalized_field: get_path(raw, raw_path) for normalized_field, raw_path in mapping.items()}


def normalize_records(raw_records: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [normalize_record(r, mapping) for r in raw_records]
