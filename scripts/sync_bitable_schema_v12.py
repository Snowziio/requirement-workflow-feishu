from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableField,
    AppTableFieldBuilder,
    CreateAppTableFieldRequest,
    ListAppTableFieldRequest,
    UpdateAppTableFieldRequest,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from requirement_workflow_v12.bitable_schema import coordinator_managed_field_specs


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def build_client() -> lark.Client:
    app_id = required_env("FEISHU_APP_ID")
    app_secret = required_env("FEISHU_APP_SECRET")
    return lark.Client.builder().app_id(app_id).app_secret(app_secret).build()


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
        response = client.bitable.v1.app_table_field.list(request)
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
    response = client.bitable.v1.app_table_field.create(request)
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
    response = client.bitable.v1.app_table_field.update(request)
    ensure_success(response, f"update bitable field {spec.name}")
    print(f"[updated] {spec.name}")


def ensure_success(response, action: str) -> None:
    if not response.success():
        raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")


def main() -> int:
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    client = build_client()
    field_specs = coordinator_managed_field_specs()

    current_fields = list_fields(client, app_token, table_id)
    print(f"[info] current field count: {len(current_fields)}")

    for spec in field_specs:
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
