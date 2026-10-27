"""Offline OCR export with a synthetic scan and an app-scoped test engine."""

import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document


def make_scan():
    image = Image.new("RGB", (1500, 400), "white")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = (
        ImageFont.truetype(str(font_path), 72) if font_path.exists() else ImageFont.load_default()
    )
    draw.text((80, 120), "FORGE OCR SAMPLE", fill="black", font=font)
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(750, 200))
    canvas.drawImage(ImageReader(image), 0, 0, width=750, height=200)
    canvas.save()
    image.close()
    return stream.getvalue()


def test_ocr_searchable_image_copy(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    original = make_scan()
    document = Document(original)
    target = tmp_path / "ocr.pdf"
    document.export_searchable_image_copy(target, ocr_dir=Path(bundle))
    reader = PdfReader(target)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text().upper()
    assert "FORGE" in text and "SAMPLE" in text
    assert document.data == original
    assert not reader.is_encrypted
    with pytest.raises(ValueError, match="original"):
        document.sources.add(target.resolve())
        document.export_searchable_image_copy(target, overwrite=True, ocr_dir=Path(bundle))


def test_ocr_missing_bundle_keeps_existing_target(tmp_path):
    document = Document(make_scan())
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    with pytest.raises(ValueError, match="unavailable"):
        document.export_searchable_image_copy(target, overwrite=True, ocr_dir=tmp_path / "missing")
    assert target.read_bytes() == b"keep"
