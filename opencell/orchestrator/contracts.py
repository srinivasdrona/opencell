"""JSON Schema validation for data contracts.

All parameter files, data exports, and pipeline inputs are validated
against JSON Schemas before being used. Called by CI and by the pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).parent.parent / "data" / "schemas"


def load_schema(schema_name: str) -> dict[str, Any]:
    """Load a JSON Schema by name."""
    schema_path = _SCHEMA_DIR / f"{schema_name}.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    with open(schema_path) as f:
        return json.load(f)


def validate_data(
    data: dict[str, Any],
    schema_name: str,
) -> list[str]:
    """Validate data against a named JSON Schema.

    Returns list of validation errors (empty if valid).
    """
    schema = load_schema(schema_name)
    validator = jsonschema.Draft7Validator(schema)
    errors = []
    for error in validator.iter_errors(data):
        errors.append(f"{error.json_path}: {error.message}")
    if errors:
        logger.warning(f"Schema validation failed ({schema_name}): {len(errors)} errors")
    return errors


def validate_parameter_file(filepath: str | Path) -> list[str]:
    """Validate a parameter YAML/JSON file against the parameter schema."""
    filepath = Path(filepath)
    with open(filepath) as f:
        if filepath.suffix in (".yml", ".yaml"):
            import yaml
            data = yaml.safe_load(f)
        else:
            data = json.load(f)

    if isinstance(data, list):
        all_errors = []
        for i, entry in enumerate(data):
            errors = validate_data(entry, "parameter")
            all_errors.extend([f"[{i}] {e}" for e in errors])
        return all_errors
    else:
        return validate_data(data, "parameter")
