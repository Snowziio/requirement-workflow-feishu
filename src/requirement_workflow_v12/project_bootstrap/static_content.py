"""Python constants for Bootstrap Step 4 populate commit.

All per-project / per-category files rendered here. Template repo
(Snowziio/Template-repository) stays minimal and category-agnostic;
this module is the canonical source for everything that varies.
"""
from __future__ import annotations

from datetime import date

from ..architecture_templates import derive_pkg


PROJECT_README_MD = """# project/ —— 项目级索引与上下文

本目录由 Bootstrap 在项目创建时自动落盘，存放**项目级**（非 REQ 级）的索引与上下文文件。

## req-registry.yaml

项目级 REQ 索引。由 coordinator service **自动 append**（非 plan-author 产出）。

### Schema (human + AI readable)

```yaml
project: <name>                    # 与 project_configs.project 一致
requirements:
  - req_id: REQ-YYYY-MM-DD-NNN     # 需求 ID
    title: "..."                   # 需求名称
    status: DRAFTING | APPROVED | PLANNING | SPEC_DRAFTING | MERGED | ABANDONED
    plan_id: null | PLAN-YYYY-MM-DD-NNN
    spec_pr: null | 123            # GitHub PR number
    created_at: 2026-04-20T10:00:00
```

### Update rules

- 写入方：coordinator service（不是 AI agent）
- 时机：REQ 创建 / 状态变更 / plan / spec PR 产出
- 失败不阻塞 REQ 主流程，只记告警 log

## environments.yaml

项目级环境抽象（dev / staging / prod），MVP 为占位骨架，演化通道延后。

## SECRETS-TODO.md

按 category 列出需要人工填充的 GitHub Actions secrets 清单；CI 配置 workflow 会读这些 secrets。
"""


def render_req_registry_yaml(*, project: str) -> str:
    return (
        "# project/req-registry.yaml\n"
        "# 自动生成于 Bootstrap 阶段；格式见 project/README.md\n"
        f"project: {project}\n"
        "requirements: []\n"
    )


def render_environments_yaml(*, category: str) -> str:
    return (
        "# project/environments.yaml\n"
        "# 项目级环境抽象（MVP 骨架；演化通道延后）\n"
        f"# category: {category}\n"
        "environments:\n"
        "  dev: {}\n"
        "  staging: {}\n"
        "  prod: {}\n"
    )


_SECRETS_CATEGORY_HINTS: dict[str, list[str]] = {
    "enterprise-app": ["DATABASE_URL", "JWT_SIGNING_KEY"],
    "enterprise-bot": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    "miniprogram": ["WECHAT_APP_ID", "WECHAT_APP_SECRET"],
    "public-web-site": ["ANALYTICS_TOKEN"],
    "saas-ai-automation": ["OPENAI_API_KEY", "DATABASE_URL"],
}


def render_secrets_todo(*, category: str) -> str:
    hints = _SECRETS_CATEGORY_HINTS.get(category, [])
    bullet_lines = "\n".join(f"- [ ] `{k}`" for k in hints) if hints else "- [ ] (空)"
    return (
        f"# SECRETS-TODO ({category})\n\n"
        "以下 secrets 需在 GitHub repo Settings → Secrets and variables → Actions 中手动填充，"
        "Bootstrap 阶段不自动注入。\n\n"
        f"{bullet_lines}\n\n"
        "填完后可删除此文件。\n"
    )


def render_claude_md(*, project: str) -> str:
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    return (
        f"# CLAUDE.md — {project}\n\n"
        f"项目包名：`{pkg}`\n\n"
        f"创建于 Bootstrap：{today}\n\n"
        "## Conventions\n\n"
        "（Bootstrap 占位；后续通过 REQ 的 project_context_change gate 演化）\n"
    )


def render_skill_md(*, project: str) -> str:
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    return (
        f"# SKILL.md — {project}\n\n"
        f"项目包名：`{pkg}`\n\n"
        f"创建于 Bootstrap：{today}\n\n"
        "## Project-specific agent overrides\n\n"
        "（Bootstrap 占位；后续通过 REQ 的 project_context_change gate 演化）\n"
    )
