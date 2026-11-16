import io
import os
from zipfile import ZipFile

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link, Text
from pypdf.generic import RectangleObject

from forge_pdf.document import Document, read_pdf, serialize
from test_document import fixture_pdf, texts


def linked_document():
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.add_outline_item("Page three", 2)
    writer.add_annotation(0, Link(rect=(10, 10, 50, 50), target_page_index=2))
    return Document(serialize(writer))


def test_reorder_keeps_links_and_bookmarks_and_can_be_undone():
    doc = linked_document()
    original = doc.data
    doc.reorder_pages([2, 0, 1])
    reader = read_pdf(doc.data)
    assert "Original page 3" in reader.pages[0].extract_text()
    assert reader.get_destination_page_number(reader.outline[0]) == 0
    assert (
        reader.pages[1]["/Annots"][0].get_object()["/Dest"][0] == reader.pages[0].indirect_reference
    )
    doc.undo()
    assert doc.data == original


def test_subset_keeps_internal_links_to_retained_pages(tmp_path):
    doc = linked_document()
    dest = tmp_path / "subset.pdf"
    doc.export_pages([2, 0], dest)
    reader = PdfReader(dest)
    assert (
        reader.pages[1]["/Annots"][0].get_object()["/Dest"][0] == reader.pages[0].indirect_reference
    )


def test_batch_delete_is_transactional():
    doc = Document(fixture_pdf())
    original = doc.data
    with pytest.raises(ValueError, match="at least one page"):
        doc.delete_pages([0, 1, 2])
    assert not doc.undo_stack and doc.data == original
    doc.delete_pages([2, 0])
    assert doc.count == 1 and "Original page 2" in texts(doc)[0]
    doc.undo()
    assert doc.data == original


def test_insert_password_opened_subset_in_order_and_protect_its_source(tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.encrypt("synthetic-password", algorithm="AES-256")
    source = tmp_path / "protected.pdf"
    original = serialize(writer)
    source.write_bytes(original)
    doc = Document(fixture_pdf(1))
    doc.insert_pages(Document.open(source, "synthetic-password"), [2, 0], 1)
    assert [text.splitlines()[0] for text in texts(doc)] == [
        "Original page 1",
        "Original page 3",
        "Original page 1",
    ]
    doc.undo()
    with pytest.raises(ValueError, match="different name"):
        doc.save_copy(source, overwrite=True)
    assert source.read_bytes() == original


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_header_uses_visible_crop_and_keeps_native_notes(rotation):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(2)))
    page = writer.pages[0]
    page.cropbox = RectangleObject((20, 30, 380, 490))
    page.rotate(rotation)
    writer.add_annotation(0, Text(rect=(60, 70, 100, 110), text="Synthetic note"))
    doc = Document(serialize(writer))
    before = doc.render(0)
    doc.mark_pages([0], "header", "Test header", 12)
    delta = ImageChops.difference(before, doc.render(0)).getbbox()
    assert delta is not None and delta[3] < 40
    assert doc.notes(0) == ["Synthetic note"]
    assert "Test header" in texts(doc)[0] and "Test header" not in texts(doc)[1]


def test_numbering_follows_requested_order_and_fit_failure_rolls_back():
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.pages[1].cropbox = RectangleObject((0, 0, 40, 40))
    doc = Document(serialize(writer))
    original = doc.data
    with pytest.raises(ValueError, match="page 2"):
        doc.mark_pages([0, 1], "watermark", "Synthetic draft", 24)
    assert doc.data == original and not doc.undo_stack
    doc.mark_pages([2, 0], "numbers", start=9)
    assert texts(doc)[2].splitlines()[-1] == "9"
    assert texts(doc)[0].splitlines()[-1] == "10"
    doc.undo()
    assert doc.data == original


@pytest.mark.parametrize("kind", ["pdf", "png", "jpg"])
def test_archives_follow_order_and_leave_document_alone(tmp_path, kind):
    doc = Document(fixture_pdf())
    doc.rotate(2)
    original = doc.data, doc.saved, doc.undo_stack.copy()
    destination = tmp_path / "pages.zip"
    doc.export_page_archive([2, 0], destination, kind)
    with ZipFile(destination) as archive:
        assert archive.namelist() == [f"001-page-3.{kind}", f"002-page-1.{kind}"]
        data = archive.read(archive.namelist()[0])
        if kind == "pdf":
            assert "Original page 3" in read_pdf(data).pages[0].extract_text()
        else:
            with Image.open(io.BytesIO(data)) as image:
                assert image.size == (1000, 800)
                assert image.format == ("PNG" if kind == "png" else "JPEG")
    assert (doc.data, doc.saved, doc.undo_stack) == original


def test_text_export_is_utf8_in_requested_order_and_refuses_source_hardlink(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(fixture_pdf())
    doc = Document.open(source)
    doc.overlay(0, "text", (40, 200, 40, 200), "Résumé")
    destination = tmp_path / "text.txt"
    doc.export_text([2, 0], destination)
    text = destination.read_text(encoding="utf-8")
    assert text.index("--- Page 3 ---") < text.index("--- Page 1 ---") < text.index("Résumé")
    alias = tmp_path / "alias.txt"
    os.link(source, alias)
    with pytest.raises(ValueError, match="different name"):
        doc.export_text([0], alias, overwrite=True)
    assert source.read_bytes().startswith(b"%PDF")
