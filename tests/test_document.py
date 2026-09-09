import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document, serialize


def fixture_pdf(pages=3):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    for n in range(pages):
        canvas.setFont("Helvetica", 18)
        canvas.drawString(40, 440, f"Original page {n + 1}")
        canvas.setFillColorRGB(0.1, 0.2, 0.3)
        canvas.rect(40, 300, 150, 70, fill=1)
        canvas.showPage()
    canvas.save()
    return stream.getvalue()


def texts(doc):
    return [page.extract_text() for page in PdfReader(io.BytesIO(doc.data)).pages]


def test_reorder_delete_merge_and_restore(tmp_path):
    doc = Document(fixture_pdf())
    original = doc.data
    doc.move(0, 2)
    assert ["3" in texts(doc)[1], "1" in texts(doc)[2]] == [True, True]
    doc.delete(1)
    assert doc.count == 2
    extra = tmp_path / "extra.pdf"
    extra.write_bytes(fixture_pdf(1))
    doc.append(extra)
    assert doc.count == 3
    doc.undo()
    doc.undo()
    doc.undo()
    assert doc.data == original
    doc.redo()
    assert "1" in texts(doc)[2]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_marks_align_after_rotation_and_crop(rotation):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(1)))
    writer.pages[0].cropbox = RectangleObject((20, 30, 380, 480))
    writer.pages[0].rotate(rotation)
    doc = Document(serialize(writer))
    width, height = doc.size(0)
    doc.overlay(0, "text", (35, 35, 35, 35), "New text", 16)
    assert "New text" in texts(doc)[0]
    assert doc.size(0) == (width, height)
    doc.overlay(0, "highlight", (100, 100, 160, 150))
    image = doc.render(0)
    assert image.getpixel((125, 120)) != (255, 255, 255)
    doc.overlay(0, "whiteout", (90, 90, 170, 160))
    assert doc.render(0).getpixel((125, 120)) == (255, 255, 255)


def test_whiteout_is_visual_not_redaction_and_undoable():
    doc = Document(fixture_pdf(1))
    original = doc.data
    doc.overlay(0, "whiteout", (0, 0, 400, 200))
    assert "Original page 1" in texts(doc)[0]
    assert doc.render(0).crop((0, 0, 400, 199)).getextrema() == ((255, 255),) * 3
    doc.undo()
    assert doc.data == original
    doc.redo()
    assert doc.data != original


def test_save_source_protection_and_reopen(tmp_path):
    source = tmp_path / "original.pdf"
    original = fixture_pdf()
    source.write_bytes(original)
    doc = Document.open(source)
    doc.rotate(0)
    with pytest.raises(ValueError, match="different name"):
        doc.save_copy(source, overwrite=True)
    copy = tmp_path / "edited.pdf"
    doc.save_copy(copy)
    assert Document.open(copy).size(0) == (500, 400)
    assert source.read_bytes() == original
    assert not doc.dirty
    with pytest.raises(FileExistsError):
        doc.save_copy(copy)
    assert not list(tmp_path.glob(".forge-pdf-*"))


def test_failed_edits_leave_history_unchanged():
    doc = Document(fixture_pdf(1))
    original = doc.data
    with pytest.raises(ValueError):
        doc.delete(0)
    with pytest.raises(ValueError, match="does not fit"):
        doc.overlay(0, "text", (390, 40, 0, 0), "This will not fit")
    with pytest.raises(ValueError, match="Western European"):
        doc.overlay(0, "text", (20, 20, 0, 0), "你好")
    assert doc.data == original
    assert not doc.undo_stack


def test_rejects_encrypted_and_invalid():
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(1)))
    writer.encrypt("test-password")
    with pytest.raises(ValueError, match="Password"):
        Document(serialize(writer))
    with pytest.raises(PdfReadError):
        Document(b"not a PDF")


def test_undo_after_save_and_branch(tmp_path):
    doc = Document(fixture_pdf(1))
    doc.rotate(0)
    doc.save_copy(tmp_path / "copy.pdf")
    doc.undo()
    assert doc.dirty
    doc.redo()
    assert not doc.dirty
    doc.undo()
    doc.overlay(0, "whiteout", (20, 20, 60, 60))
    assert not doc.redo_stack


def test_save_failure_preserves_existing_destination(tmp_path, monkeypatch):
    doc = Document(fixture_pdf(1))
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep me")

    def fail(*args):
        raise PermissionError("locked")

    monkeypatch.setattr("forge_pdf.document.os.replace", fail)
    with pytest.raises(PermissionError):
        doc.save_copy(target, overwrite=True)
    assert target.read_bytes() == b"keep me"
    assert not list(tmp_path.glob(".forge-pdf-*"))
