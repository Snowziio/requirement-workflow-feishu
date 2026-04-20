from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional during tests before runtime deps are installed
    import lark_oapi as lark
    from lark_oapi.api.bitable.v1 import (
        AppTableRecord,
        CreateAppTableRecordRequest,
        ListAppTableRecordRequest,
        UpdateAppTableRecordRequest,
    )
    from lark_oapi.api.docx.v1 import (
        Block,
        CreateDocumentBlockChildrenRequest,
        CreateDocumentBlockChildrenRequestBody,
        CreateDocumentRequest,
        CreateDocumentRequestBody,
        Text,
        TextElement,
        TextRun,
    )
    from lark_oapi.api.im.v1 import CreateChatRequest, CreateChatRequestBody, CreateMessageRequest, CreateMessageRequestBody
except ImportError:  # pragma: no cover - optional during tests before runtime deps are installed
    lark = None
    AppTableRecord = Any
    CreateAppTableRecordRequest = Any
    ListAppTableRecordRequest = Any
    UpdateAppTableRecordRequest = Any
    Block = Any
    CreateDocumentBlockChildrenRequest = Any
    CreateDocumentBlockChildrenRequestBody = Any
    CreateDocumentRequest = Any
    CreateDocumentRequestBody = Any
    Text = Any
    TextElement = Any
    TextRun = Any
    CreateChatRequest = Any
    CreateChatRequestBody = Any
    CreateMessageRequest = Any
    CreateMessageRequestBody = Any

from .config import Settings
from .bitable_schema import (
    PROJECT_CONFIG_FIELD_ARCH_DOC_ID,
    PROJECT_CONFIG_FIELD_ARCH_DOC_URL,
    PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT,
    PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON,
    PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS,
    PROJECT_CONFIG_FIELD_CATEGORY,
    PROJECT_CONFIG_FIELD_DESIGN_SYSTEM_DOC_ID,
    PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID,
    PROJECT_CONFIG_FIELD_GITHUB_OWNER_USERNAME,
    PROJECT_CONFIG_FIELD_GITHUB_REPO_URL,
    PROJECT_CONFIG_FIELD_PROJECT,
    PROJECT_CONFIG_FIELD_PROJECT_STATUS,
    PROJECT_CONFIG_FIELD_TECH_STACK_JSON,
    PROJECT_CONFIG_FIELD_TEMPLATE_VERSION,
    build_coordinator_record_fields,
)
from .models import Requirement
from .project_config import ProjectConfig


LOGGER = logging.getLogger(__name__)


@dataclass
class CreatedChat:
    chat_id: str
    name: str


@dataclass
class CreatedRecord:
    record_id: str


@dataclass
class CreatedDocument:
    document_id: str
    document_url: str


