from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from .github_client import GitHubClient
from .models import Requirement, WorkflowStatus


ARCHITECTURE_YAML_DEFAULT_PATH = "ARCHITECTURE.yaml"

SPEC_CONTEXT_ALLOWED_STATUSES = {
    WorkflowStatus.APPROVED,
    WorkflowStatus.SPEC_DRAFTING,
}


class SpecContextGateError(Exception):
    """Requirement is not in a state that permits spec-context retrieval."""

    def __init__(self, message: str, current_status: str) -> None:
        super().__init__(message)
        self.current_status = current_status


class SpecContextMisconfigured(Exception):
    """Project lacks configuration required to serve spec-context."""


@dataclass
class SpecContextResult:
    context: dict
    context_token: str


class SpecContextBuilder:
    def __init__(
        self,
        service,
        github_client: GitHubClient,
        *,
        architecture_yaml_path: str = ARCHITECTURE_YAML_DEFAULT_PATH,
    ) -> None:
        self._service = service
        self._github = github_client
        self._arch_path = architecture_yaml_path

    def build(self, req_id: str) -> SpecContextResult:
        requirement = self._service.get_requirement(req_id)
        if requirement is None:
            raise ValueError(f"未知需求：{req_id}")

        if requirement.status not in SPEC_CONTEXT_ALLOWED_STATUSES:
            raise SpecContextGateError(
                f"当前状态 {requirement.status.value} 不允许获取 spec-context",
                current_status=requirement.status.value,
            )

        project_cfg = self._service.project_configs.get(requirement.project)
        if project_cfg is None:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 未完成 onboarding"
            )
        if not project_cfg.github_repo_url:
            raise SpecContextMisconfigured(
                f"项目 {requirement.project} 缺少 github_repo_url"
            )

        fetched = self._github.fetch_file(project_cfg.github_repo_url, self._arch_path)

        context_token = self._mint_token(req_id)
        requirement.active_spec_context_token = context_token

        context = {
            "req_id": requirement.req_id,
            "name": requirement.name,
            "project": requirement.project,
            "status": requirement.status.value,
            "needs_ui": requirement.needs_ui,
            "hifi_prototype_url": requirement.hifi_prototype_url,
            "design_system_snapshot": None,
            "requirement_document_url": requirement.document_url,
            "spec_document_url": requirement.spec_document_url,
            "spec_document_id": requirement.spec_document_id,
            "architecture_yaml": fetched.content,
            "architecture_commit_sha": fetched.commit_sha,
            "github_repo_url": project_cfg.github_repo_url,
            "latest_review_summary": requirement.latest_review_summary,
        }
        return SpecContextResult(context=context, context_token=context_token)

    @staticmethod
    def _mint_token(req_id: str) -> str:
        return f"spec_ctx_{req_id}_{int(time.time())}_{secrets.token_hex(4)}"
