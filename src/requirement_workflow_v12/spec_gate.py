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


def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_ac_schedule_schema(payload))
    findings.extend(_check_tasks_md_format(payload))
    findings.extend(_check_path_consistency(payload))
    findings.extend(_check_round_zero_ac_recall(payload, snapshot))
    findings.extend(_check_supersedes_completeness(payload, snapshot))
    return GateResult(passed=len(findings) == 0, findings=findings)
