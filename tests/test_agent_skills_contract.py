from __future__ import annotations

from pathlib import Path

import yaml


AGENT_ROOT = Path(__file__).resolve().parents[1] / "docs" / "agents"
GENERATIVE_AGENTS = {
    "design-brief-author",
    "plan-author",
    "requirement-author",
    "spec-author",
    "spec-transformer",
}


def _skill_paths() -> list[Path]:
    return sorted(AGENT_ROOT.glob("*/SKILL.md"))


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} missing YAML frontmatter"
    raw = text.split("---", 2)[1]
    data = yaml.safe_load(raw) or {}
    assert isinstance(data, dict)
    return data


def test_agent_skill_descriptions_are_trigger_only():
    """Superpowers-style descriptions should help discovery, not summarize workflow."""
    forbidden_workflow_terms = (
        "Step",
        "流程",
        "产出",
        "回写",
        "callback",
        "分三段",
        "按 9 节",
        "7 步",
        "最多 3 轮",
    )
    for path in _skill_paths():
        data = _read_frontmatter(path)
        desc = str(data.get("description", ""))
        assert desc.startswith("Use when "), f"{path} description must start with 'Use when '"
        assert len(desc) <= 500, f"{path} description is too long"
        for term in forbidden_workflow_terms:
            assert term not in desc, f"{path} description leaks workflow term: {term}"


def test_generative_agent_skills_define_context_and_evidence_gates():
    required_sections = (
        "## Context Inventory",
        "## Missing Context Policy",
        "## 生成前自检",
        "## Callback Evidence",
    )
    for name in GENERATIVE_AGENTS:
        path = AGENT_ROOT / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        for section in required_sections:
            assert section in text, f"{path} missing {section}"


def test_agent_callback_contracts_do_not_contradict_context_fetching():
    """A skill cannot require context fetch and also say the first tool call is callback."""
    banned_phrases = (
        "本轮的**第一个**（也是必做的）tool call 必须是",
        "本阶段本轮的**第一个**（也是必做的）tool call 必须是",
        "第一个 tool call 就是它",
    )
    for path in _skill_paths():
        text = path.read_text(encoding="utf-8")
        for phrase in banned_phrases:
            assert phrase not in text, f"{path} has contradictory callback wording: {phrase}"
