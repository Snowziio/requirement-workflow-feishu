"""Project Bootstrap orchestrator.

Runs a 7-step flow: validate → upsert config → create repo → populate →
create arch doc → create group → finalize. Each step is idempotent and
``--resume`` skips already-completed steps (based on bootstrap_log).
"""
from __future__ import annotations

import logging
import re

from ..architecture_templates import available_categories
from .types import BootstrapRequest


_logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")


class ValidationError(ValueError):
    """Raised by ``validate()`` on illegal inputs (Step 1)."""


class ProjectBootstrapService:
    def __init__(
        self,
        *,
        repo_tools,
        feishu_gateway,
        github_gateway,
        template_owner: str,
        template_repo: str,
        new_owner: str,
    ):
        self._repo_tools = repo_tools
        self._feishu = feishu_gateway
        self._github = github_gateway
        self._template_owner = template_owner
        self._template_repo = template_repo
        self._new_owner = new_owner

    def validate(self, request: BootstrapRequest) -> None:
        if not _NAME_RE.match(request.project):
            raise ValidationError(
                f"project name must match {_NAME_RE.pattern}: got {request.project!r}"
            )
        if request.category not in available_categories():
            raise ValidationError(
                f"unknown category {request.category!r}; available: {available_categories()}"
            )
        if not request.owner_user_id:
            raise ValidationError("owner_user_id is required")

        existing_configs = self._feishu.list_project_configs()
        if request.project in existing_configs and not request.resume:
            raise ValidationError(
                f"project {request.project} already exists; use --resume to continue"
            )

        existing_repo = self._github.get_repo(
            owner=self._new_owner, name=request.project
        )
        if existing_repo is not None and not request.resume:
            raise ValidationError(
                f"GitHub repo {self._new_owner}/{request.project} already exists"
            )
