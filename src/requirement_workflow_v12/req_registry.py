"""Append new REQ rows to ``project/req-registry.yaml`` in a project repo.

Best-effort helper invoked after a requirement is provisioned. Failures do
not abort REQ creation; they are logged so operators can reconcile later.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import yaml

from .github_gateway import FileChange, GitHubGatewayError

if TYPE_CHECKING:
    from .github_gateway import GitHubGateway


_logger = logging.getLogger(__name__)

_REGISTRY_PATH = "project/req-registry.yaml"


class RegistryAppendError(RuntimeError):
    """Raised when the registry YAML cannot be parsed or rendered."""


def render_registry_with_new_req(
    *,
    original_text: str,
    req_id: str,
    title: str,
    status: str,
    created_at: str,
) -> str:
    try:
        data = yaml.safe_load(original_text) or {}
    except yaml.YAMLError as exc:
        raise RegistryAppendError(f"req-registry parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryAppendError("req-registry top-level must be a mapping")
    requirements = data.get("requirements") or []
    if not isinstance(requirements, list):
        raise RegistryAppendError("req-registry 'requirements' must be a list")
    requirements.append(
        {
            "req_id": req_id,
            "title": title,
            "status": status,
            "plan_id": None,
            "spec_pr": None,
            "created_at": created_at,
        }
    )
    data["requirements"] = requirements
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def append_req_to_registry(
    *,
    github_gateway: "GitHubGateway",
    project_repo: str,
    req_id: str,
    title: str,
    status: str,
    created_at: str,
    swallow_errors: bool = True,
) -> None:
    owner, repo = project_repo.split("/", 1)
    try:
        _sha, original = github_gateway.fetch_file_sha(
            project_repo, "main", _REGISTRY_PATH,
        )
        new_text = render_registry_with_new_req(
            original_text=original,
            req_id=req_id,
            title=title,
            status=status,
            created_at=created_at,
        )
        github_gateway.commit_files(
            owner=owner,
            repo=repo,
            branch="main",
            files=[FileChange(path=_REGISTRY_PATH, content=new_text)],
            message=f"chore(req-registry): append {req_id}",
        )
    except (GitHubGatewayError, RegistryAppendError) as exc:
        if swallow_errors:
            _logger.warning(
                "req-registry append failed for %s @ %s: %s",
                req_id, project_repo, exc,
            )
            return
        raise
