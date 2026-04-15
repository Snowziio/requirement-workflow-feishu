"""One-shot script: create the ProjectConfigs Bitable table in the existing app.

Reads schema from `bitable_project_configs_schema.json`. Prints the new
`table_id` and writes it to `$GITHUB_OUTPUT` if set, so the GitHub workflow
`init-project-configs-table.yml` can surface it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    AppTableCreateHeader,
    CreateAppTableRequest,
    CreateAppTableRequestBody,
    ReqTable,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from requirement_workflow_v12.bitable_schema import (  # noqa: E402
    load_project_config_field_specs,
    project_config_table_name,
)


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


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def build_headers() -> list[AppTableCreateHeader]:
    return [
        AppTableCreateHeader.builder()
        .field_name(spec.name)
        .type(spec.bitable_type)
        .build()
        for spec in load_project_config_field_specs()
    ]


def main() -> int:
    app_token = required_env("FEISHU_BITABLE_APP_TOKEN")
    table_name = os.environ.get(
        "FEISHU_BITABLE_PROJECT_CONFIGS_TABLE_NAME", project_config_table_name()
    )
    client = build_client()

    request = (
        CreateAppTableRequest.builder()
        .app_token(app_token)
        .request_body(
            CreateAppTableRequestBody.builder()
            .table(
                ReqTable.builder()
                .name(table_name)
                .default_view_name("All Project Configs")
                .fields(build_headers())
                .build()
            )
            .build()
        )
        .build()
    )
    response = client.bitable.v1.app_table.create(request)
    ensure_success(response, "create project_configs table")
    table_id = response.data.table_id
    print(f"[created] table_id={table_id}")
    print(f"[created] table_name={table_name}")
    print(f"[created] app_token={app_token}")
    write_output("table_id", table_id)
    write_output("table_name", table_name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - ops script
        print(f"[error] {exc}", file=sys.stderr)
        raise
