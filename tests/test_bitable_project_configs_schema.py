"""Contract tests for bitable_project_configs_schema.json.

Ensures every ProjectConfig field the Coordinator serializes has a
corresponding column definition in the on-disk schema.
"""
from __future__ import annotations

import json
from pathlib import Path


_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "bitable_project_configs_schema.json").read_text(
        encoding="utf-8"
    )
)


def _field_names() -> set[str]:
    return {f["name"] for f in _SCHEMA["fields"]}


def test_bootstrap_fields_present():
    names = _field_names()
    expected = {
        "引导状态",
        "引导日志JSON",
        "引导完成时间",
        "项目状态",
        "飞书群chat_id",
    }
    missing = expected - names
    assert not missing, f"missing bitable fields: {missing}"


def test_all_fields_declare_text_field_type():
    for spec in _SCHEMA["fields"]:
        assert spec.get("field_type") == "text", f"unexpected field_type for {spec['name']!r}"
