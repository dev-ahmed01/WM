# WorkMate private OCR — operations and acceptance

## Supported inputs

- Scanned or hybrid PDF files: pypdf extracts selectable text per page; only low-text pages are rendered by PDFium and sent to local Tesseract.
- Single-frame PNG, JPEG, TIFF and WEBP scans. The decoder verifies the actual image format matches the extension; broken or multi-frame images are rejected.
- Tesseract is provisioned with eng+hin inside infra/docker/backend.Dockerfile. Processing is local; no third-party OCR endpoint is used.

## Runtime limits and config

Default config: OCR_ENABLED=true, OCR_LANGUAGES=eng+hin, OCR_PDF_DPI=150, OCR_MAX_PAGES=12, OCR_MAX_IMAGE_PIXELS=16000000, OCR_TIMEOUT_SECONDS=20.
The global 25 MB input cap, 200-page selectable-PDF limit, 1,000,000-character extracted-text cap and 12,000-character UI preview still apply.
OCR consumes CPU: configure gateway rate limiting and concurrent-work quotas before broad production rollout.
Set OCR_ENABLED=false to reject scans requiring OCR, rather than silently importing incomplete content.
The admin-only GET /api/v1/knowledge/ocr-status endpoint reports whether the language packs and engine are present.

## Review process

1. Knowledge Studio > Add knowledge > Read document: upload the scan.
2. Inspect OCR warnings and verify safety-critical terminology, names, quantities and tables against the original.
3. Save as a draft reference document. Review its extracted text in the reference library and approve only after manual verification.
4. Employees may then search approved excerpts and use Copilot's read-only Ask documents mode. OCR cannot publish an OWD workflow graph.

## Known limitations

- OCR text does not preserve table coordinates, merged cells, diagram content, handwriting, or form layout.
- Original source files remain in the Snowflake stage; the current review UI shows extracted text rather than an aligned source-image viewer.
- Pages with fewer than 25 selectable alphanumeric glyphs invoke OCR, including blank pages; more than 12 such pages causes rejection. Split long scans.
- Real English OCR is tested in CI. Hindi language-pack installation and a mocked Hindi extraction path are checked, but Hindi recognition accuracy and mixed-script error rates have not been measured.
- Third-party parsers still execute inside the web-service process. Production parser isolation and stronger admission controls are required before accepting untrusted public uploads.

## Smoke checks

Run 'tesseract --list-langs' and 'PYTHONPATH=backend python -m pytest -q backend/tests/test_private_ocr.py backend/tests/test_document_extraction.py' in an environment with OCR dependencies installed.
Snowflake migration 19_reference_knowledge.sql from the parent PR must be applied before saving reference drafts.