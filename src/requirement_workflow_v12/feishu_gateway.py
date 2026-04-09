from __future__ import annotations

import json
from dataclasses import dataclass

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import AppTableRecord, CreateAppTableRecordRequest, UpdateAppTableRecordRequest
from lark_oapi.api.docx.v1 import CreateDocumentRequest, CreateDocumentRequestBody
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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = lark.Client.builder().app_id(settings.feishu_app_id).app_secret(settings.feishu_app_secret).build()

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
        response = self.client.im.v1.message.create(request)
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
        response = self.client.im.v1.chat.create(request)
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
        response = self.client.bitable.v1.app_table_record.create(request)
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
        response = self.client.bitable.v1.app_table_record.update(request)
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
        response = self.client.docx.v1.document.create(request)
        self._ensure_success(response, "create requirement document")
        document = response.data.document
        return CreatedDocument(
            document_id=document.document_id,
            document_url=f"{self.settings.feishu_base_url}/docx/{document.document_id}",
        )

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
            "AI Ready": requirement.ai_ready,
            "Human Confirmed": requirement.human_confirmed,
            "需求文档链接": requirement.document_url,
        }

    def _ensure_success(self, response, action: str) -> None:
        if not response.success():
            raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")
