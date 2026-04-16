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


def run_gate(payload: dict, snapshot) -> GateResult:
    findings: list[GateFinding] = []
    findings.extend(_check_ac_schedule_schema(payload))
    return GateResult(passed=len(findings) == 0, findings=findings)
