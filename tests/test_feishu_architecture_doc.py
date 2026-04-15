import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_gateway():
    """Return a FeishuGateway instance with lark SDK symbols mocked at module level."""
    from requirement_workflow_v12 import feishu_gateway as gw_module
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)

    # Replace module-level SDK stubs with real MagicMocks so builder() chains work
    mock_block_cls = MagicMock()
    mock_create_doc_request = MagicMock()
    mock_create_doc_request_body = MagicMock()
    mock_create_block_children_request = MagicMock()
    mock_create_block_children_request_body = MagicMock()
    mock_text = MagicMock()
    mock_text_element = MagicMock()
    mock_text_run = MagicMock()

    gateway._mock_patches = {
        "Block": mock_block_cls,
        "CreateDocumentRequest": mock_create_doc_request,
        "CreateDocumentRequestBody": mock_create_doc_request_body,
        "CreateDocumentBlockChildrenRequest": mock_create_block_children_request,
        "CreateDocumentBlockChildrenRequestBody": mock_create_block_children_request_body,
        "Text": mock_text,
        "TextElement": mock_text_element,
        "TextRun": mock_text_run,
    }

    for name, mock in gateway._mock_patches.items():
        setattr(gw_module, name, mock)

    return gateway, gw_module


def test_create_architecture_document_calls_docx_api():
    gateway, gw_module = _make_gateway()
    gateway.settings = MagicMock(
        feishu_doc_folder_token="folder_xyz",
        feishu_base_url="https://feishu.example",
    )
    fake_document = MagicMock(document_id="doc_arch_1")
    response = MagicMock(
        code=0,
        msg="ok",
        data=MagicMock(document=fake_document),
    )
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.create.return_value = response

    result = gateway.create_architecture_document("MyProj")
    assert result is not None
    assert result.document_id == "doc_arch_1"
    assert result.document_url.endswith("/docx/doc_arch_1")


def test_create_architecture_document_without_folder_returns_none():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock(feishu_doc_folder_token="")
    assert gateway.create_architecture_document("Anything") is None


def test_write_document_text_creates_block():
    gateway, gw_module = _make_gateway()
    gateway.settings = MagicMock()
    response = MagicMock(code=0, msg="ok")
    response.success.return_value = True
    gateway.client = MagicMock()
    gateway.client.docx.v1.document_block_children.create.return_value = response

    gateway.write_document_text("doc_arch_1", "version: 2026-04-15\nproject: MyProj")
    gateway.client.docx.v1.document_block_children.create.assert_called_once()


def test_fetch_document_revision_returns_string():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    response = MagicMock(code=0, msg="ok")
    response.success.return_value = True
    response.data = MagicMock(revision_id=42)
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.raw_content.return_value = response

    rev = gateway.fetch_document_revision("doc_arch_1")
    assert rev == "rev-42"


def test_fetch_document_revision_falls_back_when_api_unavailable():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway

    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    gateway.client = MagicMock()
    gateway.client.docx.v1.document.raw_content.side_effect = AttributeError("no raw_content")

    rev = gateway.fetch_document_revision("doc_arch_1")
    assert rev.startswith("ts-") and rev[3:].isdigit()
