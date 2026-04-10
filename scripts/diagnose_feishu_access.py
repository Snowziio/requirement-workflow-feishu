from __future__ import annotations

import os
import sys
import uuid

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableRecord,
    CreateAppTableRecordRequest,
    ListAppTableRequest,
)
from lark_oapi.api.docx.v1 import CreateDocumentRequest, CreateDocumentRequestBody


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


def build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(required_env("FEISHU_APP_ID"))
        .app_secret(required_env("FEISHU_APP_SECRET"))
        .build()
    )


def dump_response(prefix: str, response) -> None:
    print(f"{prefix}: success={response.success()} code={response.code} msg={response.msg}")


def try_list_tables(client: lark.Client, app_token: str) -> None:
    request = ListAppTableRequest.builder().app_token(app_token).page_size(100).build()
    response = client.bitable.v1.app_table.list(request)
    dump_response("[bitable:list_tables]", response)
    if response.success():
        names = [f"{item.table_id}:{item.name}" for item in (response.data.items or [])]
        print(f"[bitable:list_tables] tables={names}")


def try_create_record(client: lark.Client, app_token: str, table_id: str, with_user_id_type: bool) -> None:
    payload = (
        CreateAppTableRecordRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .request_body(
            AppTableRecord.builder()
            .fields(
                {
                    "REQ ID": f"DIAG-{uuid.uuid4().hex[:8]}",
                    "需求名称": "权限诊断记录",
                    "项目代号": "DIAG",
                    "需求简述": "用于诊断飞书 Bitable 写入权限",
                    "状态": "DIAG",
                }
            )
            .build()
        )
    )
    if with_user_id_type:
        payload = payload.user_id_type(optional_env("FEISHU_USER_ID_TYPE", "open_id"))
    request = payload.build()
    response = client.bitable.v1.app_table_record.create(request)
    suffix = "with_user_id_type" if with_user_id_type else "without_user_id_type"
    dump_response(f"[bitable:create_record:{suffix}]", response)
    if response.success():
        print(f"[bitable:create_record:{suffix}] record_id={response.data.record.record_id}")


def try_create_doc(client: lark.Client, folder_token: str) -> None:
    request = (
        CreateDocumentRequest.builder()
        .request_body(
            CreateDocumentRequestBody.builder()
            .folder_token(folder_token)
            .title(f"Requirement Workflow Feishu Access Diagnose {uuid.uuid4().hex[:6]}")
            .build()
        )
        .build()
    )
    response = client.docx.v1.document.create(request)
    dump_response("[doc:create]", response)
    if response.success():
        print(f"[doc:create] document_id={response.data.document.document_id}")


def main() -> int:
    client = build_client()
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    folder_token = required_env("FEISHU_DOC_FOLDER_TOKEN")

    try_list_tables(client, app_token)
    try_create_record(client, app_token, table_id, with_user_id_type=True)
    try_create_record(client, app_token, table_id, with_user_id_type=False)
    try_create_doc(client, folder_token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        raise
