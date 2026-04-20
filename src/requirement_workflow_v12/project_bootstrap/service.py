"""Project Bootstrap orchestrator.

Runs a 7-step flow: validate → upsert config → create repo → populate →
create arch doc → create group → finalize. Each step is idempotent and
``--resume`` skips already-completed steps (based on bootstrap_log).
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace

from datetime import datetime, timezone

from ..architecture_templates import available_categories, render_template
from ..project_config import ProjectConfig
from .state import append_log_entry, last_completed_step
from .static_content import (
    PROJECT_README_MD,
    render_claude_md,
    render_environments_yaml,
    render_req_registry_yaml,
    render_secrets_todo,
    render_skill_md,
)
from .types import (
    BootstrapRequest,
    BootstrapResult,
    BootstrapStep,
    BootstrapStepError,
)


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

    def upsert_config(
        self, request: BootstrapRequest, *, template_version: str
    ) -> ProjectConfig:
        existing = self._feishu.list_project_configs().get(request.project)
        if existing is None:
            cfg = ProjectConfig(
                category=request.category,
                template_version=template_version,
                architecture_doc_id="",
                architecture_doc_url="",
                bootstrap_status="BOOTSTRAPPING",
                project_status="BOOTSTRAPPING",
            )
        else:
            cfg = replace(
                existing,
                category=request.category,
                template_version=template_version,
                bootstrap_status="BOOTSTRAPPING",
                project_status="BOOTSTRAPPING",
            )
        new_log = cfg.bootstrap_log
        if last_completed_step(new_log) < int(BootstrapStep.VALIDATE):
            new_log = append_log_entry(
                new_log, step=BootstrapStep.VALIDATE, status="ok"
            )
        new_log = append_log_entry(
            new_log, step=BootstrapStep.UPSERT_CONFIG, status="ok"
        )
        cfg = replace(cfg, bootstrap_log=new_log)
        self._feishu.upsert_project_config(request.project, cfg)
        return cfg

    def create_repo_and_populate(
        self,
        request: BootstrapRequest,
        *,
        template_version: str,
        rendered_architecture_md: str,
    ) -> ProjectConfig:
        cfg = self._feishu.list_project_configs()[request.project]
        last_step = last_completed_step(cfg.bootstrap_log)
        if last_step >= int(BootstrapStep.POPULATE_MAIN):
            _logger.info(
                "bootstrap: skipping create_repo+populate (already completed) project=%s",
                request.project,
            )
            return cfg

        populate_files = {
            "docs/ARCHITECTURE.md": rendered_architecture_md,
            "project/README.md": PROJECT_README_MD,
            "project/req-registry.yaml": render_req_registry_yaml(
                project=request.project
            ),
            "project/environments.yaml": render_environments_yaml(
                category=request.category
            ),
            "project/SECRETS-TODO.md": render_secrets_todo(category=request.category),
            "CLAUDE.md": render_claude_md(project=request.project),
            "SKILL.md": render_skill_md(project=request.project),
        }
        try:
            result = self._repo_tools.bootstrap_project_repo(
                template_owner=self._template_owner,
                template_repo=self._template_repo,
                new_owner=self._new_owner,
                new_name=request.project,
                populate_files=populate_files,
                populate_commit_message=(
                    f"project bootstrap: populate initial files for {request.project}"
                ),
                collaborator_username=request.github_username,
            )
        except Exception as exc:
            failed_log = append_log_entry(
                cfg.bootstrap_log,
                step=BootstrapStep.CREATE_REPO,
                status="error",
                error_msg=str(exc),
            )
            cfg = replace(cfg, bootstrap_log=failed_log)
            self._feishu.upsert_project_config(request.project, cfg)
            raise BootstrapStepError(
                step=BootstrapStep.CREATE_REPO, message=str(exc)
            ) from exc

        log = append_log_entry(
            cfg.bootstrap_log, step=BootstrapStep.CREATE_REPO, status="ok"
        )
        log = append_log_entry(log, step=BootstrapStep.POPULATE_MAIN, status="ok")
        cfg = replace(
            cfg,
            github_repo_url=result.html_url,
            github_owner_username=request.github_username or "",
            bootstrap_log=log,
        )
        self._feishu.upsert_project_config(request.project, cfg)
        return cfg

    def create_architecture_doc(
        self, request: BootstrapRequest, *, rendered_architecture_md: str
    ) -> ProjectConfig:
        cfg = self._feishu.list_project_configs()[request.project]
        if last_completed_step(cfg.bootstrap_log) >= int(
            BootstrapStep.CREATE_ARCHITECTURE_DOC
        ):
            _logger.info(
                "bootstrap: skipping create_architecture_doc (already ok) project=%s",
                request.project,
            )
            return cfg

        try:
            created = self._feishu.create_architecture_document(request.project)
            if created is None:
                raise BootstrapStepError(
                    step=BootstrapStep.CREATE_ARCHITECTURE_DOC,
                    message="create_architecture_document returned None (missing folder token)",
                )
            self._feishu.write_document_text(
                created.document_id, rendered_architecture_md
            )
        except Exception as exc:
            failed_log = append_log_entry(
                cfg.bootstrap_log,
                step=BootstrapStep.CREATE_ARCHITECTURE_DOC,
                status="error",
                error_msg=str(exc),
            )
            cfg = replace(cfg, bootstrap_log=failed_log)
            self._feishu.upsert_project_config(request.project, cfg)
            if isinstance(exc, BootstrapStepError):
                raise
            raise BootstrapStepError(
                step=BootstrapStep.CREATE_ARCHITECTURE_DOC, message=str(exc)
            ) from exc

        new_log = append_log_entry(
            cfg.bootstrap_log,
            step=BootstrapStep.CREATE_ARCHITECTURE_DOC,
            status="ok",
        )
        cfg = replace(
            cfg,
            architecture_doc_id=created.document_id,
            architecture_doc_url=created.document_url,
            bootstrap_log=new_log,
        )
        self._feishu.upsert_project_config(request.project, cfg)
        return cfg

    def create_feishu_group(self, request: BootstrapRequest) -> ProjectConfig:
        cfg = self._feishu.list_project_configs()[request.project]
        if last_completed_step(cfg.bootstrap_log) >= int(
            BootstrapStep.CREATE_FEISHU_GROUP
        ):
            _logger.info(
                "bootstrap: skipping create_feishu_group (already ok) project=%s",
                request.project,
            )
            return cfg

        try:
            created = self._feishu.create_project_group(
                project=request.project,
                owner_user_id=request.owner_user_id,
                member_user_ids=[request.owner_user_id],
            )
        except Exception as exc:
            failed_log = append_log_entry(
                cfg.bootstrap_log,
                step=BootstrapStep.CREATE_FEISHU_GROUP,
                status="error",
                error_msg=str(exc),
            )
            cfg = replace(cfg, bootstrap_log=failed_log)
            self._feishu.upsert_project_config(request.project, cfg)
            raise BootstrapStepError(
                step=BootstrapStep.CREATE_FEISHU_GROUP, message=str(exc)
            ) from exc

        new_log = append_log_entry(
            cfg.bootstrap_log,
            step=BootstrapStep.CREATE_FEISHU_GROUP,
            status="ok",
        )
        cfg = replace(cfg, feishu_chat_id=created.chat_id, bootstrap_log=new_log)
        self._feishu.upsert_project_config(request.project, cfg)
        return cfg

    def finalize(self, request: BootstrapRequest) -> ProjectConfig:
        cfg = self._feishu.list_project_configs()[request.project]
        if cfg.bootstrap_status == "PROVISIONED":
            _logger.info(
                "bootstrap: skipping finalize (already PROVISIONED) project=%s",
                request.project,
            )
            return cfg
        if last_completed_step(cfg.bootstrap_log) < int(
            BootstrapStep.CREATE_FEISHU_GROUP
        ):
            raise BootstrapStepError(
                step=BootstrapStep.FINALIZE,
                message="earlier steps not complete",
            )
        new_log = append_log_entry(
            cfg.bootstrap_log, step=BootstrapStep.FINALIZE, status="ok"
        )
        cfg = replace(
            cfg,
            bootstrap_status="PROVISIONED",
            project_status="PROVISIONED",
            bootstrap_completed_at=datetime.now(timezone.utc).isoformat(),
            bootstrap_log=new_log,
        )
        self._feishu.upsert_project_config(request.project, cfg)
        return cfg

    def run(self, request: BootstrapRequest) -> BootstrapResult:
        self.validate(request)
        template_version, rendered_arch_md = render_template(
            request.category, project=request.project
        )
        self.upsert_config(request, template_version=template_version)
        self.create_repo_and_populate(
            request,
            template_version=template_version,
            rendered_architecture_md=rendered_arch_md,
        )
        self.create_architecture_doc(
            request, rendered_architecture_md=rendered_arch_md
        )
        self.create_feishu_group(request)
        final_cfg = self.finalize(request)
        return BootstrapResult(
            project=request.project,
            github_repo_url=final_cfg.github_repo_url,
            architecture_doc_id=final_cfg.architecture_doc_id,
            architecture_doc_url=final_cfg.architecture_doc_url,
            feishu_chat_id=final_cfg.feishu_chat_id,
            template_version=final_cfg.template_version,
        )