class FeishuGateway:
    BLOCK_TYPE_TEXT = 2
    BLOCK_TYPE_HEADING1 = 3
    BLOCK_TYPE_HEADING2 = 4

    def __init__(self, settings: Settings) -> None:
        if lark is None:
            raise RuntimeError("lark_oapi is not installed. Install runtime dependencies first.")
        self.settings = settings
        self.client = lark.Client.builder().app_id(settings.feishu_app_id).app_secret(settings.feishu_app_secret).build()

    def send_text(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> None:
        LOGGER.info("Feishu send_text receive_id=%s receive_id_type=%s text_preview=%s", receive_id, receive_id_type, text[:120])
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        self._ensure_success(response, "send text message")

    def send_card(self, receive_id: str, card: dict[str, object], receive_id_type: str = "chat_id") -> None:
        card_title = ""
        header = card.get("header")
        if isinstance(header, dict):
            title = header.get("title")
            if isinstance(title, dict):
                card_title = str(title.get("content", ""))
        LOGGER.info(
            "Feishu send_card receive_id=%s receive_id_type=%s card_title=%s",
            receive_id,
            receive_id_type,
            card_title,
        )
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        self._ensure_success(response, "send card message")

    def create_project_group(self, project: str, owner_user_id: str, member_user_ids: list[str] | None = None) -> CreatedChat:
        member_user_ids = member_user_ids or []
        LOGGER.info("Feishu create_project_group project=%s owner_user_id=%s member_count=%s", project, owner_user_id, len(member_user_ids))
        request = (
            CreateChatRequest.builder()
            .user_id_type(self.settings.feishu_user_id_type)
            .request_body(
                CreateChatRequestBody.builder()
                .name(self.settings.project_group_name_template.format(project=project))
                .description(f"{project} 项目的需求协作群")
                .owner_id(owner_user_id)
                .user_id_list(member_user_ids)
                .group_message_type("chat")
                .chat_mode("group")
                .chat_type("private")
                .membership_approval("no_approval_required")
                .build()
            )
            .build()
        )
        response = self.client.im.v1.chat.create(request)
        self._ensure_success(response, "create project group")
        body = response.data
        LOGGER.info("Feishu created project group project=%s chat_id=%s", project, body.chat_id)
        return CreatedChat(chat_id=body.chat_id, name=body.name or "")

    def create_requirement_record(self, requirement: Requirement) -> CreatedRecord | None:
        if not self.settings.feishu_bitable_app_token or not self.settings.feishu_bitable_table_id:
            return None
        LOGGER.info("Feishu create_requirement_record req_id=%s", requirement.req_id)
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(self.settings.feishu_bitable_app_token)
            .table_id(self.settings.feishu_bitable_table_id)
            .user_id_type(self.settings.feishu_user_id_type)
            .request_body(
                AppTableRecord.builder()
                .fields(self._record_fields(requirement))
                .build()
            )
            .build()
        )
        response = self.client.bitable.v1.app_table_record.create(request)
        self._ensure_success(response, "create bitable record")
        LOGGER.info("Feishu created bitable record req_id=%s record_id=%s", requirement.req_id, response.data.record.record_id)
        return CreatedRecord(record_id=response.data.record.record_id)

    def update_requirement_record(self, requirement: Requirement) -> None:
        if not requirement.bitable_record_id:
            return
        LOGGER.info(
            "Feishu update_requirement_record req_id=%s record_id=%s status=%s phase=%s owner=%s",
            requirement.req_id,
            requirement.bitable_record_id,
            requirement.status.value,
            requirement.current_phase,
            requirement.current_owner,
        )
        request = (
            UpdateAppTableRecordRequest.builder()
            .app_token(self.settings.feishu_bitable_app_token)
            .table_id(self.settings.feishu_bitable_table_id)
            .record_id(requirement.bitable_record_id)
            .user_id_type(self.settings.feishu_user_id_type)
            .request_body(
                AppTableRecord.builder()
                .fields(self._record_fields(requirement))
                .build()
            )
            .build()
        )
        response = self.client.bitable.v1.app_table_record.update(request)
        self._ensure_success(response, "update bitable record")
        LOGGER.info("Feishu updated bitable record req_id=%s record_id=%s", requirement.req_id, requirement.bitable_record_id)

    def create_requirement_document(self, requirement: Requirement) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
        LOGGER.info("Feishu create_requirement_document req_id=%s title=%s", requirement.req_id, requirement.name)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(self.settings.feishu_doc_folder_token)
                .title(f"{requirement.req_id} {requirement.name}")
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create requirement document")
        document = response.data.document
        LOGGER.info("Feishu created requirement document req_id=%s document_id=%s", requirement.req_id, document.document_id)
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

    def create_spec_document(self, requirement: Requirement) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
        title = f"{requirement.req_id} {requirement.name} — 技术规格"
        LOGGER.info("Feishu create_spec_document req_id=%s title=%s", requirement.req_id, title)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(self.settings.feishu_doc_folder_token)
                .title(title)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create spec document")
        document = response.data.document
        LOGGER.info(
            "Feishu created spec document req_id=%s document_id=%s",
            requirement.req_id,
            document.document_id,
        )
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

    def create_architecture_document(self, project: str) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
        title = f"{project} 架构快照 ARCHITECTURE"
        LOGGER.info("Feishu create_architecture_document project=%s title=%s", project, title)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .folder_token(self.settings.feishu_doc_folder_token)
                .title(title)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create architecture document")
        document = response.data.document
        LOGGER.info(
            "Feishu created architecture document project=%s document_id=%s",
            project,
            document.document_id,
        )
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

    def write_document_text(self, document_id: str, content: str) -> None:
        """Append the given text as a single code-like block to the document."""
        LOGGER.info(
            "Feishu write_document_text document_id=%s content_bytes=%d",
            document_id,
            len(content.encode("utf-8")),
        )
        block = (
            Block.builder()
            .block_type(self.BLOCK_TYPE_TEXT)
            .text(self._rich_text(content))
            .build()
        )
        request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(document_id)
            .block_id(document_id)
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .children([block])
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document_block_children.create(request)
        self._ensure_success(response, "write document text")

    def fetch_document_revision(self, document_id: str) -> str:
        """Return a revision marker for the document.

        Uses the raw_content endpoint's revision_id when available; otherwise
        falls back to a wall-clock timestamp marker so the Coordinator always
        has something to persist for auditing.
        """
        import time as _time
        try:
            response = self.client.docx.v1.document.raw_content(document_id)
            self._ensure_success(response, "fetch document revision")
            revision_id = getattr(response.data, "revision_id", None)
            if revision_id is not None:
                return f"rev-{revision_id}"
        except Exception as exc:  # pragma: no cover - SDK variance
            LOGGER.warning(
                "Failed to query revision for document_id=%s, falling back to timestamp: %s",
                document_id,
                exc,
            )
        return f"ts-{int(_time.time() * 1000)}"

    def bitable_url(self) -> str:
        if not self.settings.feishu_bitable_app_token:
            return ""
        url = f"{self.settings.feishu_base_url}/base/{self.settings.feishu_bitable_app_token}"
        if self.settings.feishu_bitable_table_id:
            url += f"?table={self.settings.feishu_bitable_table_id}"
        return url

    def _record_fields(self, requirement: Requirement) -> dict[str, object]:
        return build_coordinator_record_fields(requirement)

    def _rich_text(self, content: str) -> Text:
        return Text.builder().elements([self._text_element(content)]).build()

    def _text_element(self, content: str) -> TextElement:
        return TextElement.builder().text_run(TextRun.builder().content(content).build()).build()

    def create_design_system_document(self, project: str) -> str:
        """Create a Feishu doc for the project design system. Returns doc_id."""
        title = f"{project} 设计系统"
        LOGGER.info("Creating design system document project=%s title=%s", project, title)
        request = (
            CreateDocumentRequest.builder()
            .request_body(
                CreateDocumentRequestBody.builder()
                .title(title)
                .folder_token(self.settings.feishu_doc_folder_token)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create design system document")
        doc_id = response.data.document.document_id
        LOGGER.info("Created design system document doc_id=%s project=%s", doc_id, project)
        return doc_id

    def append_design_decision_to_doc(self, doc_id: str, req_id: str, content: str) -> None:
        """Append a design decision block (text) to the design system document."""
        LOGGER.info("Appending design decision doc_id=%s req_id=%s", doc_id, req_id)
        text_content = f"[{req_id}] {content}"
        block = (
            Block.builder()
            .block_type(self.BLOCK_TYPE_TEXT)
            .text(self._rich_text(text_content))
            .build()
        )
        request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(doc_id)
            .block_id(doc_id)
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .children([block])
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document_block_children.create(request)
        if not response.success():
            LOGGER.warning("Failed to append design decision: %s", response.msg)

    # ── Project configs (Bitable-backed single source of truth) ───────────

    def _project_configs_table_configured(self) -> bool:
        return bool(
            self.settings.feishu_bitable_app_token
            and self.settings.feishu_bitable_project_configs_table_id
        )

    def _project_config_to_fields(self, cfg: ProjectConfig, project: str) -> dict[str, object]:
        return {
            PROJECT_CONFIG_FIELD_PROJECT: project,
            PROJECT_CONFIG_FIELD_CATEGORY: cfg.category,
            PROJECT_CONFIG_FIELD_TEMPLATE_VERSION: cfg.template_version,
            PROJECT_CONFIG_FIELD_ARCH_DOC_ID: cfg.architecture_doc_id,
            PROJECT_CONFIG_FIELD_ARCH_DOC_URL: cfg.architecture_doc_url,
            PROJECT_CONFIG_FIELD_TECH_STACK_JSON: json.dumps(
                cfg.tech_stack, ensure_ascii=False
            ),
            PROJECT_CONFIG_FIELD_DESIGN_SYSTEM_DOC_ID: cfg.design_system_doc_id or "",
            PROJECT_CONFIG_FIELD_GITHUB_REPO_URL: cfg.github_repo_url,
            PROJECT_CONFIG_FIELD_GITHUB_OWNER_USERNAME: cfg.github_owner_username,
            PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS: cfg.bootstrap_status,
            PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON: json.dumps(
                cfg.bootstrap_log, ensure_ascii=False
            ),
            PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT: cfg.bootstrap_completed_at or "",
            PROJECT_CONFIG_FIELD_PROJECT_STATUS: cfg.project_status,
            PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID: cfg.feishu_chat_id,
        }

    @staticmethod
    def _extract_field_text(raw: object) -> str:
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        if raw is None:
            return ""
        return str(raw)

    def list_project_configs(self) -> dict[str, ProjectConfig]:
        """Load all ProjectConfig rows from the Bitable project configs table.

        Returns empty dict when the table is not configured, so boot can proceed
        on first-ever start before the one-shot init workflow has run.
        """
        if not self._project_configs_table_configured():
            LOGGER.warning(
                "Bitable project configs table not configured; skipping load "
                "(FEISHU_BITABLE_PROJECT_CONFIGS_TABLE_ID missing)"
            )
            return {}

        configs: dict[str, ProjectConfig] = {}
        page_token = ""
        while True:
            builder = (
                ListAppTableRecordRequest.builder()
                .app_token(self.settings.feishu_bitable_app_token)
                .table_id(self.settings.feishu_bitable_project_configs_table_id)
                .page_size(100)
            )
            if page_token:
                builder = builder.page_token(page_token)
            response = self.client.bitable.v1.app_table_record.list(builder.build())
            self._ensure_success(response, "list project_configs records")
            data = response.data
            for item in data.items or []:
                fields = item.fields or {}
                project = self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_PROJECT))
                if not project:
                    LOGGER.warning(
                        "Skipping project_configs row without project name record_id=%s",
                        item.record_id,
                    )
                    continue
                tech_stack_raw = self._extract_field_text(
                    fields.get(PROJECT_CONFIG_FIELD_TECH_STACK_JSON)
                )
                try:
                    tech_stack = json.loads(tech_stack_raw) if tech_stack_raw else {}
                    if not isinstance(tech_stack, dict):
                        tech_stack = {}
                except json.JSONDecodeError:
                    LOGGER.warning(
                        "Invalid tech_stack JSON for project=%s record_id=%s; resetting to empty dict",
                        project,
                        item.record_id,
                    )
                    tech_stack = {}
                design_system_doc_id = self._extract_field_text(
                    fields.get(PROJECT_CONFIG_FIELD_DESIGN_SYSTEM_DOC_ID)
                ) or None
                bootstrap_log_raw = self._extract_field_text(
                    fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_LOG_JSON)
                )
                try:
                    bootstrap_log = json.loads(bootstrap_log_raw) if bootstrap_log_raw else []
                    if not isinstance(bootstrap_log, list):
                        bootstrap_log = []
                except json.JSONDecodeError:
                    LOGGER.warning(
                        "Invalid bootstrap_log JSON for project=%s record_id=%s; resetting to empty list",
                        project,
                        item.record_id,
                    )
                    bootstrap_log = []
                configs[project] = ProjectConfig(
                    category=self._extract_field_text(fields.get(PROJECT_CONFIG_FIELD_CATEGORY)),
                    template_version=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_TEMPLATE_VERSION)
                    ),
                    architecture_doc_id=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_ARCH_DOC_ID)
                    ),
                    architecture_doc_url=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_ARCH_DOC_URL)
                    ),
                    tech_stack=tech_stack,
                    design_system_doc_id=design_system_doc_id,
                    github_repo_url=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_GITHUB_REPO_URL)
                    ),
                    github_owner_username=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_GITHUB_OWNER_USERNAME)
                    ),
                    bitable_record_id=item.record_id or "",
                    bootstrap_status=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_STATUS)
                    ) or "UNBOOTSTRAPPED",
                    bootstrap_log=bootstrap_log,
                    bootstrap_completed_at=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_BOOTSTRAP_COMPLETED_AT)
                    ) or None,
                    project_status=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_PROJECT_STATUS)
                    ) or "UNBOOTSTRAPPED",
                    feishu_chat_id=self._extract_field_text(
                        fields.get(PROJECT_CONFIG_FIELD_FEISHU_CHAT_ID)
                    ),
                )
            if not data.has_more:
                break
            page_token = data.page_token or ""
        LOGGER.info("Loaded %d project_configs rows from Bitable", len(configs))
        return configs

    def upsert_project_config(self, project: str, cfg: ProjectConfig) -> ProjectConfig:
        """Create or update the row for `project` and return cfg with record_id set."""
        if not self._project_configs_table_configured():
            LOGGER.warning(
                "Bitable project configs table not configured; upsert for project=%s is a no-op",
                project,
            )
            return cfg
        fields = self._project_config_to_fields(cfg, project)
        if cfg.bitable_record_id:
            request = (
                UpdateAppTableRecordRequest.builder()
                .app_token(self.settings.feishu_bitable_app_token)
                .table_id(self.settings.feishu_bitable_project_configs_table_id)
                .record_id(cfg.bitable_record_id)
                .request_body(AppTableRecord.builder().fields(fields).build())
                .build()
            )
            response = self.client.bitable.v1.app_table_record.update(request)
            self._ensure_success(response, "update project_configs record")
            LOGGER.info(
                "Updated project_configs record project=%s record_id=%s",
                project,
                cfg.bitable_record_id,
            )
            return cfg
        request = (
            CreateAppTableRecordRequest.builder()
            .app_token(self.settings.feishu_bitable_app_token)
            .table_id(self.settings.feishu_bitable_project_configs_table_id)
            .request_body(AppTableRecord.builder().fields(fields).build())
            .build()
        )
        response = self.client.bitable.v1.app_table_record.create(request)
        self._ensure_success(response, "create project_configs record")
        record_id = response.data.record.record_id
        LOGGER.info(
            "Created project_configs record project=%s record_id=%s", project, record_id
        )
        cfg.bitable_record_id = record_id
        return cfg

    def _ensure_success(self, response, action: str) -> None:
        if not response.success():
            raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")
