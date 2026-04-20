"""Idempotent sync of Bitable project_configs table schema.

Mirrors scripts/sync_bitable_schema_v12.py but targets the separate
project_configs table (FEISHU_BITABLE_PROJECT_CONFIGS_TABLE_ID) and drives
the field list from bitable_project_configs_schema.json via
load_project_config_field_specs().

Creates any fields that are missing; does NOT delete or rename existing
fields. Safe to re-run.
"""
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
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from requirement_workflow_v12.bitable_schema import (  # noqa: E402
    ProjectConfigFieldSpec,
    load_project_config_field_specs,
)


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


def build_field_payload(spec: ProjectConfigFieldSpec) -> AppTableField:
    return AppTableFieldBuilder().field_name(spec.name).type(spec.bitable_type).build()


def create_field(
    client: lark.Client, app_token: str, table_id: str, spec: ProjectConfigFieldSpec
) -> None:
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
    print(f"[created] {spec.name} (type={spec.field_type})")


def ensure_success(response, action: str) -> None:
    if not response.success():
        raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Bitable project_configs table schema (idempotent create-only)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended create actions without calling Lark APIs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_PROJECT_CONFIGS_TABLE_ID")
    client = build_client()
    field_specs = load_project_config_field_specs()

    current_fields = list_fields(client, app_token, table_id)
    print(f"[info] current field count in project_configs table: {len(current_fields)}")
    if args.dry_run:
        print("[info] dry-run mode — no changes will be applied")

    planned_creates: list[str] = []
    skipped: list[str] = []

    for spec in field_specs:
        if spec.name in current_fields:
            skipped.append(spec.name)
            if args.dry_run:
                print(f"[dry-run skip] {spec.name}")
            continue
        planned_creates.append(spec.name)
        if args.dry_run:
            print(f"[dry-run create] {spec.name} type={spec.field_type}")
        else:
            create_field(client, app_token, table_id, spec)

    print(f"[summary] create={len(planned_creates)} skip={len(skipped)}")
    if args.dry_run:
        print("[done] dry-run complete; no changes were made")
    else:
        print("[done] project_configs schema synced")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
