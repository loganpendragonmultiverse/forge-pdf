"""Native PDF highlight annotations on synthetic rotated and cropped pages."""

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, RectangleObject

from forge_pdf.document import Document

from test_professional_workflows import form_pdf


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_native_highlight_survives_reopen_and_is_undoable(rotation, tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(form_pdf()))
    writer.pages[0].cropbox = RectangleObject((20, 30, 380, 480))
    writer.pages[0].rotate(rotation)
    stream = io.BytesIO()
    writer.write(stream)
    doc = Document(stream.getvalue())
    before = doc.render(0, 1).getpixel((75, 65))
    doc.add_native_highlight(0, (40, 40, 110, 90))
    assert doc.highlight_annotation_count(0) == 1
    reader = PdfReader(io.BytesIO(doc.data))
    assert "customer" in (reader.get_fields() or {})
    highlight = next(
        ref.get_object()
        for ref in reader.pages[0]["/Annots"]
        if ref.get_object().get("/Subtype") == "/Highlight"
    )
    assert len(highlight["/QuadPoints"]) == 8
    assert all(0 <= float(value) <= 1 for value in highlight["/C"])
    target = tmp_path / f"highlight-{rotation}.pdf"
    doc.save_copy(target)
    assert Document.open(target).highlight_annotation_count(0) == 1
    image = doc.render(0, 1)
    assert image.getpixel((75, 65)) != before
    doc.delete_native_highlight(0, 0)
    assert doc.highlight_annotation_count(0) == 0
    doc.undo()
    assert doc.highlight_annotation_count(0) == 1


def test_native_highlight_rejects_invalid_rectangles_and_indices():
    doc = Document(form_pdf())
    with pytest.raises(ValueError, match="complete highlight"):
        doc.add_native_highlight(0, (-1, 0, 30, 30))
    with pytest.raises(ValueError, match="finite"):
        doc.add_native_highlight(0, (0, 0, float("nan"), 30))
    with pytest.raises(ValueError, match="Choose a native highlight"):
        doc.delete_native_highlight(0, 0)


def test_recolor_native_highlight_preserves_annotation_and_undo(tmp_path):
    doc = Document(form_pdf())
    doc.add_native_highlight(0, (40, 40, 110, 90))
    original = doc.data
    before = doc.render(0, 1)
    doc.recolor_native_highlight(0, 0, "blue")
    after = doc.render(0, 1)
    try:
        assert before.tobytes() != after.tobytes()
    finally:
        before.close()
        after.close()
    target = tmp_path / "recolored.pdf"
    doc.save_copy(target)
    reopened = PdfReader(target)
    highlight = next(
        ref.get_object()
        for ref in reopened.pages[0]["/Annots"]
        if ref.get_object().get("/Subtype") == "/Highlight"
    )
    assert [round(float(value), 3) for value in highlight["/C"]] == [0.565, 0.792, 0.976]
    assert "customer" in (reopened.get_fields() or {})
    doc.undo()
    assert doc.data == original
    with pytest.raises(ValueError, match="green, blue or pink"):
        doc.recolor_native_highlight(0, 0, "orange")
    with pytest.raises(ValueError, match="Choose a native highlight"):
        doc.recolor_native_highlight(0, 4, "green")


def test_recolor_rejects_custom_appearance_without_changing_document():
    doc = Document(form_pdf())
    doc.add_native_highlight(0, (40, 40, 110, 90))
    writer = PdfWriter(clone_from=io.BytesIO(doc.data))
    highlight = next(
        ref.get_object()
        for ref in writer.pages[0]["/Annots"]
        if ref.get_object().get("/Subtype") == "/Highlight"
    )
    highlight[NameObject("/AP")] = DictionaryObject()
    stream = io.BytesIO()
    writer.write(stream)
    custom = Document(stream.getvalue())
    original = custom.data
    with pytest.raises(ValueError, match="custom appearance"):
        custom.recolor_native_highlight(0, 0, "pink")
    assert custom.data == original
