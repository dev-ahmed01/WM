"""Private OCR for raster images and scanned PDF pages.

Tesseract runs as a local subprocess (no external OCR API). All inputs have
strict byte, pixel, PDF page and execution limits; documents stay untrusted.
Only the extracted text goes to admin review, never to the OWD publisher.
"""
from __future__ import annotations

import io
import shutil
import warnings

from app.core.config import settings


class OcrError(ValueError):
    """Sanitized local OCR failure suitable for an administrator."""


RASTER_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"})
_ACTUAL_FORMATS = {
    ".png": frozenset({"PNG"}),
    ".jpg": frozenset({"JPEG"}),
    ".jpeg": frozenset({"JPEG"}),
    ".tif": frozenset({"TIFF"}),
    ".tiff": frozenset({"TIFF"}),
    ".webp": frozenset({"WEBP"}),
}


def _checked_image(image):
    from PIL import Image, ImageOps
    if image.width < 1 or image.height < 1:
        raise OcrError("The image has invalid dimensions.")
    if image.width * image.height > settings.OCR_MAX_IMAGE_PIXELS:
        raise OcrError("Image exceeds the safe pixel limit; reduce the resolution.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        return image
    except (Image.DecompressionBombWarning, Image.DecompressionBombError, MemoryError) as exc:
        raise OcrError("Image exceeds OCR decompression or memory safety limits.") from exc


def _run_tesseract(image) -> str:
    """Never fall back silently to a wrong language pack."""
    if not settings.OCR_ENABLED:
        raise OcrError("Private OCR is disabled for this deployment.")
    if not shutil.which("tesseract"):
        raise OcrError("Local OCR engine is unavailable. Install Tesseract with English and Hindi data.")
    try:
        import pytesseract
        installed = set(pytesseract.get_languages(config=""))
        requested = settings.OCR_LANGUAGES.split("+")
        if not set(requested).issubset(installed):
            raise OcrError("OCR language data is missing. Install the English and Hindi traineddata.")
        text = pytesseract.image_to_string(
            image, lang=settings.OCR_LANGUAGES,
            config="--psm 3", timeout=settings.OCR_TIMEOUT_SECONDS,
        )
        return str(text or "").strip()
    except OcrError:
        raise
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError) as exc:
        # No raw engine paths or sensitive content in public HTTP errors.
        raise OcrError("OCR could not read this image. Check scan quality and local OCR setup.") from exc


def ocr_raster(raw: bytes, extension: str) -> str:
    """Read a single image, rejecting spoofed extensions and multi-frame files."""
    if not settings.OCR_ENABLED:
        raise OcrError("Private OCR is disabled for this deployment.")
    if extension not in RASTER_EXTENSIONS:
        raise OcrError("Unsupported image type for OCR.")
    try:
        from PIL import Image, UnidentifiedImageError
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in _ACTUAL_FORMATS[extension]:
                raise OcrError("Image contents do not match the filename extension.")
            if getattr(original, "n_frames", 1) != 1:
                raise OcrError("Multi-page image files are not supported. Export individual images.")
            checked = _checked_image(original)
            try:
                return _run_tesseract(checked)
            finally:
                if checked is not original:
                    checked.close()
    except OcrError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, MemoryError) as exc:
        raise OcrError("Image is damaged or uses an unsupported encoding.") from exc


def ocr_pdf_page(raw: bytes, page_index: int) -> str:
    """Rasterize one requested PDF page locally, never the full document at once."""
    if not settings.OCR_ENABLED:
        raise OcrError("Private OCR is disabled for this deployment.")
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(raw)
        try:
            if page_index < 0 or page_index >= len(pdf):
                raise OcrError("Requested OCR PDF page is out of range.")
            page = pdf[page_index]
            try:
                width, height = page.get_size()
                scale = settings.OCR_PDF_DPI / 72.0
                if width <= 0 or height <= 0 or width * height * scale * scale > settings.OCR_MAX_IMAGE_PIXELS:
                    raise OcrError("PDF page exceeds the safe rasterization limit.")
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil()
                    try:
                        checked = _checked_image(image)
                        try:
                            return _run_tesseract(checked)
                        finally:
                            if checked is not image:
                                checked.close()
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            pdf.close()
    except OcrError:
        raise
    except (ImportError, OSError, ValueError, RuntimeError, MemoryError) as exc:
        raise OcrError("PDF page could not be rendered for private OCR.") from exc


def ocr_capability() -> dict[str, object]:
    """Non-sensitive, local status only; does not upload a sample."""
    if not settings.OCR_ENABLED:
        return {"enabled": False, "ready": False, "languages": [], "reason": "disabled"}
    if not shutil.which("tesseract"):
        return {"enabled": True, "ready": False, "languages": [], "reason": "engine_missing"}
    try:
        import pytesseract
        available = set(pytesseract.get_languages(config=""))
        required = set(settings.OCR_LANGUAGES.split("+"))
        return {
            "enabled": True, "ready": required <= available,
            "languages": sorted(required & available),
            "reason": "ready" if required <= available else "language_data_missing",
        }
    except Exception:
        return {"enabled": True, "ready": False, "languages": [], "reason": "engine_unavailable"}
