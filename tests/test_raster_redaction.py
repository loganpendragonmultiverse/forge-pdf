"""Prove the rasterized export contains only rebuilt page images."""

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document, serialize


def secret_pdf(rotation):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    canvas.drawString(40, 440, "TOPSECRET synthetic text")
    canvas.setFillColorRGB(1, 0, 0)
    canvas.rect(40, 350, 100, 60, fill=1)
    canvas.acroForm.textfield(name="secret_field", x=40, y=260, width=150, height=20)
    canvas.showPage()
    canvas.save()
    writer = PdfWriter(clone_from=io.BytesIO(stream.getvalue()))
    writer.pages[0].cropbox = RectangleObject((20, 30, 380, 480))
    writer.pages[0].rotate(rotation)
    writer.add_metadata({"/Title": "TOPSECRET title"})
    writer.add_outline_item("TOPSECRET bookmark", 0)
    writer.add_attachment("TOPSECRET.txt", b"TOPSECRET attachment")
    return serialize(writer)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rasterized_redaction_removes_source_objects(rotation, tmp_path):
    doc = Document(secret_pdf(rotation))
    doc.add_note(0, 20, 20, "TOPSECRET note")
    before = doc.data
    width, height = doc.size(0)
    box = (20, 20, 100, 100)
    destination = tmp_path / f"redacted-{rotation}.pdf"
    doc.export_raster_redacted(0, box, destination)
    assert doc.data == before
    output = destination.read_bytes()
    assert b"TOPSECRET" not in output
    reader = PdfReader(io.BytesIO(output))
    assert len(reader.pages) == 1
    assert not reader.pages[0].extract_text()
    assert not reader.pages[0].get("/Annots")
    assert not reader.get_fields()
    assert not reader.outline
    assert "TOPSECRET" not in str(reader.metadata)
    assert "/Names" not in reader.trailer["/Root"]
    assert "/XObject" in reader.pages[0]["/Resources"]
    reopened = Document.open(destination)
    assert reopened.size(0) == (width, height)
    assert reopened.render(0).getpixel((60, 60)) == (0, 0, 0)


def test_rasterized_export_rejects_invalid_box_and_original(tmp_path):
    source = tmp_path / "source.pdf"
    original = secret_pdf(0)
    source.write_bytes(original)
    doc = Document.open(source)
    with pytest.raises(ValueError, match="rectangle"):
        doc.export_raster_redacted(0, (-1, 0, 100, 100), tmp_path / "bad.pdf")
    with pytest.raises(ValueError, match="different name"):
        doc.export_raster_redacted(0, (0, 0, 100, 100), source, overwrite=True)
    assert source.read_bytes() == original
