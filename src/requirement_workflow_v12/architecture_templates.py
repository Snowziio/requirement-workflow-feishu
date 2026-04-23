from __future__ import annotations

import re
from datetime import date
from pathlib import Path


class UnknownCategory(Exception):
    """Requested category has no template on disk."""


TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "docs" / "context" / "architecture-templates"

_VERSION_RE = re.compile(r"^(?P<category>[a-z0-9\-]+)\.v(?P<num>\d+)\.yaml$")


def available_categories() -> list[str]:
    cats: set[str] = set()
    if not TEMPLATE_DIR.exists():
        return []
    for entry in TEMPLATE_DIR.iterdir():
        m = _VERSION_RE.match(entry.name)
        if m:
            cats.add(m.group("category"))
    return sorted(cats)


def _latest_template_path(category: str) -> tuple[str, Path]:
    best: tuple[int, Path] | None = None
    if not TEMPLATE_DIR.exists():
        raise UnknownCategory(f"template dir missing: {TEMPLATE_DIR}")
    for entry in TEMPLATE_DIR.iterdir():
        m = _VERSION_RE.match(entry.name)
        if not m or m.group("category") != category:
            continue
        num = int(m.group("num"))
        if best is None or num > best[0]:
            best = (num, entry)
    if best is None:
        raise UnknownCategory(f"no template for category: {category}")
    num, path = best
    return f"{category}.v{num}", path


def derive_pkg(project: str) -> str:
    """Lowercase and replace runs of non-alphanumeric-unicode chars with '_'."""
    # Insert underscore before uppercase letters (camelCase splitting)
    with_underscores = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", project)
    lowered = with_underscores.strip().lower()
    return re.sub(r"[^\w]+", "_", lowered, flags=re.UNICODE).strip("_")


def render_template(
    category: str,
    *,
    project: str,
    seed: dict[str, str] | None = None,
) -> tuple[str, str]:
    version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    seed = seed or {}
    text = (
        raw.replace("{pkg}", pkg)
           .replace("{project}", project)
           .replace("{date}", today)
           .replace("{{display_name}}", seed.get("display_name", ""))
           .replace("{{brief}}", seed.get("brief", ""))
           .replace("{{tech_stack}}", seed.get("tech_stack", ""))
    )
    return version, text


def parse_template_yaml(category: str) -> dict:
    """Load raw YAML for a category (latest version) as a Python dict.

    Placeholders like {pkg}, {project}, {date} are NOT substituted here —
    this is for structural inspection (e.g., reading frontend.subpath).
    """
    import yaml
    _version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict):
        raise UnknownCategory(f"template for {category} did not parse as dict")
    return parsed


def _fmt_tech_stack(stack: dict) -> str:
    if not stack:
        return "（未定义）"
    return " / ".join(f"{k}: {v}" for k, v in stack.items())


def _build_ui_context_section(parsed: dict) -> str | None:
    """Build a '## UI Context' Markdown section from parsed YAML.

    Returns None when the YAML has neither 'frontend' nor 'design' keys
    (i.e., existing YAMLs that haven't been extended yet).
    """
    has_frontend_key = "frontend" in parsed
    has_design_key = "design" in parsed
    if not (has_frontend_key or has_design_key):
        return None

    lines = ["## UI Context", ""]
    frontend = parsed.get("frontend")
    if frontend is None and has_frontend_key:
        lines.append(
            "- **前端**：本 category 默认无前端（若需管理后台见 enterprise-app 栈）"
        )
    elif frontend:
        lines.append(f"- **前端栈**：{_fmt_tech_stack(frontend.get('tech_stack', {}))}")
        lines.append(f"- **前端代码位置**：`{frontend.get('subpath', '')}`")
    design = parsed.get("design")
    if design:
        lines.append(
            "- **设计工具**：Claude Design（project URL 见 "
            "`project_configs` → `design.claude_design_project_url`）"
        )
        lines.append(
            f"- **Design System 快照**：`{design.get('design_system_snapshot_path', '')}`"
        )
        lines.append(f"- **Page Registry**：`{design.get('pages_registry_path', '')}`")
    return "\n".join(lines)
