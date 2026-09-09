import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document, serialize


def annotated_pdf():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    canvas.drawString(50, 400, "Clickable text")
    canvas.linkURL("https://example.org", (40, 385, 170, 420), relative=0)
    canvas.acroForm.textfield(
        name="sample", value="Visible field", x=40, y=280, width=200, height=30, forceBorder=True
    )
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_form_appearance_whiteout_with_links_rotation_crop(rotation, tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(annotated_pdf()))
    writer.pages[0].cropbox = RectangleObject((10, 10, 390, 490))
    writer.pages[0].rotate(rotation)
    doc = Document(serialize(writer))
    before_size = doc.size(0)
    doc.overlay(0, "whiteout", (0, 0, *before_size))
    image = doc.render(0)
    assert image.crop((2, 2, image.width - 2, image.height - 2)).getextrema() == ((255, 255),) * 3
    reader = PdfReader(io.BytesIO(doc.data))
    assert any(a.get_object()["/Subtype"] == "/Link" for a in reader.pages[0]["/Annots"])
    assert doc.size(0) == before_size
    target = tmp_path / "forms-edited.pdf"
    doc.save_copy(target)
    assert Document.open(target).render(0).getpixel((50, 50)) == (255, 255, 255)
    doc.undo()
    assert doc.data == serialize(writer)


def test_link_only_edit_preserves_link_geometry():
    writer = PdfWriter()
    writer.add_blank_page(400, 500)
    writer.add_annotation(0, Link(rect=(20, 30, 100, 60), url="https://example.org"))
    doc = Document(serialize(writer))
    doc.overlay(0, "whiteout", (20, 20, 200, 80))
    page = PdfReader(io.BytesIO(doc.data)).pages[0]
    assert list(page["/Annots"][0].get_object()["/Rect"]) == [20, 30, 100, 60]


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-128", "AES-256"])
def test_page_utilities_and_password(tmp_path, algorithm):
    writer = PdfWriter()
    writer.add_blank_page(400, 500)
    writer.encrypt("owner-test", algorithm=algorithm)
    source = tmp_path / "protected.pdf"
    source.write_bytes(serialize(writer))
    with pytest.raises(ValueError, match="Password"):
        Document.open(source)
    doc = Document.open(source, "owner-test")
    doc.duplicate(0)
    doc.overlay(0, "text", (20, 20, 0, 0), "Only first copy")
    reader = PdfReader(io.BytesIO(doc.data))
    assert "Only first copy" not in reader.pages[1].extract_text()
    doc.insert_blank(1)
    assert doc.count == 3
    target = tmp_path / "page.pdf"
    doc.export_page(0, target)
    assert Document.open(target).count == 1
    assert PdfReader(source).is_encrypted
