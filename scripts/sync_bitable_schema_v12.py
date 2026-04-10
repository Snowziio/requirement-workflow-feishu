from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableField,
    AppTableFieldBuilder,
    CreateAppTableFieldRequest,
    ListAppTableFieldRequest,
    UpdateAppTableFieldRequest,
)
from lark_oapi.core.model import RequestOption


FIELD_TYPE_TEXT = 1
FIELD_TYPE_NUMBER = 2
FIELD_TYPE_CHECKBOX = 7


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: int


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("REQ ID", FIELD_TYPE_TEXT),
    FieldSpec("需求名称", FIELD_TYPE_TEXT),
    FieldSpec("项目代号", FIELD_TYPE_TEXT),
    FieldSpec("需求简述", FIELD_TYPE_TEXT),
    FieldSpec("状态", FIELD_TYPE_TEXT),
    FieldSpec("当前阶段", FIELD_TYPE_TEXT),
    FieldSpec("当前轮次", FIELD_TYPE_NUMBER),
    FieldSpec("当前讨论字段", FIELD_TYPE_TEXT),
    FieldSpec("当前Owner", FIELD_TYPE_TEXT),
    FieldSpec("当前接手角色", FIELD_TYPE_TEXT),
    FieldSpec("已完成字段", FIELD_TYPE_TEXT),
    FieldSpec("待补字段", FIELD_TYPE_TEXT),
    FieldSpec("最近一次提问", FIELD_TYPE_TEXT),
    FieldSpec("最近一次review结论", FIELD_TYPE_TEXT),
    FieldSpec("AI Ready", FIELD_TYPE_CHECKBOX),
    FieldSpec("Human Confirmed", FIELD_TYPE_CHECKBOX),
    FieldSpec("需求文档链接", FIELD_TYPE_TEXT),
]


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def build_client() -> lark.Client:
    app_id = required_env("FEISHU_APP_ID")
    app_secret = required_env("FEISHU_APP_SECRET")
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .enable_set_token(True)
        .build()
    )


def list_fields(client: lark.Client, app_token: str, table_id: str) -> dict[str, object]:
    page_token = ""
    fields_by_name: dict[str, object] = {}
    while True:
        request = (
            ListAppTableFieldRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(200)
            .page_token(page_token)
            .build()
        )
        response = client.bitable.v1.app_table_field.list(request, option=request_option())
        ensure_success(response, "list bitable fields")
        data = response.data
        for item in data.items or []:
            fields_by_name[item.field_name] = item
        if not data.has_more:
            return fields_by_name
        page_token = data.page_token or ""


def build_field_payload(spec: FieldSpec, *, field_id: str = "") -> AppTableField:
    builder = AppTableFieldBuilder().field_name(spec.name).type(spec.field_type)
    if field_id:
        builder = builder.field_id(field_id)
    return builder.build()


def create_field(client: lark.Client, app_token: str, table_id: str, spec: FieldSpec) -> None:
    request = (
        CreateAppTableFieldRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .client_token(str(uuid.uuid4()))
        .request_body(build_field_payload(spec))
        .build()
    )
    response = client.bitable.v1.app_table_field.create(request, option=request_option())
    ensure_success(response, f"create bitable field {spec.name}")
    print(f"[created] {spec.name}")


def update_field(client: lark.Client, app_token: str, table_id: str, field_id: str, spec: FieldSpec) -> None:
    request = (
        UpdateAppTableFieldRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .field_id(field_id)
        .request_body(build_field_payload(spec, field_id=field_id))
        .build()
    )
    response = client.bitable.v1.app_table_field.update(request, option=request_option())
    ensure_success(response, f"update bitable field {spec.name}")
    print(f"[updated] {spec.name}")


def ensure_success(response, action: str) -> None:
    if not response.success():
        raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")


def request_option() -> RequestOption | None:
    token = os.environ.get("FEISHU_USER_ACCESS_TOKEN", "").strip()
    if not token:
        return None
    return RequestOption.builder().user_access_token(token).build()


def main() -> int:
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    client = build_client()

    current_fields = list_fields(client, app_token, table_id)
    print(f"[info] current field count: {len(current_fields)}")

    for spec in FIELD_SPECS:
        existing = current_fields.get(spec.name)
        if existing is None:
            create_field(client, app_token, table_id, spec)
            continue

        if existing.type != spec.field_type:
            update_field(client, app_token, table_id, existing.field_id, spec)
            continue

        print(f"[skip] {spec.name}")

    print("[done] Bitable schema synced to v1.2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
