import io
import os

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Text
from pypdf.generic import RectangleObject

from forge_pdf.document import Document, parse_page_ranges, serialize
from test_document import fixture_pdf


@pytest.mark.parametrize(
    "selection",
    [
        "",
        " ",
        "1,",
        ",1",
        "0",
        "-1",
        "6",
        "3-2",
        "1-6",
        "1.0",
        "1;2",
        "all",
        "1,1",
        "1-3,3",
        "1--2",
    ],
)
def test_reject_malformed_outside_and_duplicate_ranges(selection):
    with pytest.raises(ValueError):
        parse_page_ranges(selection, 5)


def test_range_order_and_count():
    assert parse_page_ranges(" 5, 1, 3 - 4 ", 5) == [4, 0, 2, 3]
    assert parse_page_ranges("1,3-5", 5) == [0, 2, 3, 4]


def test_export_preserves_order_crop_rotation_annotation_and_history(tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(5)))
    writer.pages[2].cropbox = RectangleObject((20, 30, 380, 480))
    writer.pages[2].rotate(90)
    writer.add_annotation(2, Text(rect=(60, 70, 100, 110), text="Synthetic annotation"))
    doc = Document(serialize(writer))
    doc.rotate(0)
    doc.undo()
    before = (doc.data, doc.saved, doc.undo_stack.copy(), doc.redo_stack.copy(), doc.dirty)
    output = tmp_path / "subset.pdf"
    doc.export_pages(parse_page_ranges("5,3,1", 5), output)
    reader = PdfReader(output)
    assert len(reader.pages) == 3
    assert [
        "Original page 5" in reader.pages[0].extract_text(),
        "Original page 3" in reader.pages[1].extract_text(),
        "Original page 1" in reader.pages[2].extract_text(),
    ] == [True] * 3
    assert reader.pages[1].rotation == 90
    assert tuple(reader.pages[1].cropbox) == (20, 30, 380, 480)
    assert reader.pages[1]["/Annots"][0].get_object()["/Contents"] == "Synthetic annotation"
    assert (doc.data, doc.saved, doc.undo_stack, doc.redo_stack, doc.dirty) == before
    doc.redo()
    dirty_before = (doc.data, doc.saved, doc.undo_stack.copy(), doc.redo_stack.copy())
    doc.export_pages([0], tmp_path / "dirty.pdf")
    assert doc.dirty
    assert (doc.data, doc.saved, doc.undo_stack, doc.redo_stack) == dirty_before


def test_export_refuses_original_aliases_and_preserves_failed_output(tmp_path, monkeypatch):
    source = tmp_path / "original.pdf"
    source.write_bytes(fixture_pdf())
    doc = Document.open(source)
    aliases = [source]
    hardlink = tmp_path / "hard.pdf"
    os.link(source, hardlink)
    aliases.append(hardlink)
    try:
        symlink = tmp_path / "sym.pdf"
        symlink.symlink_to(source)
        aliases.append(symlink)
    except OSError:
        pass
    for alias in aliases:
        with pytest.raises(ValueError, match="different name"):
            doc.export_pages([0, 1], alias, overwrite=True)
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        doc.export_pages([0], target)

    def failed_replace(*args):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", failed_replace)
    with pytest.raises(OSError, match="synthetic replace"):
        doc.export_pages([0], target, overwrite=True)
    assert target.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".forge-pdf-*"))
    assert source.read_bytes() == fixture_pdf() or Document.open(source).count == 3


@pytest.mark.parametrize("indices", [[], [0, 0], [-1], [3], [True], ["1"]])
def test_invalid_export_indices(indices, tmp_path):
    with pytest.raises(ValueError):
        Document(fixture_pdf()).export_pages(indices, tmp_path / "invalid.pdf")
    assert not (tmp_path / "invalid.pdf").exists()
