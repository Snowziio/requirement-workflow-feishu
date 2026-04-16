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


import threading
import time
from unittest.mock import MagicMock


def test_fetch_snapshot_returns_sha_and_doc():
    gw = MagicMock()
    gw.fetch_file_sha = MagicMock(return_value=(
        "sha-1",
        "version: 3\nentries:\n  - {ac_id: AC-1, req_id: R, status: active, priority: P0}\n",
    ))
    reg = AcmRegistry(gateway=gw)
    sha, doc = reg.fetch_snapshot("o/r")
    assert sha == "sha-1"
    assert len(doc.entries) == 1
    gw.fetch_file_sha.assert_called_once_with("o/r", "main", "acm-registry.yaml")


def test_write_lock_serializes_concurrent_callers():
    reg = AcmRegistry(gateway=None)
    order = []
    started = threading.Event()

    def worker(name: str):
        with reg.write_lock():
            order.append(("enter", name))
            time.sleep(0.02)
            order.append(("exit", name))

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    # Serialization: each thread's (enter, exit) are adjacent, never interleaved
    assert order in (
        [("enter", "a"), ("exit", "a"), ("enter", "b"), ("exit", "b")],
        [("enter", "b"), ("exit", "b"), ("enter", "a"), ("exit", "a")],
    )


def test_write_lock_is_context_manager_and_releases():
    reg = AcmRegistry(gateway=None)
    with reg.write_lock():
        pass
    # Acquiring a second time after release must succeed within timeout
    with reg.write_lock():
        pass
