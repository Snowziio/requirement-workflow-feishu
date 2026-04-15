from __future__ import annotations

import argparse
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

from requirement_workflow_v12.bitable_schema import BitableFieldSpec, coordinator_managed_field_specs


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


def build_field_payload(spec: BitableFieldSpec, *, field_id: str = "") -> AppTableField:
    # bitable_type is the int enum expected by lark-oapi; spec.field_type is the
    # human-readable string label from the JSON schema and must NOT be passed here.
    builder = AppTableFieldBuilder().field_name(spec.name).type(spec.bitable_type)
    if field_id:
        builder = builder.field_id(field_id)
    return builder.build()


def create_field(client: lark.Client, app_token: str, table_id: str, spec: BitableFieldSpec) -> None:
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


def update_field(client: lark.Client, app_token: str, table_id: str, field_id: str, spec: BitableFieldSpec) -> None:
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Bitable schema to v1.2 spec.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended create/update actions without calling Lark APIs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    client = build_client()
    field_specs = coordinator_managed_field_specs()

    current_fields = list_fields(client, app_token, table_id)
    print(f"[info] current field count: {len(current_fields)}")
    if args.dry_run:
        print("[info] dry-run mode — no changes will be applied")

    planned_creates: list[str] = []
    planned_updates: list[str] = []
    skipped: list[str] = []

    for spec in field_specs:
        existing = current_fields.get(spec.name)
        if existing is None:
            planned_creates.append(spec.name)
            if args.dry_run:
                print(f"[dry-run create] {spec.name} type={spec.bitable_type}")
            else:
                create_field(client, app_token, table_id, spec)
            continue

        # existing.type is the int enum; compare against spec.bitable_type
        # (not spec.field_type which is a string label).
        if existing.type != spec.bitable_type:
            planned_updates.append(spec.name)
            if args.dry_run:
                print(
                    f"[dry-run update] {spec.name} "
                    f"existing_type={existing.type} → {spec.bitable_type}"
                )
            else:
                update_field(client, app_token, table_id, existing.field_id, spec)
            continue

        skipped.append(spec.name)
        if args.dry_run:
            print(f"[dry-run skip] {spec.name}")

    print(
        f"[summary] create={len(planned_creates)} update={len(planned_updates)} skip={len(skipped)}"
    )
    if args.dry_run:
        print("[done] dry-run complete; no changes were made")
    else:
        print("[done] Bitable schema synced to v1.2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
