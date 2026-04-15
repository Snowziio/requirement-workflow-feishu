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
    assert cfg.github_repo_url == ""
    assert cfg.github_owner_username == ""


def test_project_config_from_dict_accepts_github_fields():
    cfg = ProjectConfig.from_dict({
        "category": "enterprise-bot",
        "template_version": "enterprise-bot.v1",
        "architecture_doc_id": "doc_a",
        "architecture_doc_url": "https://feishu.example/docx/doc_a",
        "tech_stack": {"language": "python"},
        "github_repo_url": "https://github.com/org/repo",
        "github_owner_username": "alice",
    })
    assert cfg.github_repo_url == "https://github.com/org/repo"
    assert cfg.github_owner_username == "alice"


def test_project_config_from_dict_ignores_legacy_onboarding_fields():
    cfg = ProjectConfig.from_dict({
        "category": "enterprise-bot",
        "template_version": "enterprise-bot.v1",
        "architecture_doc_id": "doc_a",
        "architecture_doc_url": "https://feishu.example/docx/doc_a",
        "is_new_project": True,
        "architecture_yaml_initialized": True,
        "acm_registry_initialized": True,
        "onboarding_state": "COMPLETE",
    })
    assert cfg.category == "enterprise-bot"
    assert not hasattr(cfg, "onboarding_state")
    assert not hasattr(cfg, "is_new_project")
