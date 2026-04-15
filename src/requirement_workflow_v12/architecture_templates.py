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


def render_template(category: str, *, project: str) -> tuple[str, str]:
    version, path = _latest_template_path(category)
    raw = path.read_text(encoding="utf-8")
    pkg = derive_pkg(project)
    today = date.today().isoformat()
    text = (
        raw.replace("{pkg}", pkg)
           .replace("{project}", project)
           .replace("{date}", today)
    )
    return version, text
