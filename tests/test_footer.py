import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document, serialize


def footer_pdf():
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(300, 400))
    for _ in range(4):
        canvas.setFillColorRGB(0.1, 0.2, 0.3)
        canvas.rect(0, 0, 300, 400, fill=1, stroke=0)
        canvas.showPage()
    canvas.save()
    writer = PdfWriter(clone_from=io.BytesIO(buffer.getvalue()))
    for index, page in enumerate(writer.pages):
        page.cropbox = RectangleObject((10, 10, 290, 390))
        page.rotate(index * 90)
    return serialize(writer)


@pytest.mark.parametrize("height", [5, 25])
def test_footer_matches_visible_bottom_on_all_rotations_and_one_undo(height, tmp_path):
    original = footer_pdf()
    doc = Document(original)
    doc.clear_footer(height)
    assert len(doc.undo_stack) == 1
    target = tmp_path / "footers.pdf"
    doc.save_copy(target)
    reopened = Document.open(target)
    for index in range(doc.count):
        image = reopened.render(index)
        x = image.width // 2
        assert image.getpixel((x, image.height - height)) == (255, 255, 255)
        assert image.getpixel((x, image.height - 1)) == (255, 255, 255)
        assert image.getpixel((x, image.height - height - 2)) != (255, 255, 255)
    doc.undo()
    assert doc.data == original
    doc.redo()
    assert doc.data == reopened.data


def test_footer_failure_is_transactional(monkeypatch):
    doc = Document(footer_pdf())
    original = doc.data
    overlay = Document.overlay

    def fail_second(self, index, *args, **kwargs):
        if index == 1:
            raise ValueError("Simulated unsupported page")
        return overlay(self, index, *args, **kwargs)

    monkeypatch.setattr(Document, "overlay", fail_second)
    with pytest.raises(ValueError, match="Simulated"):
        doc.clear_footer()
    assert doc.data == original
    assert not doc.undo_stack


def test_footer_invalid_height_does_not_edit():
    doc = Document(footer_pdf())
    for height in (0, -5, 2.5, True):
        with pytest.raises(ValueError):
            doc.clear_footer(height)
    assert not doc.dirty
