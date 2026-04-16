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
