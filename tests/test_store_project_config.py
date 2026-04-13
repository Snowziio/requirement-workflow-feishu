from tempfile import NamedTemporaryFile
from requirement_workflow_v12.store import JsonStateStore
from requirement_workflow_v12.project_config import OnboardingState, ProjectConfig


def _make_store() -> JsonStateStore:
    f = NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return JsonStateStore(f.name)


def test_store_saves_and_loads_project_configs():
    store = _make_store()
    cfg = ProjectConfig(
        github_repo_url="https://github.com/org/repo",
        is_new_project=True,
        tech_stack={"language": "Python"},
        architecture_yaml_initialized=True,
        onboarding_state=OnboardingState.COMPLETE,
    )
    store.save_snapshot({}, {}, {}, project_configs={"PROJ": cfg})
    _, _, _, loaded = store.load_snapshot()
    assert "PROJ" in loaded
    assert loaded["PROJ"].github_repo_url == "https://github.com/org/repo"
    assert loaded["PROJ"].architecture_yaml_initialized is True
    assert loaded["PROJ"].onboarding_state == OnboardingState.COMPLETE


def test_store_loads_empty_project_configs_when_missing():
    store = _make_store()
    store.save_snapshot({}, {}, {}, project_configs={})
    _, _, _, loaded = store.load_snapshot()
    assert loaded == {}
