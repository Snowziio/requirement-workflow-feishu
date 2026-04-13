from unittest.mock import MagicMock, patch
from requirement_workflow_v12.project_bootstrapper import ProjectBootstrapper


def _make_bootstrapper(token: str = "ghp_test", branch: str = "main") -> ProjectBootstrapper:
    return ProjectBootstrapper(github_token=token, default_branch=branch)


def test_render_architecture_yaml():
    b = _make_bootstrapper()
    yaml_text = b.render_architecture_yaml(
        project="risk-platform",
        tech_stack={"language": "Python", "framework": "FastAPI", "database": "PostgreSQL", "test_framework": "pytest"},
    )
    assert "project: risk-platform" in yaml_text
    assert "language: Python" in yaml_text
    assert "framework: FastAPI" in yaml_text
    assert "services: []" in yaml_text
    assert "modules: []" in yaml_text
    assert "data_models: []" in yaml_text


def test_render_acm_registry_yaml():
    b = _make_bootstrapper()
    yaml_text = b.render_acm_registry_yaml()
    assert "registry: []" in yaml_text
    assert "last_updated:" in yaml_text


def test_bootstrap_new_project_calls_github_api():
    b = _make_bootstrapper()
    mock_repo = MagicMock()
    mock_repo.get_contents.side_effect = Exception("404 Not Found")

    with patch("requirement_workflow_v12.project_bootstrapper.Github") as MockGithub:
        MockGithub.return_value.get_repo.return_value = mock_repo
        b.bootstrap_new_project(
            repo_url="https://github.com/org/repo",
            project="risk-platform",
            tech_stack={"language": "Python", "framework": "FastAPI", "database": "PostgreSQL", "test_framework": "pytest"},
        )

    assert mock_repo.create_file.call_count == 2
    calls = [call.kwargs["path"] for call in mock_repo.create_file.call_args_list]
    assert "ARCHITECTURE.yaml" in calls
    assert "spec/registry/consolidated.yaml" in calls


def test_bootstrap_skips_existing_architecture_yaml():
    b = _make_bootstrapper()
    mock_repo = MagicMock()

    def get_contents_side_effect(path, **kwargs):
        if path == "ARCHITECTURE.yaml":
            return MagicMock()  # exists
        raise Exception("404 Not Found")  # ACM doesn't exist

    mock_repo.get_contents.side_effect = get_contents_side_effect

    with patch("requirement_workflow_v12.project_bootstrapper.Github") as MockGithub:
        MockGithub.return_value.get_repo.return_value = mock_repo
        b.bootstrap_new_project(
            repo_url="https://github.com/org/repo",
            project="risk-platform",
            tech_stack={"language": "Python"},
        )

    create_calls = [call.kwargs["path"] for call in mock_repo.create_file.call_args_list]
    assert "ARCHITECTURE.yaml" not in create_calls
    assert "spec/registry/consolidated.yaml" in create_calls


def test_repo_path_from_url():
    assert ProjectBootstrapper._repo_path_from_url("https://github.com/org/repo") == "org/repo"
    assert ProjectBootstrapper._repo_path_from_url("https://github.com/org/repo/") == "org/repo"
