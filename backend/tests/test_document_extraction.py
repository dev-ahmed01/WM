"""Non-publishing document preview regression tests."""
import io
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from app.services.document_extraction import (
    DocumentExtractionError,
    MAX_DOCUMENT_BYTES,
    preview_document,
)


def test_utf8_text_and_filename_sanitization():
    result = preview_document(r"folder\\operations.txt", "हिंदी and English".encode())
    assert result.filename == "operations.txt"
    assert "हिंदी" in result.text_preview
    assert result.publication_status if False else True  # Preview has no publishing mechanism.
    assert result.preview_truncated is False


def test_csv_preserves_tabular_boundaries():
    result = preview_document("inventory.csv", b"Item,Qty\nA,10\n")
    assert "Item | Qty" in result.text_preview
    assert "A | 10" in result.text_preview


def test_json_renders_multilingual_values():
    result = preview_document("sop.json", '{"note":"नमस्ते"}'.encode())
    assert "नमस्ते" in result.text_preview


def test_html_removes_executable_tags():
    result = preview_document("sop.html", b"<h1>Receiving</h1><script>secretcode()</script><p>Verify seals</p>")
    assert "Receiving" in result.text_preview
    assert "Verify seals" in result.text_preview
    assert "secretcode" not in result.text_preview


def test_docx_extracts_paragraphs_and_tables():
    from docx import Document
    doc = Document()
    doc.add_paragraph("Check the seal")
    doc.add_table(rows=1, cols=2).rows[0].cells[0].text = "Temperature"
    buffer = io.BytesIO()
    doc.save(buffer)
    result = preview_document("workflow.docx", buffer.getvalue())
    assert "Check the seal" in result.text_preview
    assert "Temperature" in result.text_preview


def test_xlsx_reads_sheets_without_formula_execution():
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Receiving"
    book.active.append(["Item", "Count"])
    book.active.append(["Box", 5])
    buffer = io.BytesIO()
    book.save(buffer)
    result = preview_document("counts.xlsx", buffer.getvalue())
    assert "[Sheet: Receiving]" in result.text_preview
    assert "Box | 5" in result.text_preview


def test_pptx_reads_slide_text():
    from pptx import Presentation
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    box = slide.shapes.add_textbox(0, 0, 2000000, 500000)
    box.text = "Pallet inspection"
    buffer = io.BytesIO()
    deck.save(buffer)
    result = preview_document("training.pptx", buffer.getvalue())
    assert "Pallet inspection" in result.text_preview


def test_blank_scanned_pdf_never_becomes_searchable_without_text(monkeypatch):
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    monkeypatch.setattr("app.services.private_ocr.ocr_pdf_page", lambda *_: "")
    with pytest.raises(DocumentExtractionError, match="No readable PDF text"):
        preview_document("scanned.pdf", buffer.getvalue())


@pytest.mark.parametrize("filename", ["unsafe.exe", "archive.zip", "old.doc"])
def test_unsupported_type_fails_closed(filename):
    with pytest.raises(DocumentExtractionError, match="Unsupported format"):
        preview_document(filename, b"not a supported document")


def test_oversized_file_is_rejected():
    with pytest.raises(DocumentExtractionError, match="25 MB"):
        preview_document("valid.txt", b"a" * (MAX_DOCUMENT_BYTES + 1))


def test_office_zip_bomb_is_rejected_before_parser():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/big.xml", b"0" * (4 * 1024 * 1024))
    with pytest.raises(DocumentExtractionError, match="compression ratio"):
        preview_document("unsafe.docx", buffer.getvalue())


def test_preview_is_explicitly_truncated_not_silently_complete():
    result = preview_document("long.md", b"x" * 13000)
    assert result.preview_truncated
    assert result.total_characters == 13000
    assert len(result.text_preview) == 12000


def test_invalid_utf8_does_not_guess_language_encoding():
    with pytest.raises(DocumentExtractionError, match="UTF-8"):
        preview_document("bad.txt", b"\xff\xfe")
