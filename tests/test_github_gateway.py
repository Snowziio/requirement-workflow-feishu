"""Unit tests for GitHubGateway using httpx MockTransport (no real network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.config import Settings
from requirement_workflow_v12.github_gateway import (
    FileChange,
    GitHubGateway,
    GitHubGatewayError,
)


def _gateway_with(handler) -> GitHubGateway:
    settings = Settings(github_token="ghp_test", github_default_branch="main")
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="https://api.github.com",
        headers={"Authorization": "token ghp_test"},
    )
    return GitHubGateway(settings, client=client)


def test_create_repo_from_template_returns_html_url():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/repos/Snowziio/harness-scaffold/generate"
        body = json.loads(req.content)
        assert body == {
            "owner": "Snowziio",
            "name": "proj-foo",
            "private": True,
            "description": "",
            "include_all_branches": False,
        }
        return httpx.Response(201, json={"html_url": "https://github.com/Snowziio/proj-foo"})

    gw = _gateway_with(handler)
    url = gw.create_repo_from_template(
        template_owner="Snowziio",
        template_repo="harness-scaffold",
        owner="Snowziio",
        name="proj-foo",
    )
    assert url == "https://github.com/Snowziio/proj-foo"


def test_create_branch_resolves_base_sha_then_creates_ref():
    seen_paths: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_paths.append(req.url.path)
        if req.url.path == "/repos/o/r/git/refs/heads/main":
            return httpx.Response(200, json={"object": {"sha": "base_sha_123"}})
        if req.url.path == "/repos/o/r/git/refs":
            body = json.loads(req.content)
            assert body == {"ref": "refs/heads/spec/REQ-X-1", "sha": "base_sha_123"}
            return httpx.Response(201, json={"object": {"sha": "new_sha_456"}})
        return httpx.Response(404)

    gw = _gateway_with(handler)
    sha = gw.create_branch(owner="o", repo="r", branch="spec/REQ-X-1")
    assert sha == "new_sha_456"
    assert seen_paths == [
        "/repos/o/r/git/refs/heads/main",
        "/repos/o/r/git/refs",
    ]


def test_commit_files_walks_full_git_data_api():
    seen: list[tuple[str, str]] = []  # (method, path)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, req.url.path))
        path = req.url.path
        if req.method == "GET" and path == "/repos/o/r/git/refs/heads/spec/REQ-X-1":
            return httpx.Response(200, json={"object": {"sha": "branch_head"}})
        if req.method == "GET" and path == "/repos/o/r/git/commits/branch_head":
            return httpx.Response(200, json={"tree": {"sha": "tree_base"}})
        if req.method == "POST" and path == "/repos/o/r/git/blobs":
            body = json.loads(req.content)
            assert body["encoding"] == "base64"
            return httpx.Response(201, json={"sha": f"blob_{len(seen)}"})
        if req.method == "POST" and path == "/repos/o/r/git/trees":
            body = json.loads(req.content)
            assert body["base_tree"] == "tree_base"
            assert {e["path"] for e in body["tree"]} == {"a.md", "b.yaml"}
            return httpx.Response(201, json={"sha": "new_tree"})
        if req.method == "POST" and path == "/repos/o/r/git/commits":
            body = json.loads(req.content)
            assert body == {
                "message": "spec: REQ-X-1 four files",
                "tree": "new_tree",
                "parents": ["branch_head"],
            }
            return httpx.Response(201, json={"sha": "new_commit_sha"})
        if req.method == "PATCH" and path == "/repos/o/r/git/refs/heads/spec/REQ-X-1":
            body = json.loads(req.content)
            assert body == {"sha": "new_commit_sha", "force": False}
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"message": f"unmatched {req.method} {path}"})

    gw = _gateway_with(handler)
    sha = gw.commit_files(
        owner="o",
        repo="r",
        branch="spec/REQ-X-1",
        files=[FileChange("a.md", "hello"), FileChange("b.yaml", "x: 1")],
        message="spec: REQ-X-1 four files",
    )
    assert sha == "new_commit_sha"
    methods = [m for m, _ in seen]
    assert methods.count("POST") == 4  # 2 blobs + tree + commit
    assert methods[-1] == "PATCH"


def test_commit_files_rejects_empty_payload():
    gw = _gateway_with(lambda req: httpx.Response(500))
    with pytest.raises(ValueError, match="at least one"):
        gw.commit_files(owner="o", repo="r", branch="b", files=[], message="m")


def test_open_pull_request_returns_number_and_url():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/repos/o/r/pulls"
        body = json.loads(req.content)
        assert body == {
            "title": "Spec: REQ-X-1",
            "head": "spec/REQ-X-1",
            "base": "main",
            "body": "spec_source_revision=rev-12",
        }
        return httpx.Response(
            201, json={"number": 42, "html_url": "https://github.com/o/r/pull/42"}
        )

    gw = _gateway_with(handler)
    pr = gw.open_pull_request(
        owner="o",
        repo="r",
        head_branch="spec/REQ-X-1",
        title="Spec: REQ-X-1",
        body="spec_source_revision=rev-12",
    )
    assert pr == {"number": 42, "html_url": "https://github.com/o/r/pull/42"}


def test_non_2xx_raises_gateway_error_with_status():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Resource not accessible"})

    gw = _gateway_with(handler)
    with pytest.raises(GitHubGatewayError) as exc:
        gw.create_repo_from_template(
            template_owner="t", template_repo="r", owner="o", name="n"
        )
    assert exc.value.status == 403
    assert "Resource not accessible" in str(exc.value)


def test_constructor_requires_token():
    settings = Settings(github_token="")
    with pytest.raises(ValueError, match="github_token"):
        GitHubGateway(settings)


def test_fetch_file_sha_returns_sha_and_content():
    import base64

    encoded = base64.b64encode(b"hello").decode("ascii")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/repos/o/r/contents/path.yaml"
        assert req.url.params["ref"] == "main"
        return httpx.Response(
            200,
            json={"sha": "abc123", "content": encoded, "encoding": "base64"},
        )

    gw = _gateway_with(handler)
    sha, content = gw.fetch_file_sha("o/r", "main", "path.yaml")
    assert sha == "abc123"
    assert content == "hello"


# --- delete_branch tests --------------------------------------------------


def test_delete_branch_sends_delete_to_correct_path():
    """DELETE is sent to /repos/o/r/git/refs/heads/<branch>."""

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        assert req.url.path == "/repos/o/r/git/refs/heads/spec/REQ-X"
        return httpx.Response(204)

    gw = _gateway_with(handler)
    gw.delete_branch("o/r", "spec/REQ-X")  # must not raise


def test_delete_branch_204_does_not_raise():
    gw = _gateway_with(lambda req: httpx.Response(204))
    gw.delete_branch("o/r", "spec/REQ-X")  # idempotent success


def test_delete_branch_404_is_idempotent():
    """404 means branch already gone — should not raise."""
    gw = _gateway_with(lambda req: httpx.Response(404, json={"message": "Reference does not exist"}))
    gw.delete_branch("o/r", "spec/REQ-X")  # must not raise


def test_delete_branch_422_is_idempotent():
    """422 (stale ref / already deleted) — should not raise."""
    gw = _gateway_with(lambda req: httpx.Response(422, json={"message": "Reference update failed"}))
    gw.delete_branch("o/r", "spec/REQ-X")  # must not raise


def test_delete_branch_non_2xx_raises_gateway_error():
    """Any other non-2xx (e.g. 403, 500) raises GitHubGatewayError."""
    gw = _gateway_with(lambda req: httpx.Response(403, json={"message": "Forbidden"}))
    with pytest.raises(GitHubGatewayError) as exc:
        gw.delete_branch("o/r", "spec/REQ-X")
    assert exc.value.status == 403
