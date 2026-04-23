import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_gateway_minimal():
    """Return a FeishuGateway with SDK mocked at module level, for create_design_document tests."""
    from requirement_workflow_v12 import feishu_gateway as gw_module
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    # Mock SDK symbols used by create_design_document (same set create_plan_document uses)
    mocks = {
        "CreateDocumentRequest": MagicMock(),
        "CreateDocumentRequestBody": MagicMock(),
    }
    for name, mock in mocks.items():
        setattr(gw_module, name, mock)
    return gateway, gw_module


def _fake_requirement():
    req = MagicMock()
    req.req_id = "REQ-X-007"
    req.name = "头像审核"
    return req


def test_create_design_document_returns_none_when_no_folder_token():
    gateway, _ = _make_gateway_minimal()
    gateway.settings = MagicMock(feishu_doc_folder_token="")
    result = gateway.create_design_document(_fake_requirement())
    assert result is None


def test_create_design_document_returns_created_document_with_id_and_url():
    gateway, _ = _make_gateway_minimal()
    gateway.settings = MagicMock(
        feishu_doc_folder_token="folder_abc",
        feishu_base_url="https://feishu.example",
    )
    fake_document = MagicMock(document_id="doc_design_1")
    response = MagicMock(code=0, msg="ok", data=MagicMock(document=fake_document))
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.create.return_value = response

    result = gateway.create_design_document(_fake_requirement())
    assert result is not None
    assert result.document_id == "doc_design_1"
    assert result.document_url == "https://feishu.example/docx/doc_design_1"

    # Verify the title passed includes the REQ id + "Design Brief"
    # (The builder chain is mocked; confirm SDK create was called)
    gateway.client.docx.v1.document.create.assert_called_once()


def test_create_design_document_title_format():
    """Verify title contains REQ id, name, and 'Design Brief'."""
    gateway, gw_module = _make_gateway_minimal()
    gateway.settings = MagicMock(
        feishu_doc_folder_token="folder_abc",
        feishu_base_url="https://feishu.example",
    )
    # Spy on what title the builder body receives
    captured_titles = []
    mock_body_instance = MagicMock()
    def capture_title(title):
        captured_titles.append(title)
        return mock_body_instance
    mock_body_instance.folder_token.return_value = mock_body_instance
    mock_body_instance.title.side_effect = capture_title
    mock_body_instance.build.return_value = MagicMock()

    gw_module.CreateDocumentRequestBody.builder.return_value = mock_body_instance

    fake_document = MagicMock(document_id="doc_design_2")
    response = MagicMock(data=MagicMock(document=fake_document))
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.create.return_value = response

    gateway.create_design_document(_fake_requirement())
    assert len(captured_titles) == 1
    title = captured_titles[0]
    assert "REQ-X-007" in title
    assert "头像审核" in title
    assert "Design" in title
