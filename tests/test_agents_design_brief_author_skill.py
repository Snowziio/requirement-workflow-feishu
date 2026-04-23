"""Static validation for design-brief-author SKILL.md + callback schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "docs" / "agents" / "design-brief-author"


def test_skill_md_exists():
    assert (SKILL_DIR / "SKILL.md").is_file()


def test_skill_md_yaml_frontmatter_parses():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.index("\n---\n", 4)
    raw = text[4:end]
    fm = yaml.safe_load(raw)
    assert isinstance(fm, dict)
    assert fm["name"] == "design-brief-author"
    assert isinstance(fm.get("description"), str) and len(fm["description"]) > 20


def test_skill_md_has_hard_behavior_contract():
    """Mirror plan-author's '行为合同' pattern: first tool call must be the callback."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "行为合同" in text
    assert "curl" in text and "200" in text


def test_skill_md_mentions_single_turn():
    """Skill must explicitly state it's single-turn (no multi-turn dialogue)."""
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "单轮" in text or "single-turn" in text.lower()


def test_skill_md_lists_design_context_endpoint():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "/queries/openclaw/design-context/" in text


def test_skill_md_lists_design_callback_endpoint():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "/openclaw/design-callback" in text
    assert "design_brief_submit" in text


def test_callback_schema_is_valid_draft07():
    schema_path = SKILL_DIR / "callback-schema.json"
    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["title"]


def test_callback_schema_accepts_valid_payload():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    valid = {
        "req_id": "REQ-TEST-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "schema_version: '1.0'\nreq_id: REQ-TEST-001\n",
            "brief_markdown_body": "# Brief\n\n## 背景\n...",
        },
    }
    jsonschema.validate(valid, schema)


def test_callback_schema_rejects_wrong_event():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "REQ-TEST-001",
        "event": "some_other_event",
        "payload": {
            "brief_yaml_frontmatter": "x",
            "brief_markdown_body": "y",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_callback_schema_rejects_empty_frontmatter():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "REQ-TEST-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "",
            "brief_markdown_body": "non-empty",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)


def test_callback_schema_rejects_wrong_req_id_prefix():
    import jsonschema
    schema_path = SKILL_DIR / "callback-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    invalid = {
        "req_id": "NOTREQ-001",
        "event": "design_brief_submit",
        "payload": {
            "brief_yaml_frontmatter": "x",
            "brief_markdown_body": "y",
        },
    }
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(invalid, schema)
