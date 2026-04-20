"""Unit tests for render_template's seed kwarg."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.architecture_templates import render_template  # noqa: E402


def test_render_template_substitutes_seed_fields():
    version, text = render_template(
        "saas-ai-automation",
        project="test5",
        seed={
            "display_name": "Test 5 Display",
            "brief": "解决 X 场景的 Y 自动化",
            "tech_stack": "FastAPI + OpenAI + PostgreSQL",
        },
    )
    assert version.startswith("saas-ai-automation.v")
    assert "Test 5 Display" in text
    assert "解决 X 场景的 Y 自动化" in text
    assert "FastAPI + OpenAI + PostgreSQL" in text
    # Existing placeholders still work
    assert "test5" in text
    assert "{pkg}" not in text
    assert "{project}" not in text


def test_render_template_seed_missing_fields_become_empty():
    version, text = render_template(
        "saas-ai-automation",
        project="test6",
        seed={"display_name": "Only Name"},
    )
    assert "Only Name" in text
    assert "{{display_name}}" not in text
    assert "{{brief}}" not in text
    assert "{{tech_stack}}" not in text


def test_render_template_no_seed_still_works():
    """Backward-compat: callers not passing seed still get a valid render."""
    version, text = render_template("saas-ai-automation", project="test7")
    assert "test7" in text
    assert "{{display_name}}" not in text
    assert "{{brief}}" not in text
    assert "{{tech_stack}}" not in text
