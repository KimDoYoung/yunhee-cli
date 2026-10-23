"""
Tests for Gotenberg PDF Generator (ext_gotenberg.py)
"""

from unittest.mock import MagicMock, patch

from yunhee.agent.tools.ext_gotenberg import (
    convert_markdown_to_pdf,
    export_pdf_from_file,
    render_html_from_markdown,
)


def test_render_html_from_markdown():
    md = "# 테스트 제목\n\n- 항목 1\n- 항목 2\n\n```python\nprint('hello')\n```"
    html = render_html_from_markdown(md, title="테스트 문서")
    assert "<title>테스트 문서</title>" in html
    assert "<h1" in html
    assert "테스트 제목" in html
    assert "항목 1" in html
    assert "<code>" in html or "<pre>" in html


def test_convert_markdown_to_pdf_success(tmp_path):
    pdf_path = tmp_path / "test.pdf"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = b"%PDF-1.4 mock pdf content bytes"

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp

        ok, msg = convert_markdown_to_pdf("# Test", pdf_path, gotenberg_url="http://fake-gotenberg:3000")

    assert ok is True
    assert "✔ PDF 발간 완료" in msg
    assert pdf_path.is_file()
    assert pdf_path.read_bytes() == b"%PDF-1.4 mock pdf content bytes"


def test_convert_markdown_to_pdf_error(tmp_path):
    pdf_path = tmp_path / "test.pdf"

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.headers = {"content-type": "text/plain"}

    with patch("httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_resp

        ok, msg = convert_markdown_to_pdf("# Test", pdf_path, gotenberg_url="http://fake-gotenberg:3000")

    assert ok is False
    assert "Gotenberg PDF 변환 실패" in msg


def test_export_pdf_from_file(tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Doc Content", encoding="utf-8")
    pdf_out = tmp_path / "doc.pdf"

    with patch("yunhee.agent.tools.ext_gotenberg.convert_markdown_to_pdf", return_value=(True, "✔ PDF 발간 완료")):
        ok, msg = export_pdf_from_file(md_file, pdf_out)

    assert ok is True
    assert "✔ PDF 발간 완료" in msg
