import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.github_client import (
    GitHubClient,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubTransientError,
    parse_repo_url,
)


def test_parse_repo_url_https():
    assert parse_repo_url("https://github.com/org/repo") == ("org", "repo")


def test_parse_repo_url_with_dot_git_suffix():
    assert parse_repo_url("https://github.com/org/repo.git") == ("org", "repo")


def test_parse_repo_url_with_trailing_slash():
    assert parse_repo_url("https://github.com/org/repo/") == ("org", "repo")


def test_parse_repo_url_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_repo_url("not-a-url")


import base64
import json as _json
from urllib.error import HTTPError, URLError


def _fake_response(payload: dict):
    ctx = MagicMock()
    ctx.__enter__ = lambda s: MagicMock(read=MagicMock(return_value=_json.dumps(payload).encode("utf-8")))
    ctx.__exit__ = lambda s, *a: False
    return ctx


def test_fetch_file_success():
    client = GitHubClient(token="t")
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(b"hello yaml").decode("ascii"),
        "sha": "abc123",
    }
    with patch("requirement_workflow_v12.github_client.urlopen", return_value=_fake_response(payload)):
        result = client.fetch_file("https://github.com/org/repo", "ARCHITECTURE.yaml")
    assert result.content == "hello yaml"
    assert result.commit_sha == "abc123"


def test_fetch_file_404_raises_not_found():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=404, msg="nf", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubNotFoundError):
            client.fetch_file("https://github.com/org/repo", "missing.yaml")


def test_fetch_file_401_raises_auth_error():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=401, msg="unauth", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubAuthError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")


def test_fetch_file_5xx_raises_transient():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=HTTPError(url="u", code=503, msg="down", hdrs=None, fp=None),
    ):
        with pytest.raises(GitHubTransientError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")


def test_fetch_file_network_error_raises_transient():
    import pytest
    client = GitHubClient(token="t")
    with patch(
        "requirement_workflow_v12.github_client.urlopen",
        side_effect=URLError("connection refused"),
    ):
        with pytest.raises(GitHubTransientError):
            client.fetch_file("https://github.com/org/repo", "x.yaml")
