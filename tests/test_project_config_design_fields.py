"""ProjectConfig design-related field tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _minimal_data():
    return {
        "category": "enterprise-app",
        "template_version": "enterprise-app.v1",
        "architecture_doc_id": "doc1",
        "architecture_doc_url": "https://feishu.example/docx/doc1",
    }


def test_project_config_new_design_fields_default_empty():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig(**_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_reads_design_fields():
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["claude_design_project_url"] = "https://claude.ai/design/p/xyz"
    data["frontend_subpath"] = "src/myproj_webapp"
    data["frontend_tech_stack"] = {"framework": "React 18", "build": "Vite 5.x"}
    cfg = ProjectConfig.from_dict(data)
    assert cfg.claude_design_project_url == "https://claude.ai/design/p/xyz"
    assert cfg.frontend_subpath == "src/myproj_webapp"
    assert cfg.frontend_tech_stack == {"framework": "React 18", "build": "Vite 5.x"}


def test_project_config_from_dict_missing_design_fields_default_gracefully():
    from requirement_workflow_v12.project_config import ProjectConfig
    cfg = ProjectConfig.from_dict(_minimal_data())
    assert cfg.claude_design_project_url == ""
    assert cfg.frontend_subpath == ""
    assert cfg.frontend_tech_stack == {}


def test_project_config_from_dict_tolerates_non_dict_frontend_tech_stack():
    """Bitable may return None or a string if parse fails; coerce to empty dict."""
    from requirement_workflow_v12.project_config import ProjectConfig
    data = _minimal_data()
    data["frontend_tech_stack"] = None
    cfg = ProjectConfig.from_dict(data)
    assert cfg.frontend_tech_stack == {}
