import sys
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from requirement_workflow_v12.models import Requirement, WorkflowStatus


def test_dispatch_design_start_if_needed_creates_doc_and_starts_design():
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed

    app = MagicMock()
    app.service = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d-1", document_url="https://feishu/d/1")
    app.gateway.create_design_document.return_value = created_doc

    r = Requirement(
        req_id="REQ-X-001", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )

    dispatch_design_start_if_needed(app, r)

    app.gateway.create_design_document.assert_called_once_with(r)
    app.service.design_start.assert_called_once_with(
        "REQ-X-001", design_doc_id="d-1", design_doc_url="https://feishu/d/1",
    )


def test_dispatch_design_start_if_needed_skips_when_needs_ui_false():
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed

    app = MagicMock()
    app.gateway = MagicMock()
    app.service = MagicMock()

    r = Requirement(
        req_id="REQ-X-002", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=False,
    )
    dispatch_design_start_if_needed(app, r)

    app.gateway.create_design_document.assert_not_called()
    app.service.design_start.assert_not_called()


def test_dispatch_design_start_if_needed_handles_doc_creation_failure():
    """If create_design_document fails, log warning and skip design_start. No raise."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed

    app = MagicMock()
    app.gateway = MagicMock()
    app.gateway.create_design_document.side_effect = RuntimeError("feishu 500")
    app.service = MagicMock()

    r = Requirement(
        req_id="REQ-X-003", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    # Should not raise
    dispatch_design_start_if_needed(app, r)
    app.service.design_start.assert_not_called()


def test_dispatch_design_start_if_needed_handles_design_start_failure():
    """If design_start raises, log warning. No re-raise."""
    from requirement_workflow_v12.service_app import dispatch_design_start_if_needed

    app = MagicMock()
    app.gateway = MagicMock()
    created_doc = MagicMock(document_id="d", document_url="u")
    app.gateway.create_design_document.return_value = created_doc
    app.service = MagicMock()
    app.service.design_start.side_effect = ValueError("guards failed")

    r = Requirement(
        req_id="REQ-X-004", name="n", project="X", summary="s", creator="c",
        status=WorkflowStatus.APPROVED, needs_ui=True,
    )
    dispatch_design_start_if_needed(app, r)
    # No exception propagated
