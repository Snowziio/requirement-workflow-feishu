import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.acm_registry import (
    AcmRegistry, AcEntry, RegistryDoc, SupersedeDecl,
)


def test_parse_active_slice_returns_only_active_ids():
    text = (
        "version: 3\n"
        "entries:\n"
        "  - {ac_id: AC-001, req_id: R, status: active, priority: P0}\n"
        "  - {ac_id: AC-002, req_id: R, status: retired, priority: P1}\n"
        "  - {ac_id: AC-003, req_id: R, status: active, priority: P0}\n"
    )
    reg = AcmRegistry(gateway=None)
    assert reg.parse_active_slice(text) == ["AC-001", "AC-003"]


def test_parse_active_slice_empty_when_no_entries():
    reg = AcmRegistry(gateway=None)
    assert reg.parse_active_slice("version: 3\nentries: []\n") == []


def test_compose_patch_appends_active_entries():
    reg = AcmRegistry(gateway=None)
    current = RegistryDoc(version=3, entries=[
        AcEntry("AC-001", "REQ-A", "active", "P0"),
    ])
    new_acs = [{"id": "AC-100", "priority": "P0"}]
    patched = reg.compose_patch(
        current, new_acs=new_acs, supersedes=[], req_id="REQ-B",
    )
    ids = [e.ac_id for e in patched.entries]
    assert "AC-001" in ids
    assert "AC-100" in ids
    new_entry = next(e for e in patched.entries if e.ac_id == "AC-100")
    assert new_entry.status == "active"
    assert new_entry.req_id == "REQ-B"


def test_compose_patch_marks_superseded_old_ac():
    reg = AcmRegistry(gateway=None)
    current = RegistryDoc(version=3, entries=[
        AcEntry("AC-001", "REQ-A", "active", "P0"),
    ])
    patched = reg.compose_patch(
        current,
        new_acs=[{"id": "AC-100", "priority": "P0"}],
        supersedes=[SupersedeDecl(old_ac_id="AC-001", by_ac_id="AC-100")],
        req_id="REQ-B",
    )
    old = next(e for e in patched.entries if e.ac_id == "AC-001")
    assert old.status == "retired"
    assert old.superseded_by == "AC-100"
