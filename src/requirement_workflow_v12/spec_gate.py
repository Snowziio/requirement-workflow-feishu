from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import re
import yaml


@dataclass(frozen=True)
class GateFinding:
    kind: Literal["format", "semantic"]
    rule: str
    detail: str


@dataclass(frozen=True)
class GateResult:
    passed: bool
    findings: list[GateFinding]

    @property
    def has_format_failure(self) -> bool:
        return any(f.kind == "format" for f in self.findings)

    @property
    def has_semantic_failure(self) -> bool:
        return any(f.kind == "semantic" for f in self.findings)


_REQUIRED_AC_FIELDS = {"id", "title", "priority", "given", "expected",
                       "test_file", "test_function"}


def _check_ac_schedule_schema(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    try:
        doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
    except yaml.YAMLError as exc:
        return [GateFinding("format", "ac_schedule_schema", f"yaml parse error: {exc}")]
    acs = doc.get("acs", [])
    if not isinstance(acs, list):
        return [GateFinding("format", "ac_schedule_schema", "acs must be a list")]
    for idx, ac in enumerate(acs):
        missing = _REQUIRED_AC_FIELDS - set(ac.keys() if isinstance(ac, dict) else [])
        if missing:
            findings.append(GateFinding(
                "format", "ac_schedule_schema",
                f"acs[{idx}] missing fields: {sorted(missing)}",
            ))
    return findings


_TASK_LINE_RE = re.compile(r"^\s*[-*]?\s*T-\d{3,}\s+\S")


def _check_tasks_md_format(payload) -> list[GateFinding]:
    text = payload.get("tasks_md", "")
    has_any = any(_TASK_LINE_RE.match(line) for line in text.splitlines())
    if not has_any:
        return [GateFinding(
            "format", "tasks_md_format",
            "no `T-NNN <subject>` lines found in tasks.md",
        )]
    return []


def _check_path_consistency(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    try:
        doc = yaml.safe_load(payload["ac_schedule_yaml"]) or {}
    except yaml.YAMLError:
        return findings
    files = payload.get("harness_files", {})
    for ac in doc.get("acs", []) or []:
        if not isinstance(ac, dict):
            continue
        path = ac.get("test_file")
        if not path:
            continue
        if path not in files:
            findings.append(GateFinding(
                "format", "path_consistency",
                f"AC {ac.get('id')} test_file '{path}' not present in harness payload",
            ))
            continue
        ac_id = ac.get("id", "")
        if f"@pytest.mark.ac('{ac_id}')" not in files[path] \
           and f'@pytest.mark.ac("{ac_id}")' not in files[path]:
            findings.append(GateFinding(
                "format", "path_consistency",
                f"AC {ac_id}: test_file present but lacks @pytest.mark.ac",
            ))
    return findings


def _check_round_zero_ac_recall(payload, snapshot) -> list[GateFinding]:
    declared = set(payload.get("round_zero_ac_ids") or [])
    expected = set(snapshot.acm_active_slice)
    missing = expected - declared
    if missing:
        return [GateFinding(
            "semantic", "round_zero_ac_recall",
            f"Round 0 AC recall missing: {sorted(missing)}",
        )]
    return []


def _check_supersedes_completeness(payload, snapshot) -> list[GateFinding]:
    findings: list[GateFinding] = []
    decls = payload.get("supersedes_decl") or []
    active = set(snapshot.acm_active_slice)
    for decl in decls:
        old = decl.get("old_ac_id")
        if old and old not in active:
            findings.append(GateFinding(
                "semantic", "supersedes_completeness",
                f"supersedes target {old} not in current active slice",
            ))
    return findings


def _check_metadata_files_present(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    for key in ("design_md", "tasks_md", "ac_schedule_yaml"):
        if not (payload.get(key) or "").strip():
            findings.append(GateFinding(
                "format", "metadata_files_present",
                f"payload['{key}'] missing or empty",
            ))
    return findings


_DESIGN_REQUIRED_HEADERS = ("## supersedes", "## 项目级上下文消费")


def _check_design_md_required_sections(payload) -> list[GateFinding]:
    text = payload.get("design_md") or ""
    findings: list[GateFinding] = []
    for header in _DESIGN_REQUIRED_HEADERS:
        if header not in text:
            findings.append(GateFinding(
                "format", "design_md_required_sections",
                f"design.md missing required section: {header}",
            ))
    return findings


_SUPERSEDES_ITEM_RE = re.compile(r"^\s*-\s+取代\s+AC-[A-Z0-9-]+", re.MULTILINE)


def _extract_supersedes_section(text: str) -> str | None:
    """Return the body between ``## supersedes`` and the next ``## `` (or EOF)."""
    marker = "## supersedes"
    idx = text.find(marker)
    if idx == -1:
        return None
    body_start = idx + len(marker)
    next_idx = text.find("\n## ", body_start)
    return text[body_start:] if next_idx == -1 else text[body_start:next_idx]


def _check_supersedes_section_syntax(payload) -> list[GateFinding]:
    text = payload.get("design_md") or ""
    section = _extract_supersedes_section(text)
    if section is None:
        return []  # missing-section case is owned by design_md_required_sections
    if "no supersession" in section.lower():
        return []
    if _SUPERSEDES_ITEM_RE.search(section):
        return []
    return [GateFinding(
        "format", "supersedes_section_syntax",
        "## supersedes section must contain '- 取代 AC-...' lines or 'no supersession'",
    )]


def _check_harness_path_prefix(payload, snapshot) -> list[GateFinding]:
    expected_prefix = f"harness/tests/{snapshot.req_id}/"
    findings: list[GateFinding] = []
    for path in (payload.get("harness_files") or {}).keys():
        if not path.startswith(expected_prefix):
            findings.append(GateFinding(
                "format", "harness_path_prefix",
                f"harness file '{path}' must start with '{expected_prefix}'",
            ))
    return findings


_RESERVED_HARNESS_PATHS = ("acm-registry.yaml",)
_RESERVED_HARNESS_PREFIXES = ("docs/specs/",)


def _check_harness_scope_discipline(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    for path in (payload.get("harness_files") or {}).keys():
        if path in _RESERVED_HARNESS_PATHS or any(
            path.startswith(p) for p in _RESERVED_HARNESS_PREFIXES
        ):
            findings.append(GateFinding(
                "format", "harness_scope_discipline",
                f"harness_files key '{path}' is reserved (Coordinator-managed)",
            ))
    return findings


_AC_MARK_RE = re.compile(r"@pytest\.mark\.ac\(\s*['\"][^'\"]+['\"]\s*\)")


def _check_skeleton_unique_anchor(payload) -> list[GateFinding]:
    findings: list[GateFinding] = []
    for path, content in (payload.get("harness_files") or {}).items():
        count = len(_AC_MARK_RE.findall(content))
        if count != 1:
            findings.append(GateFinding(
                "format", "skeleton_unique_anchor",
                f"harness file '{path}' has {count} @pytest.mark.ac marks (expected 1)",
            ))
    return findings


def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_metadata_files_present(payload))
    findings.extend(_check_design_md_required_sections(payload))
    findings.extend(_check_supersedes_section_syntax(payload))
    findings.extend(_check_ac_schedule_schema(payload))
    findings.extend(_check_tasks_md_format(payload))
    findings.extend(_check_path_consistency(payload))
    findings.extend(_check_harness_path_prefix(payload, snapshot))
    findings.extend(_check_harness_scope_discipline(payload))
    findings.extend(_check_skeleton_unique_anchor(payload))
    findings.extend(_check_round_zero_ac_recall(payload, snapshot))
    findings.extend(_check_supersedes_completeness(payload, snapshot))
    return GateResult(passed=len(findings) == 0, findings=findings)
