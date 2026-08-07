"""Tests for feishu_office_tool — upload/import/export and mapping persistence."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_module():
    """Lazy import to avoid heavy lark_oapi eager loading at collection time."""
    import importlib

    return importlib.import_module("tools.feishu_office_tool")


@pytest.fixture
def feishu_office_tool():
    return _load_module()


@pytest.fixture
def temp_docx(tmp_path: Path):
    path = tmp_path / "report.docx"
    path.write_bytes(b"fake docx content")
    return str(path)


@pytest.fixture
def fake_client():
    """Return a mock lark client whose .request() returns configurable responses."""
    return MagicMock()


@pytest.fixture(autouse=True)
def patch_lark(feishu_office_tool, fake_client):
    """The lark_oapi SDK is an optional dependency; mock it for all tests."""
    AccessTokenType = MagicMock()
    HttpMethod = MagicMock()
    BaseRequest = MagicMock()

    with patch.object(feishu_office_tool, "_require_lark_imports", return_value=(AccessTokenType, HttpMethod, BaseRequest)):
        with patch.object(feishu_office_tool, "_require_client", return_value=fake_client):
            yield


def _make_response(code: int = 0, body: dict | None = None, content: bytes | None = None):
    resp = MagicMock()
    resp.code = code
    resp.msg = "ok" if code == 0 else "error"
    resp.data = body

    raw = MagicMock()
    raw.content = json.dumps({"data": body}).encode("utf-8") if content is None else content
    resp.raw = raw

    return resp


class TestOfficeMap:
    def test_round_trip_mapping(self, feishu_office_tool, tmp_path: Path):
        with patch.object(feishu_office_tool, "_office_map_path", return_value=tmp_path / "map.json"):
            feishu_office_tool.set_office_mapping("/tmp/a.docx", "doc_token_1", "docx")
            mapping = feishu_office_tool.get_office_mapping("/tmp/a.docx")

        assert mapping == {"doc_type": "docx", "token": "doc_token_1"}

    def test_clear_mapping(self, feishu_office_tool, tmp_path: Path):
        with patch.object(feishu_office_tool, "_office_map_path", return_value=tmp_path / "map.json"):
            feishu_office_tool.set_office_mapping("/tmp/a.docx", "doc_token_1", "docx")
            feishu_office_tool.clear_office_mapping("/tmp/a.docx")
            assert feishu_office_tool.get_office_mapping("/tmp/a.docx") is None


class TestUploadAndImport:
    def test_unsupported_extension(self, feishu_office_tool, tmp_path: Path):
        bad = tmp_path / "file.pptx"
        bad.write_bytes(b"x")

        with pytest.raises(ValueError, match="Unsupported extension"):
            feishu_office_tool.upload_and_import_office_file(str(bad))

    def test_happy_path_docx(self, feishu_office_tool, temp_docx: str, fake_client):
        upload_body = {"code": 0, "data": {"file_token": "file_token_1"}}
        create_resp = _make_response(
            body={"ticket": "ticket_1"}
        )
        poll_resp = _make_response(
            body={
                "result": {
                    "status": "success",
                    "token": "doc_token_1",
                    "type": "docx",
                    "url": "https://example.com/doc",
                }
            }
        )

        fake_client.request.side_effect = [create_resp, poll_resp]

        with patch.object(feishu_office_tool, "_get_tenant_access_token", return_value="tenant_token"):
            with patch.object(feishu_office_tool, "_get_root_folder_token", return_value="root_token_1"):
                with patch.object(feishu_office_tool, "_post_multipart_upload", return_value=upload_body):
                    with patch.object(feishu_office_tool, "_office_map_path", return_value=Path(tempfile.mktemp())):
                        result = feishu_office_tool.upload_and_import_office_file(temp_docx)

        assert result["token"] == "doc_token_1"
        assert result["type"] == "docx"
        assert result["url"] == "https://example.com/doc"


class TestExportAndOverwrite:
    def test_no_mapping(self, feishu_office_tool, tmp_path: Path):
        target = tmp_path / "report.docx"
        target.write_bytes(b"x")

        with patch.object(feishu_office_tool, "_office_map_path", return_value=Path(tempfile.mktemp())):
            with pytest.raises(RuntimeError, match="No Feishu cloud document linked"):
                feishu_office_tool.export_and_overwrite_office_file(str(target))

    def test_happy_path(self, feishu_office_tool, tmp_path: Path, fake_client):
        target = tmp_path / "report.docx"
        target.write_bytes(b"old content")

        create_resp = _make_response(body={"ticket": "ticket_e"})
        poll_resp = _make_response(
            body={"result": {"file_token": "file_token_e", "status": "success"}}
        )
        download_resp = _make_response(content=b"new content")

        fake_client.request.side_effect = [create_resp, poll_resp, download_resp]

        map_path = tmp_path / "map.json"
        with patch.object(feishu_office_tool, "_office_map_path", return_value=map_path):
            feishu_office_tool.set_office_mapping(str(target), "doc_token_1", "docx")
            result = feishu_office_tool.export_and_overwrite_office_file(str(target))

        assert result["bytes_written"] == len(b"new content")
        assert target.read_bytes() == b"new content"
