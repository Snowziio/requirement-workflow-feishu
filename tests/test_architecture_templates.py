import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.architecture_templates import (
    UnknownCategory,
    available_categories,
    derive_pkg,
    render_template,
)


def test_available_categories_covers_five():
    cats = available_categories()
    assert set(cats) == {
        "public-web-site",
        "miniprogram",
        "enterprise-bot",
        "enterprise-app",
        "saas-ai-automation",
    }


@pytest.mark.parametrize("raw,expected", [
    ("MyApp", "my_app"),
    ("my-proj", "my_proj"),
    ("HARNESS", "harness"),
    ("Hello World 2", "hello_world_2"),
    ("已有项目", "已有项目"),  # non-ascii kept, non-alnum→_
])
def test_derive_pkg(raw, expected):
    assert derive_pkg(raw) == expected


def test_render_template_substitutes_placeholders():
    version, text = render_template("saas-ai-automation", project="MyApp")
    assert version == "saas-ai-automation.v1"
    assert "{pkg}" not in text
    assert "{project}" not in text
    assert "{date}" not in text
    assert "my_app" in text
    assert 'project: "MyApp"' in text
    assert "category: saas-ai-automation" in text


def test_render_template_unknown_category_raises():
    with pytest.raises(UnknownCategory):
        render_template("nonexistent", project="MyApp")


def test_render_template_picks_highest_v_number(tmp_path, monkeypatch):
    fake_dir = tmp_path / "architecture-templates"
    fake_dir.mkdir()
    (fake_dir / "miniprogram.v1.yaml").write_text("v1: {project}", encoding="utf-8")
    (fake_dir / "miniprogram.v2.yaml").write_text("v2: {project}", encoding="utf-8")
    from requirement_workflow_v12 import architecture_templates as mod
    monkeypatch.setattr(mod, "TEMPLATE_DIR", fake_dir)
    version, text = render_template("miniprogram", project="X")
    assert version == "miniprogram.v2"
    assert text == "v2: X"
