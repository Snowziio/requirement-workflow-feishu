from dataclasses import asdict
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def test_project_config_defaults():
    cfg = ProjectConfig(github_repo_url="https://github.com/org/repo", is_new_project=True, tech_stack={})
    assert cfg.architecture_yaml_initialized is False
    assert cfg.acm_registry_initialized is False
    assert cfg.design_system_doc_id is None
    assert cfg.onboarding_state == OnboardingState.COLLECTING_REPO


def test_project_config_serializable():
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=False,
        tech_stack={"language": "Python", "framework": "FastAPI"},
        architecture_yaml_initialized=True,
        acm_registry_initialized=True,
        design_system_doc_id="doc_abc123",
        onboarding_state=OnboardingState.COMPLETE,
    )
    d = asdict(cfg)
    assert d["github_repo_url"] == "https://github.com/org/repo"
    assert d["tech_stack"]["language"] == "Python"
    assert d["onboarding_state"] == "COMPLETE"
