"""Offline OCR export with a synthetic scan and an app-scoped test engine."""

import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from PIL import ImageChops
from pypdf import PdfReader, PdfWriter
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


def test_ocr_language_and_cancellation_preserve_target(tmp_path):
    document = Document(make_scan())
    bundle = tmp_path / "engine"
    (bundle / "tessdata").mkdir(parents=True)
    (bundle / "tesseract.exe").write_bytes(b"placeholder")
    (bundle / "tessdata" / "eng.traineddata").write_bytes(b"placeholder")
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    with pytest.raises(ValueError, match="language code"):
        document.export_searchable_image_copy(
            target, overwrite=True, ocr_dir=bundle, language="../../bad"
        )
    with pytest.raises(ValueError, match="cancelled"):
        document.export_searchable_image_copy(
            target, overwrite=True, ocr_dir=bundle, cancelled=lambda: True
        )
    assert target.read_bytes() == b"keep"


def test_ocr_progress_and_worker(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    import time

    from forge_pdf.workers import NativeWorker

    original = make_scan()
    destination = tmp_path / "worker.pdf"
    worker = NativeWorker("ocr")
    future = worker.submit(
        original,
        {
            "path": str(destination),
            "overwrite": False,
            "language": "eng",
            "ocr_dir": bundle,
        },
    )
    try:
        deadline = time.monotonic() + 30
        progress = []
        while not future.done() and time.monotonic() < deadline:
            progress.append(future.progress)
            time.sleep(0.02)
        assert future.done()
        assert future.result() is True
        assert any(total == 1 for _, total in progress)
        assert "FORGE" in PdfReader(destination).pages[0].extract_text().upper()
    finally:
        worker.shutdown()


def test_ocr_cancel_after_first_page_keeps_existing_file(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    page = PdfReader(io.BytesIO(make_scan())).pages[0]
    writer = PdfWriter()
    writer.add_page(page)
    writer.add_page(page)
    stream = io.BytesIO()
    writer.write(stream)
    document = Document(stream.getvalue())
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    progress = []
    with pytest.raises(ValueError, match="cancelled"):
        document.export_searchable_image_copy(
            target,
            overwrite=True,
            ocr_dir=Path(bundle),
            progress=lambda done, total: progress.append((done, total)),
            cancelled=lambda: (1, 2) in progress,
        )
    assert progress[:2] == [(0, 2), (1, 2)]
    assert target.read_bytes() == b"keep"


def test_ocr_text_layer_preserves_page_and_navigation(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    writer = PdfWriter(clone_from=io.BytesIO(make_scan()))
    writer.add_outline_item("Scan", 0)
    writer.add_uri(0, "https://example.com", (10, 10, 100, 30))
    writer.add_metadata({"/Title": "Synthetic scan"})
    stream = io.BytesIO()
    writer.write(stream)
    original = stream.getvalue()
    document = Document(original)
    target = tmp_path / "preserved.pdf"
    document.export_searchable_layer_copy(target, ocr_dir=Path(bundle))
    reader = PdfReader(target)
    assert "FORGE OCR SAMPLE" in reader.pages[0].extract_text().upper()
    assert reader.metadata.title == "Synthetic scan"
    assert reader.outline[0].title == "Scan"
    assert reader.pages[0]["/Annots"][0].get_object()["/A"]["/URI"] == "https://example.com"
    assert reader.pages[0]["/Resources"]["/XObject"]
    before = document.render(0, 1)
    after = Document(target.read_bytes()).render(0, 1)
    try:
        assert ImageChops.difference(before, after).getbbox() is None
    finally:
        before.close()
        after.close()
    assert document.data == original


def test_ocr_text_layer_rejects_complex_pages_and_preserves_target(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    for mutation in ("rotate", "crop", "text", "form"):
        writer = PdfWriter(clone_from=io.BytesIO(make_scan()))
        if mutation == "rotate":
            writer.pages[0].rotate(90)
        elif mutation == "crop":
            writer.pages[0].cropbox.right -= 10
        elif mutation == "text":
            from reportlab.pdfgen.canvas import Canvas

            text = io.BytesIO()
            canvas = Canvas(text, pagesize=(750, 200))
            canvas.drawString(20, 20, "already searchable")
            canvas.save()
            writer.pages[0].merge_page(PdfReader(text).pages[0])
        else:
            from pypdf.generic import DictionaryObject, NameObject

            writer._root_object[NameObject("/AcroForm")] = DictionaryObject()
        stream = io.BytesIO()
        writer.write(stream)
        with pytest.raises(ValueError):
            Document(stream.getvalue()).export_searchable_layer_copy(
                target, overwrite=True, ocr_dir=Path(bundle)
            )
        assert target.read_bytes() == b"keep"


def test_ocr_text_layer_cancel_keeps_existing_target(tmp_path):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("App-scoped OCR engine not present in this environment")
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    with pytest.raises(ValueError, match="cancelled"):
        Document(make_scan()).export_searchable_layer_copy(
            target, overwrite=True, ocr_dir=Path(bundle), cancelled=lambda: True
        )
    assert target.read_bytes() == b"keep"
