from requirement_workflow_v12.coordinator_service import CoordinatorService
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def _make_service() -> CoordinatorService:
    return CoordinatorService()


def test_is_new_project_when_no_config():
    svc = _make_service()
    assert svc.is_new_project("PROJ") is True


def test_is_not_new_project_when_config_exists():
    svc = _make_service()
    svc.project_configs["PROJ"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    assert svc.is_new_project("PROJ") is False


def test_register_project_config():
    svc = _make_service()
    cfg = svc.register_project_config(
        project="PROJ",
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={"language": "Python"},
    )
    assert cfg.github_repo_url == "https://github.com/org/repo"
    assert cfg.onboarding_state == OnboardingState.COLLECTING_PROJECT_TYPE
    assert "PROJ" in svc.project_configs


def test_advance_onboarding_state():
    svc = _make_service()
    svc.register_project_config("PROJ", "https://github.com/org/repo", True, {})
    svc.advance_onboarding_state("PROJ", OnboardingState.COLLECTING_TECH_STACK)
    assert svc.project_configs["PROJ"].onboarding_state == OnboardingState.COLLECTING_TECH_STACK


def test_complete_onboarding():
    svc = _make_service()
    svc.register_project_config("PROJ", "https://github.com/org/repo", True, {"language": "Python"})
    svc.complete_onboarding("PROJ", architecture_initialized=True, acm_initialized=True)
    cfg = svc.project_configs["PROJ"]
    assert cfg.onboarding_state == OnboardingState.COMPLETE
    assert cfg.architecture_yaml_initialized is True
    assert cfg.acm_registry_initialized is True


def test_restore_snapshot_includes_project_configs():
    svc = _make_service()
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    svc.restore_snapshot({}, {}, {}, {"PROJ": cfg})
    assert "PROJ" in svc.project_configs


def test_should_create_design_system_no_config():
    svc = _make_service()
    assert svc.should_create_design_system("PROJ") is False


def test_should_create_design_system_no_doc_yet():
    svc = _make_service()
    svc.project_configs["PROJ"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
    )
    assert svc.should_create_design_system("PROJ") is True


def test_should_not_create_design_system_already_exists():
    svc = _make_service()
    svc.project_configs["PROJ"] = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={},
        onboarding_state=OnboardingState.COMPLETE,
        design_system_doc_id="doc_abc",
    )
    assert svc.should_create_design_system("PROJ") is False
