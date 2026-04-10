from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import lark_oapi as lark
from lark_oapi.core.model import RequestOption
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

from .config import Settings
from .models import Requirement


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
        self.settings = settings
        self.client = (
            lark.Client.builder()
            .app_id(settings.feishu_app_id)
            .app_secret(settings.feishu_app_secret)
            .enable_set_token(True)
            .build()
        )

    def send_text(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> None:
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
        response = self.client.im.v1.message.create(request, option=self._request_option())
        self._ensure_success(response, "send text message")

    def create_project_group(self, project: str, owner_user_id: str, member_user_ids: list[str] | None = None) -> CreatedChat:
        member_user_ids = member_user_ids or []
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
        response = self.client.im.v1.chat.create(request, option=self._request_option())
        self._ensure_success(response, "create project group")
        body = response.data
        return CreatedChat(chat_id=body.chat_id, name=body.name or "")

    def create_requirement_record(self, requirement: Requirement) -> CreatedRecord | None:
        if not self.settings.feishu_bitable_app_token or not self.settings.feishu_bitable_table_id:
            return None
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
        response = self.client.bitable.v1.app_table_record.create(request, option=self._request_option())
        self._ensure_success(response, "create bitable record")
        return CreatedRecord(record_id=response.data.record.record_id)

    def update_requirement_record(self, requirement: Requirement) -> None:
        if not requirement.bitable_record_id:
            return
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
        response = self.client.bitable.v1.app_table_record.update(request, option=self._request_option())
        self._ensure_success(response, "update bitable record")

    def create_requirement_document(self, requirement: Requirement) -> CreatedDocument | None:
        if not self.settings.feishu_doc_folder_token:
            return None
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
        response = self.client.docx.v1.document.create(request, option=self._request_option())
        self._ensure_success(response, "create requirement document")
        document = response.data.document
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

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
            response = self.client.docx.v1.document_block.children.batch_delete(delete_request, option=self._request_option())
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
        response = self.client.docx.v1.document_block.children.create(create_request, option=self._request_option())
        self._ensure_success(response, "create document blocks")

    def _record_fields(self, requirement: Requirement) -> dict[str, object]:
        return {
            "REQ ID": requirement.req_id,
            "需求名称": requirement.name,
            "项目代号": requirement.project,
            "需求简述": requirement.summary,
            "状态": requirement.status.value,
            "当前阶段": requirement.current_phase,
            "当前轮次": requirement.current_round,
            "当前讨论字段": requirement.current_discussion_field,
            "当前Owner": requirement.current_owner,
            "当前接手角色": requirement.current_role_label,
            "已完成字段": ", ".join(requirement.completed_fields),
            "待补字段": ", ".join(requirement.pending_fields),
            "最近一次提问": requirement.latest_question,
            "最近一次review结论": requirement.latest_review_summary,
            "AI Ready": requirement.ai_ready,
            "Human Confirmed": requirement.human_confirmed,
            "需求文档链接": requirement.document_url,
        }

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
            response = self.client.docx.v1.document_block.children.get(request, option=self._request_option())
            self._ensure_success(response, "list document block children")
            data = response.data
            items.extend(data.items or [])
            if not data.has_more:
                return items
            page_token = data.page_token or ""

    def _build_requirement_blocks(self, requirement: Requirement) -> list[Block]:
        if requirement.document is None:
            return []

        blocks: list[Block] = [
            self._heading_block(self.BLOCK_TYPE_HEADING1, "需求概览"),
            self._text_block(requirement.summary or "待补充"),
        ]
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

    def _ensure_success(self, response, action: str) -> None:
        if not response.success():
            raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")

    def _request_option(self) -> RequestOption | None:
        if not self.settings.feishu_user_access_token:
            return None
        return RequestOption.builder().user_access_token(self.settings.feishu_user_access_token).build()
