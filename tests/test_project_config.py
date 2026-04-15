import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.project_config import ProjectConfig


def test_project_config_defaults():
    cfg = ProjectConfig(
        category="saas-ai-automation",
        template_version="saas-ai-automation.v1",
        architecture_doc_id="doc_xyz",
        architecture_doc_url="https://feishu.example/docx/doc_xyz",
    )
    assert cfg.category == "saas-ai-automation"
    assert cfg.template_version == "saas-ai-automation.v1"
    assert cfg.architecture_doc_id == "doc_xyz"
    assert cfg.architecture_doc_url == "https://feishu.example/docx/doc_xyz"
    assert cfg.tech_stack == {}
    assert cfg.design_system_doc_id is None


def test_project_config_from_dict_accepts_legacy_fields_and_ignores_them():
    cfg = ProjectConfig.from_dict({
        "category": "enterprise-bot",
        "template_version": "enterprise-bot.v1",
        "architecture_doc_id": "doc_a",
        "architecture_doc_url": "https://feishu.example/docx/doc_a",
        "tech_stack": {"language": "python"},
        # Legacy keys from pre-demolition state.json — must be ignored, not raise.
        "github_repo_url": "https://github.com/org/repo",
        "is_new_project": True,
        "architecture_yaml_initialized": True,
        "acm_registry_initialized": True,
        "onboarding_state": "COMPLETE",
    })
    assert cfg.category == "enterprise-bot"
    assert cfg.tech_stack == {"language": "python"}
    assert not hasattr(cfg, "github_repo_url")
    assert not hasattr(cfg, "onboarding_state")
