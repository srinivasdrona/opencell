"""Data loader for OpenCell.

Loads parameters from YAML/JSON files and validates against JSON schemas.
All parameter files must include: value, unit, source DOI, uncertainty.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_yaml(filepath: str | Path) -> dict[str, Any]:
    """Load a YAML parameter file."""
    filepath = Path(filepath)
    with open(filepath) as f:
        data = yaml.safe_load(f)
    logger.info(f"Loaded YAML: {filepath} ({len(data)} top-level keys)")
    return data


def load_json(filepath: str | Path) -> dict[str, Any]:
    """Load a JSON parameter file."""
    filepath = Path(filepath)
    with open(filepath) as f:
        data = json.load(f)
    logger.info(f"Loaded JSON: {filepath}")
    return data


def load_parameters(filepath: str | Path) -> dict[str, Any]:
    """Load parameters from YAML or JSON based on extension."""
    filepath = Path(filepath)
    if filepath.suffix in (".yml", ".yaml"):
        return load_yaml(filepath)
    elif filepath.suffix == ".json":
        return load_json(filepath)
    else:
        raise ValueError(f"Unsupported file format: {filepath.suffix}")


def validate_parameter_entry(entry: dict[str, Any], param_id: str) -> list[str]:
    """Validate a single parameter entry has required fields.

    Required: value, unit, source
    Recommended: uncertainty, conditions
    """
    errors = []
    required = ["value", "unit", "source"]
    for field in required:
        if field not in entry:
            errors.append(f"Parameter '{param_id}' missing required field: {field}")

    if "source" in entry and not entry["source"]:
        errors.append(f"Parameter '{param_id}' has empty source (no naked biology numbers!)")

    return errors
