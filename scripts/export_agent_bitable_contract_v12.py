from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from requirement_workflow_v12.bitable_schema import reader_visible_field_specs


OUTPUT_PATH = ROOT / "docs" / "specs" / "bitable-agent-readable-fields-v1.2.md"


def render_markdown() -> str:
    author_specs = reader_visible_field_specs("author")
    reviewer_specs = reader_visible_field_specs("reviewer")
    lines = [
        "# Bitable Agent Read Contract v1.2",
        "",
        "> 本文档由 `bitable_schema_v12.json` 派生，用于约束 author / reviewer 可依赖的 Bitable 字段。",
        "",
        "## 1. 规则",
        "",
        "- author / reviewer 只读这些字段，不自行假设额外字段存在。",
        "- Coordinator 是这些字段的唯一写入方。",
        "- skill 模板、TOOLS.md、方法论文档引用字段时，应以这份清单和 `bitable_schema_v12.json` 为准。",
        "",
        "## 2. Author 可读字段",
        "",
        "| 字段名 | 类型 | 必填 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for spec in author_specs:
        lines.append(f"| {spec.name} | {spec.field_type} | {'是' if spec.required else '否'} | {spec.description} |")
    lines.extend(
        [
            "",
            "## 3. Reviewer 可读字段",
            "",
            "| 字段名 | 类型 | 必填 | 说明 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for spec in reviewer_specs:
        lines.append(f"| {spec.name} | {spec.field_type} | {'是' if spec.required else '否'} | {spec.description} |")
    lines.extend(
        [
            "",
            "## 4. 使用方式",
            "",
            "- author / reviewer 先按 `req_id` 调 context query，再按这里的字段理解状态。",
            "- 如果 `需求文档链接` 非空，author 必须复用，不得新建第二份文档。",
            "- 如果后续要新增字段，先改 `bitable_schema_v12.json`，再同步 Bitable 和 skill 文档。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    OUTPUT_PATH.write_text(render_markdown() + "\n", encoding="utf-8")
    print(f"[written] {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
