from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - optional during tests before runtime deps are installed
    import lark_oapi as lark
    from lark_oapi.api.bitable.v1 import AppTableRecord, CreateAppTableRecordRequest, UpdateAppTableRecordRequest
    from lark_oapi.api.docx.v1 import (
        BatchDeleteDocumentBlockChildrenRequest,
        BatchDeleteDocumentBlockChildrenRequestBody,
        Block,
        CreateDocumentBlockChildrenRequest,
        CreateDocumentBlockChildrenRequestBody,
        CreateDocumentRequest,
        CreateDocumentRequestBody,
        GetDocumentBlockChildrenRequest,
        Text,
        TextElement,
        TextRun,
    )
    from lark_oapi.api.im.v1 import CreateChatRequest, CreateChatRequestBody, CreateMessageRequest, CreateMessageRequestBody
except ImportError:  # pragma: no cover - optional during tests before runtime deps are installed
    lark = None
    AppTableRecord = Any
    CreateAppTableRecordRequest = Any
    UpdateAppTableRecordRequest = Any
    BatchDeleteDocumentBlockChildrenRequest = Any
    BatchDeleteDocumentBlockChildrenRequestBody = Any
    Block = Any
    CreateDocumentBlockChildrenRequest = Any
    CreateDocumentBlockChildrenRequestBody = Any
    CreateDocumentRequest = Any
    CreateDocumentRequestBody = Any
    GetDocumentBlockChildrenRequest = Any
    Text = Any
    TextElement = Any
    TextRun = Any
    CreateChatRequest = Any
    CreateChatRequestBody = Any
    CreateMessageRequest = Any
    CreateMessageRequestBody = Any

from .config import Settings
from .bitable_schema import build_coordinator_record_fields
from .models import Requirement


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

    def bitable_url(self) -> str:
        if not self.settings.feishu_bitable_app_token:
            return ""
        url = f"{self.settings.feishu_base_url}/base/{self.settings.feishu_bitable_app_token}"
        if self.settings.feishu_bitable_table_id:
            url += f"?table={self.settings.feishu_bitable_table_id}"
        return url

    def sync_requirement_document(self, requirement: Requirement) -> None:
        if not requirement.document_id or requirement.document is None:
            return

        root_block_id = requirement.document_id
        existing_children = self._list_block_children(requirement.document_id, root_block_id)
        if existing_children:
            delete_request = (
                BatchDeleteDocumentBlockChildrenRequest.builder()
                .document_id(requirement.document_id)
                .block_id(root_block_id)
                .request_body(
                    BatchDeleteDocumentBlockChildrenRequestBody.builder()
                    .start_index(0)
                    .end_index(len(existing_children))
                    .build()
                )
                .build()
            )
            response = self.client.docx.v1.document_block.children.batch_delete(delete_request)
            self._ensure_success(response, "delete existing document blocks")

        blocks = self._build_requirement_blocks(requirement)
        if not blocks:
            return

        create_request = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(requirement.document_id)
            .block_id(root_block_id)
            .client_token(str(uuid.uuid4()))
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .index(0)
                .children(blocks)
                .build()
            )
            .build()
        )
        response = self.client.docx.v1.document_block.children.create(create_request)
        self._ensure_success(response, "create document blocks")

    def _record_fields(self, requirement: Requirement) -> dict[str, object]:
        return build_coordinator_record_fields(requirement)

    def _list_block_children(self, document_id: str, block_id: str) -> list[Block]:
        items: list[Block] = []
        page_token = ""
        while True:
            request = (
                GetDocumentBlockChildrenRequest.builder()
                .document_id(document_id)
                .block_id(block_id)
                .page_size(500)
                .page_token(page_token)
                .build()
            )
            response = self.client.docx.v1.document_block.children.get(request)
            self._ensure_success(response, "list document block children")
            data = response.data
            items.extend(data.items or [])
            if not data.has_more:
                return items
            page_token = data.page_token or ""

    def _build_requirement_blocks(self, requirement: Requirement) -> list[Block]:
        if requirement.document is None:
            return []

        blocks: list[Block] = []
        for section, content in requirement.document.sections.items():
            blocks.append(self._heading_block(self.BLOCK_TYPE_HEADING2, section))
            blocks.append(self._text_block(content or "待补充"))
        return blocks

    def _heading_block(self, block_type: int, content: str) -> Block:
        text = self._rich_text(content)
        block = Block.builder().block_type(block_type)
        if block_type == self.BLOCK_TYPE_HEADING1:
            return block.heading1(text).build()
        return block.heading2(text).build()

    def _text_block(self, content: str) -> Block:
        return Block.builder().block_type(self.BLOCK_TYPE_TEXT).text(self._rich_text(content)).build()

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

    def _ensure_success(self, response, action: str) -> None:
        if not response.success():
            raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")
