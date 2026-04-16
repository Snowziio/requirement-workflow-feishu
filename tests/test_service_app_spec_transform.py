import re
import pytest

SPEC_RESTART_RE = re.compile(r"^/spec\s+restart\s+(REQ-\S+)\s*$")


@pytest.mark.parametrize("text,expected", [
    ("/spec restart REQ-PROJ-005", "REQ-PROJ-005"),
    ("/spec  restart  REQ-X-1", "REQ-X-1"),
    ("/spec restart REQ-X ", "REQ-X"),
])
def test_slash_restart_parses(text, expected):
    m = SPEC_RESTART_RE.match(text)
    assert m is not None
    assert m.group(1) == expected


@pytest.mark.parametrize("text", [
    "/spec restart",
    "spec restart REQ-X",
    "/spec lock REQ-X",
    "",
])
def test_slash_restart_rejects(text):
    assert SPEC_RESTART_RE.match(text) is None


from unittest.mock import MagicMock


def test_handle_spec_restart_command_calls_coordinator():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from requirement_workflow_v12.service_app import CoordinatorRuntimeApp
    app = CoordinatorRuntimeApp.__new__(CoordinatorRuntimeApp)
    app.service = MagicMock()
    event = MagicMock()
    event.chat_id = "oc_test_chat"
    result = app._handle_spec_restart_command(req_id="REQ-PROJ-1", context=event)
    app.service.spec_restart.assert_called_once_with("REQ-PROJ-1")
    assert len(result) == 1
    assert "REQ-PROJ-1" in result[0].text
