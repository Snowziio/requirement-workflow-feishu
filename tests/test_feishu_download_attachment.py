import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _make_gateway():
    from requirement_workflow_v12.feishu_gateway import FeishuGateway
    gateway = FeishuGateway.__new__(FeishuGateway)
    gateway.settings = MagicMock()
    gateway.client = MagicMock()
    return gateway


def test_download_card_attachment_writes_to_path(tmp_path: Path):
    gateway = _make_gateway()
    dest = tmp_path / "handoff.zip"

    # Mock the private download helper (or the lark SDK call) to return bytes
    with patch.object(gateway, "_download_file_bytes", return_value=b"FAKE_ZIP_BYTES"):
        got = gateway.download_card_attachment(
            file_key="file-key-abc",
            message_id="msg-id-xyz",
            dest_path=dest,
        )
    assert got == dest
    assert dest.read_bytes() == b"FAKE_ZIP_BYTES"


def test_download_card_attachment_creates_parent_dir(tmp_path: Path):
    gateway = _make_gateway()
    dest = tmp_path / "nested" / "deeper" / "file.zip"
    with patch.object(gateway, "_download_file_bytes", return_value=b"x"):
        gateway.download_card_attachment(
            file_key="fk", message_id="mid", dest_path=dest,
        )
    assert dest.exists()
    assert dest.read_bytes() == b"x"


def test_download_card_attachment_returns_path_object(tmp_path: Path):
    gateway = _make_gateway()
    dest = tmp_path / "handoff.zip"
    with patch.object(gateway, "_download_file_bytes", return_value=b"x"):
        result = gateway.download_card_attachment(
            file_key="fk", message_id="mid", dest_path=dest,
        )
    assert isinstance(result, Path)
