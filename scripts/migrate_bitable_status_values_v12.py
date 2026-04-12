from __future__ import annotations

import os
import sys

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableRecord,
    ListAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)


STATUS_ALIASES = {
    "DISCUSSION_ROUTING": "DRAFTING",
    "DISCUSSING": "DRAFTING",
    "AI_REVIEWING": "AI_REVIEW",
    "HUMAN_CONFIRMING": "HUMAN_CONFIRM",
    "REVIEWING": "FINAL_REVIEW",
    "REQ_APPROVED": "APPROVED",
}

PHASE_ALIASES = {
    "需求构造": "需求构造",
    "AI Review": "AI Review",
    "人工确认": "人工确认",
    "正式审查": "正式审查",
    "需求已批准": "需求已批准",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env: {name}")
    return value


def build_client() -> lark.Client:
    return (
        lark.Client.builder()
        .app_id(required_env("FEISHU_APP_ID"))
        .app_secret(required_env("FEISHU_APP_SECRET"))
        .build()
    )


def ensure_success(response, action: str) -> None:
    if not response.success():
        raise RuntimeError(f"Failed to {action}: {response.code} {response.msg}")


def list_records(client: lark.Client, app_token: str, table_id: str) -> list[object]:
    page_token = ""
    records: list[object] = []
    while True:
        request = (
            ListAppTableRecordRequest.builder()
            .app_token(app_token)
            .table_id(table_id)
            .page_size(500)
            .page_token(page_token)
            .build()
        )
        response = client.bitable.v1.app_table_record.list(request)
        ensure_success(response, "list bitable records")
        data = response.data
        records.extend(data.items or [])
        if not data.has_more:
            return records
        page_token = data.page_token or ""


def normalize_record_fields(fields: dict[str, object]) -> dict[str, object]:
    updates: dict[str, object] = {}
    raw_status = str(fields.get("状态", "")).strip()
    normalized_status = STATUS_ALIASES.get(raw_status)
    if normalized_status and normalized_status != raw_status:
        updates["状态"] = normalized_status

    raw_phase = str(fields.get("当前阶段", "")).strip()
    if raw_phase in PHASE_ALIASES and PHASE_ALIASES[raw_phase] != raw_phase:
        updates["当前阶段"] = PHASE_ALIASES[raw_phase]

    return updates


def update_record(
    client: lark.Client,
    app_token: str,
    table_id: str,
    record_id: str,
    fields: dict[str, object],
) -> None:
    request = (
        UpdateAppTableRecordRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .record_id(record_id)
        .request_body(AppTableRecord.builder().fields(fields).build())
        .build()
    )
    response = client.bitable.v1.app_table_record.update(request)
    ensure_success(response, f"update record {record_id}")


def main() -> int:
    client = build_client()
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = required_env("FEISHU_BITABLE_TABLE_ID")
    dry_run = os.environ.get("DRY_RUN", "0").strip() == "1"

    scanned = 0
    changed = 0
    records = list_records(client, app_token, table_id)
    for record in records:
        scanned += 1
        fields = dict(record.fields or {})
        updates = normalize_record_fields(fields)
        if not updates:
            continue
        changed += 1
        req_id = str(fields.get("REQ ID", "")).strip()
        print(f"[plan] record_id={record.record_id} req_id={req_id or '-'} updates={updates}")
        if dry_run:
            continue
        update_record(client, app_token, table_id, record.record_id, updates)
        print(f"[updated] record_id={record.record_id}")

    mode = "dry-run" if dry_run else "apply"
    print(f"[done] mode={mode} scanned={scanned} changed={changed}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
