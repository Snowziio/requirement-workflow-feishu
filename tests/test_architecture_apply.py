import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from requirement_workflow_v12.project_repo.architecture_apply import (
    apply_architecture_changes, ArchitectureApplyError,
)


ORIGINAL = """# Architecture

## 会话存储

旧方案：本地文件。

## 鉴权

OAuth2。
"""


def test_apply_replaces_matching_section():
    changes = [{
        "section_path": "## 会话存储",
        "before": "## 会话存储\n\n旧方案：本地文件。",
        "after": "## 会话存储\n\n新方案：Redis 7.x。",
        "rationale": "D1",
    }]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "Redis 7.x" in new
    assert "旧方案：本地文件" not in new
    assert "## 鉴权" in new  # unchanged section preserved


def test_apply_appends_new_section_when_before_empty():
    changes = [{
        "section_path": "## 缓存",
        "before": "",
        "after": "## 缓存\n\n新增：LRU 1000 项。",
        "rationale": "D2",
    }]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "## 缓存" in new
    assert "LRU 1000 项" in new
    assert "## 会话存储" in new
    assert "## 鉴权" in new


def test_apply_multiple_changes_applied_sequentially():
    changes = [
        {
            "section_path": "## 会话存储",
            "before": "## 会话存储\n\n旧方案：本地文件。",
            "after": "## 会话存储\n\n新方案：Redis。",
            "rationale": "D1",
        },
        {
            "section_path": "## 缓存",
            "before": "",
            "after": "## 缓存\n\nLRU.",
            "rationale": "D2",
        },
    ]
    new = apply_architecture_changes(ORIGINAL, changes)
    assert "Redis" in new
    assert "LRU" in new


def test_apply_rejects_before_mismatch():
    changes = [{
        "section_path": "## 会话存储",
        "before": "## 会话存储\n\n某个不存在的旧内容。",
        "after": "## 会话存储\n\nRedis。",
        "rationale": "D1",
    }]
    with pytest.raises(ArchitectureApplyError) as exc_info:
        apply_architecture_changes(ORIGINAL, changes)
    assert exc_info.value.recoverable is True
    assert exc_info.value.reason == "architecture_conflict"


def test_apply_rejects_new_section_with_nonempty_before():
    changes = [{
        "section_path": "## 不存在的节",
        "before": "some old content",
        "after": "## 不存在的节\n\nnew.",
        "rationale": "D1",
    }]
    with pytest.raises(ArchitectureApplyError) as exc_info:
        apply_architecture_changes(ORIGINAL, changes)
    assert exc_info.value.recoverable is True


def test_empty_changes_list_is_noop():
    assert apply_architecture_changes(ORIGINAL, []) == ORIGINAL


def test_apply_preserves_higher_level_header_when_replacing_subsection():
    doc = """# Top

## A

aaa

### A.1

xxx

## B

bbb
"""
    changes = [{
        "section_path": "### A.1",
        "before": "### A.1\n\nxxx",
        "after": "### A.1\n\nyyy",
        "rationale": "t",
    }]
    new = apply_architecture_changes(doc, changes)
    assert "yyy" in new
    assert "xxx" not in new
    assert "## B" in new  # next higher-level header untouched
    assert "## A" in new
