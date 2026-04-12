from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableCreateHeader,
    CreateAppRequest,
    CreateAppTableRequest,
    CreateAppTableRequestBody,
    ReqApp,
    ReqTable,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from requirement_workflow_v12.bitable_schema import coordinator_managed_field_specs


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
        AppTableCreateHeader.builder().field_name(spec.name).type(spec.bitable_type).build()
        for spec in coordinator_managed_field_specs()
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


def create_table(client: lark.Client, app_token: str, table_name: str) -> str:
    create_table_request = (
        CreateAppTableRequest.builder()
        .app_token(app_token)
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
    return create_table_response.data.table_id


def create_bitable_app(
    client: lark.Client,
    app_name: str,
    time_zone: str,
    folder_token: str,
) -> tuple[str, Optional[str]]:
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
    return app.app_token, app.url


def main() -> int:
    client = build_client()
    existing_app_token = optional_env("FEISHU_BITABLE_APP_TOKEN")
    app_name = optional_env("FEISHU_BITABLE_APP_NAME", "Requirement Workflow v1.2")
    table_name = optional_env("FEISHU_BITABLE_TABLE_NAME", "Requirements")
    folder_token = optional_env("FEISHU_BITABLE_FOLDER_TOKEN", optional_env("FEISHU_DOC_FOLDER_TOKEN"))
    time_zone = optional_env("FEISHU_TIME_ZONE", "Asia/Shanghai")

    app_token = existing_app_token
    app_url: Optional[str] = None
    table_id: Optional[str] = None

    if existing_app_token:
        try:
            table_id = create_table(client, existing_app_token, table_name)
            print("[info] created table in existing bitable app")
        except Exception as exc:
            print(f"[warn] existing bitable app rejected table creation: {exc}")

    if not table_id:
        try:
            app_token, app_url = create_bitable_app(client, app_name, time_zone, folder_token)
        except Exception as exc:
            if folder_token and "DriveNodePermNotAllow" in str(exc):
                print("[warn] target folder rejected new bitable app; retrying without folder token")
                app_token, app_url = create_bitable_app(client, app_name, time_zone, "")
            else:
                raise
        table_id = create_table(client, app_token, table_name)
        print("[info] created fresh bitable app and requirements table")

    print(f"[created] app_token={app_token}")
    print(f"[created] table_id={table_id}")
    if app_url:
        print(f"[created] app_url={app_url}")
    write_output("app_token", app_token)
    write_output("table_id", table_id)
    write_output("app_url", app_url or "")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
