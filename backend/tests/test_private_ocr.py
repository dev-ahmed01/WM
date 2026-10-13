"""Private English/Hindi OCR input hardening, page handling and a real smoke test."""
from __future__ import annotations

import io
import shutil
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter

from app.services.document_extraction import DocumentExtractionError, extract_document, preview_document
from app.services.private_ocr import OcrError, ocr_capability, ocr_raster


def _image_bytes(format="PNG", text="RECEIVING AREA"):
    image = Image.new("RGB", (1050, 160), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 58)
    except OSError:
        font = ImageFont.load_default()
    draw.text((35, 33), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    image.close()
    return buffer.getvalue()


def _pdf_pages(count):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=220, height=280)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("name,image_format", [("proof.png", "PNG"), ("proof.jpeg", "JPEG"), ("proof.tiff", "TIFF"), ("proof.webp", "WEBP")])
def test_image_format_extracts_with_local_bilingual_engine(monkeypatch, name, image_format):
    called = []
    def fake_engine(image):
        called.append((image.size, image.mode))
        return "माल प्राप्त करें / Check receiving seal"
    monkeypatch.setattr("app.services.private_ocr._run_tesseract", fake_engine)
    document = extract_document(name, _image_bytes(image_format))
    assert called == [((1050, 160), "RGB")]
    assert "माल" in document.content
    assert any("OCR" in warning for warning in document.warnings)


def test_spoofed_image_extension_is_not_trusted():
    with pytest.raises(DocumentExtractionError, match="do not match"):
        preview_document("receiving.jpg", _image_bytes("PNG"))


def test_broken_image_is_rejected():
    with pytest.raises(DocumentExtractionError, match="damaged"):
        preview_document("receiving.png", b"malformed image data")


def test_inflated_pixel_count_is_blocked_before_render(monkeypatch):
    monkeypatch.setattr("app.services.private_ocr.settings.OCR_MAX_IMAGE_PIXELS", 10)
    with pytest.raises(DocumentExtractionError, match="pixel limit"):
        preview_document("receiving.png", _image_bytes())


def test_ocr_disabled_cannot_save_scan_as_reference(monkeypatch):
    monkeypatch.setattr("app.services.private_ocr.settings.OCR_ENABLED", False)
    with pytest.raises(DocumentExtractionError, match="disabled"):
        extract_document("receipt.jpg", _image_bytes("JPEG"))


def test_pdf_mixed_page_content_keeps_page_anchors(monkeypatch):
    raw = _pdf_pages(2)
    visited = []
    def fake_page(_raw, page_index):
        visited.append(page_index)
        return "पेज स्कैन " + str(page_index) + " - Verify the invoice and seal"
    monkeypatch.setattr("app.services.private_ocr.ocr_pdf_page", fake_page)
    doc = extract_document("receiving.pdf", raw)
    assert "[Page 1]\n" in doc.content
    assert "[Page 2]\n" in doc.content
    assert len(visited) == 2
    assert "OCR processed 2 page(s)" in doc.warnings[0]
    assert "पेज स्कैन" in doc.content


def test_pdf_scan_limit_blocks_truncation_without_publishing(monkeypatch):
    monkeypatch.setattr("app.services.document_extraction.settings.OCR_MAX_PAGES", 1)
    monkeypatch.setattr("app.services.private_ocr.ocr_pdf_page", lambda *args: "Read this scan carefully")
    with pytest.raises(DocumentExtractionError, match="more than 1 pages"):
        extract_document("many.pdf", _pdf_pages(2))


def test_pdf_renderer_rejects_untrusted_page_index():
    from app.services.private_ocr import ocr_pdf_page
    with pytest.raises(OcrError, match="out of range"):
        ocr_pdf_page(_pdf_pages(1), 9)


def test_language_pack_missing_fails_closed(monkeypatch):
    monkeypatch.setattr("app.services.private_ocr.shutil.which", lambda _: "/usr/bin/tesseract")
    import pytesseract
    monkeypatch.setattr(pytesseract, "get_languages", lambda **_kwargs: ["eng"])
    with pytest.raises(OcrError, match="language data is missing"):
        from app.services.private_ocr import _run_tesseract
        _run_tesseract(Image.new("RGB", (50, 50), "white"))


def test_ocr_capability_reports_local_only(monkeypatch):
    monkeypatch.setattr("app.services.private_ocr.shutil.which", lambda _: None)
    status = ocr_capability()
    assert status["ready"] is False
    assert status["reason"] == "engine_missing"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="local Tesseract absent")
def test_real_private_ocr_english_smoke():
    import pytesseract
    if not {"eng", "hin"}.issubset(set(pytesseract.get_languages(config=""))):
        pytest.skip("English+Hindi Tesseract language data not installed")
    result = extract_document("scanned.png", _image_bytes(text="RECEIVING AREA"))
    assert "RECEIVING" in result.content.upper()
    assert "AREA" in result.content.upper()
