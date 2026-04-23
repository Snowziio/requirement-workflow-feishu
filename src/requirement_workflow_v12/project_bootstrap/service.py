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

from ..architecture_templates import (
    available_categories,
    derive_pkg,
    parse_template_yaml,
    render_template,
)
from ..project_config import ProjectConfig
from .state import append_log_entry, last_completed_step
from .static_content import (
    PROJECT_README_MD,
    render_claude_md,
    render_design_index_md,
    render_design_pages_yaml,
    render_design_readme,
    render_environments_yaml,
    render_gitattributes,
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


def build_design_binding_card(
    *,
    project: str,
    github_repo_url: str,
    error_context: str | None = None,
) -> dict:
    """Build a Feishu interactive card prompting the user to bind Claude Design.

    error_context, when provided, is shown at the top of the card as a banner —
    used when this card is emitted after a design_start guard failure.
    """
    elements: list[dict] = []
    if error_context:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⚠️ **{error_context}**",
            },
        })
    elements.extend([
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"Bootstrap 已完成项目 **{project}** 的基建。\n\n"
                    f"**下一步**（首个 needs_ui 需求进入 design 阶段之前必须做）：\n"
                    f"1. 访问 https://claude.ai/design，登录后新建 Project\n"
                    f"2. 在 Project 中 **Import GitHub repo**：{github_repo_url}\n"
                    f"3. 搭建组织级 Design System（配色 / 字体 / 组件）\n"
                    f"4. 回到本卡片，粘贴 Claude Design Project URL\n"
                    f"（形如 `https://claude.ai/design/p/xxx`）\n"
                    f"5. 点「保存 URL」"
                ),
            },
        },
        {
            "tag": "input",
            "name": "claude_design_project_url",
            "placeholder": {
                "tag": "plain_text",
                "content": "https://claude.ai/design/p/xxx",
            },
        },
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "保存 URL"},
                    "type": "primary",
                    "value": {
                        "action": "bind_claude_design_project",
                        "project": project,
                    },
                }
            ],
        },
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "未绑定时，首个 needs_ui 需求进入 design 阶段会被阻断并重新推送此卡片。",
                }
            ],
        },
    ])
    return {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"完成 Claude Design 绑定：{project}",
            },
            "template": "orange" if error_context else "indigo",
        },
        "elements": elements,
    }


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

        pkg = derive_pkg(request.project)
        # Parse YAML to extract frontend subpath & tech_stack for this category
        try:
            parsed_yaml = parse_template_yaml(request.category)
        except Exception as exc:
            _logger.warning(
                "parse_template_yaml failed project=%s category=%s: %s; "
                "continuing without frontend fields",
                request.project, request.category, exc,
            )
            parsed_yaml = {}

        frontend_block = parsed_yaml.get("frontend")  # may be None
        frontend_subpath = ""
        frontend_tech_stack: dict = {}
        if isinstance(frontend_block, dict):
            raw_subpath = frontend_block.get("subpath", "")
            frontend_subpath = raw_subpath.replace("{pkg}", pkg)
            frontend_tech_stack = frontend_block.get("tech_stack", {}) or {}

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
            # design-phase static files
            "design/README.md": render_design_readme(),
            "design/PAGES.yaml": render_design_pages_yaml(),
            "design/INDEX.md": render_design_index_md(),
            "design/system/.gitkeep": "",
            "design/archive/.gitkeep": "",
            ".gitattributes": render_gitattributes(),
        }
        if frontend_subpath:
            populate_files[f"{frontend_subpath}/.gitkeep"] = ""
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
            frontend_subpath=frontend_subpath,
            frontend_tech_stack=frontend_tech_stack,
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

    def _emit_design_binding_reminder_card(
        self, *, project: str, cfg: "ProjectConfig",
    ) -> None:
        """Push the Claude Design binding reminder card to the project's creation group.

        Best-effort: returns silently (warns only) if feishu_chat_id is empty
        or send fails, so FINALIZE never blocks on this.
        """
        if not cfg.feishu_chat_id:
            _logger.info(
                "skip design binding reminder card: no feishu_chat_id project=%s",
                project,
            )
            return
        try:
            card = build_design_binding_card(
                project=project,
                github_repo_url=cfg.github_repo_url,
            )
            self._feishu.send_card(cfg.feishu_chat_id, card)
            _logger.info("sent design binding reminder card project=%s", project)
        except Exception as exc:
            _logger.warning(
                "design binding reminder card send failed project=%s: %s",
                project, exc,
            )

    def run(self, request: BootstrapRequest) -> BootstrapResult:
        self.validate(request)
        template_version, rendered_arch_md = render_template(
            request.category,
            project=request.project,
            seed=request.architecture_seed or None,
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
