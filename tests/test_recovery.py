"""Atomic output and bounded opt-in recovery use synthetic PDFs only."""

import io
import zipfile

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document, write_copy_bytes
from forge_pdf.enhancements import open_session, save_session


def fixture_pdf():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(300, 300))
    canvas.drawString(30, 200, "Synthetic current data")
    canvas.save()
    return stream.getvalue()


def test_new_file_is_published_only_after_complete_temp_write(tmp_path, monkeypatch):
    target = tmp_path / "new.pdf"
    real_link = __import__("os").link

    def inspect_then_link(source, destination):
        assert not target.exists()
        assert open(source, "rb").read() == b"complete data"
        real_link(source, destination)

    monkeypatch.setattr("forge_pdf.document.os.link", inspect_then_link)
    write_copy_bytes(target, b"complete data")
    assert target.read_bytes() == b"complete data"
    assert not list(tmp_path.glob(".forge-pdf-*"))


def test_failed_publish_leaves_no_partial_destination(tmp_path, monkeypatch):
    target = tmp_path / "new.pdf"

    def fail(*args):
        raise PermissionError("simulated link failure")

    monkeypatch.setattr("forge_pdf.document.os.link", fail)
    with pytest.raises(PermissionError, match="simulated"):
        write_copy_bytes(target, b"contents")
    assert not target.exists()
    assert not list(tmp_path.glob(".forge-pdf-*"))


def test_recovery_snapshot_excludes_undo_and_reopens(tmp_path):
    doc = Document(fixture_pdf())
    doc.add_bookmark("Current", 0)
    assert doc.undo_stack
    target = tmp_path / "recovery.forgepdf"
    save_session(doc, target, 0, 1.0, include_history=False)
    with zipfile.ZipFile(target) as archive:
        assert archive.namelist() == ["session.json", "current.pdf"]
    restored, page, zoom = open_session(target)
    assert restored.data == doc.data
    assert restored.undo_stack == []
    assert (page, zoom) == (0, 1.0)
    doc.add_bookmark("Later", 0)
    save_session(doc, target, 0, 1.0, overwrite=True, include_history=False)
    restored, _, _ = open_session(target)
    assert restored.data == doc.data


def test_password_opened_document_is_identified(tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.encrypt("synthetic-password", algorithm="AES-256")
    source = tmp_path / "protected.pdf"
    with source.open("wb") as output:
        writer.write(output)
    assert Document.open(source, "synthetic-password").opened_encrypted
