from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableCreateHeader,
    CreateAppRequest,
    CreateAppTableRequest,
    CreateAppTableRequestBody,
    ReqApp,
    ReqTable,
)


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


def optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


def build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(required_env("FEISHU_APP_ID"))
        .app_secret(required_env("FEISHU_APP_SECRET"))
        .build()
    )


def build_headers() -> list[AppTableCreateHeader]:
    return [
        AppTableCreateHeader.builder().field_name(spec.name).type(spec.field_type).build()
        for spec in FIELD_SPECS
    ]


def ensure_success(response, action: str) -> None:
    if not response.success():
        raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def main() -> int:
    client = build_client()
    app_name = optional_env("FEISHU_BITABLE_APP_NAME", "Requirement Workflow v1.2")
    table_name = optional_env("FEISHU_BITABLE_TABLE_NAME", "Requirements")
    folder_token = optional_env("FEISHU_BITABLE_FOLDER_TOKEN", optional_env("FEISHU_DOC_FOLDER_TOKEN"))
    time_zone = optional_env("FEISHU_TIME_ZONE", "Asia/Shanghai")

    req_app_builder = ReqApp.builder().name(app_name).time_zone(time_zone)
    if folder_token:
        req_app_builder = req_app_builder.folder_token(folder_token)

    create_app_request = (
        CreateAppRequest.builder()
        .request_body(req_app_builder.build())
        .build()
    )
    create_app_response = client.bitable.v1.app.create(create_app_request)
    ensure_success(create_app_response, "create bitable app")
    app = create_app_response.data.app

    create_table_request = (
        CreateAppTableRequest.builder()
        .app_token(app.app_token)
        .request_body(
            CreateAppTableRequestBody.builder()
            .table(
                ReqTable.builder()
                .name(table_name)
                .default_view_name("All Requirements")
                .fields(build_headers())
                .build()
            )
            .build()
        )
        .build()
    )
    create_table_response = client.bitable.v1.app_table.create(create_table_request)
    ensure_success(create_table_response, "create bitable table")

    table_id = create_table_response.data.table_id
    print(f"[created] app_token={app.app_token}")
    print(f"[created] table_id={table_id}")
    print(f"[created] app_url={app.url}")
    write_output("app_token", app.app_token)
    write_output("table_id", table_id)
    write_output("app_url", app.url or "")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
