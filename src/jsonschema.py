"""Tiny local fallback for the subset of jsonschema used by tests.

The production service does not import jsonschema at runtime. This module keeps
the repository's static schema tests runnable in minimal environments where the
third-party package is not installed.
"""
from __future__ import annotations

import re
from typing import Any


class ValidationError(Exception):
    pass


def validate(instance: Any, schema: dict[str, Any]) -> None:
    _validate(instance, schema, path="$")


def _validate(instance: Any, schema: dict[str, Any], *, path: str) -> None:
    typ = schema.get("type")
    if typ == "object":
        if not isinstance(instance, dict):
            raise ValidationError(f"{path}: expected object")
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                raise ValidationError(f"{path}: missing required property {key}")
        if schema.get("additionalProperties") is False:
            allowed = set((schema.get("properties") or {}).keys())
            extra = set(instance.keys()) - allowed
            if extra:
                raise ValidationError(f"{path}: unexpected properties {sorted(extra)}")
        for key, child_schema in (schema.get("properties") or {}).items():
            if key in instance:
                _validate(instance[key], child_schema, path=f"{path}.{key}")
        return

    if typ == "string":
        if not isinstance(instance, str):
            raise ValidationError(f"{path}: expected string")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < int(min_length):
            raise ValidationError(f"{path}: shorter than minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, instance) is None:
            raise ValidationError(f"{path}: does not match pattern")

    if "const" in schema and instance != schema["const"]:
        raise ValidationError(f"{path}: expected const {schema['const']!r}")
