import csv
import io
import os
from zipfile import ZipFile

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link, Text

from forge_pdf.document import Document, serialize
from forge_pdf.publishing import (
    export_contact_sheet,
    export_rendered_archive,
    export_report,
    export_split,
    split_groups,
    text_document,
    text_file_document,
    worksheet,
)
from test_desktop_features import editor as editor
from test_document import fixture_pdf


def test_plain_text_wraps_long_tokens_and_paginates():
    word = "abcdefghij" * 70
    doc = text_document("Résumé\n" + word + "\n" + "\n".join(f"Line {n}" for n in range(90)))
    assert doc.dirty and doc.count >= 3
    content = "".join(doc.page_text(index).replace("\n", "") for index in range(doc.count))
    assert "Résumé" + word in content
    assert "Line 89" in content


def test_utf8_source_identity_is_retained_after_insertion(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("Café notes", encoding="utf-8-sig")
    incoming = text_file_document(source)
    doc = Document(fixture_pdf())
    doc.insert_pages(incoming, [0], 1)
    assert "Café notes" in doc.page_text(1)
    alias = tmp_path / "text-alias.pdf"
    os.link(source, alias)
    with pytest.raises(ValueError, match="different name"):
        doc.save_copy(alias, overwrite=True)
    assert source.read_text(encoding="utf-8-sig") == "Café notes"


@pytest.mark.parametrize("pattern", ["Ruled", "Grid", "Dots"])
def test_worksheets_render_on_each_requested_page(pattern):
    doc = worksheet(pattern, 2, "A4", True)
    assert doc.count == 2 and doc.dirty
    assert doc.size(0)[0] > doc.size(0)[1]
    a, b = doc.render(0), doc.render(1)
    assert ImageChops.difference(a, Image.new("RGB", a.size, "white")).getbbox()
    assert ImageChops.difference(a, b).getbbox() is None


def test_split_archives_partition_pages_and_preserve_links_within_a_chunk(tmp_path):
    assert split_groups(5, every=2) == [[0, 1], [2, 3], [4]]
    with pytest.raises(ValueError):
        split_groups(5, starts=(4, 2))
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(5)))
    writer.add_annotation(0, Link(rect=(10, 10, 20, 20), target_page_index=1))
    doc = Document(serialize(writer))
    before = doc.data
    path = tmp_path / "split.zip"
    export_split(doc, split_groups(5, starts=(3, 5)), path)
    with ZipFile(path) as zip_file:
        assert zip_file.namelist() == [
            "001-pages-1-2.pdf",
            "002-pages-3-4.pdf",
            "003-pages-5-5.pdf",
        ]
        first = PdfReader(io.BytesIO(zip_file.read(zip_file.namelist()[0])))
        assert (
            first.pages[0]["/Annots"][0].get_object()["/Dest"][0]
            == first.pages[1].indirect_reference
        )
    assert doc.data == before and not doc.undo_stack


def test_contact_sheet_order_and_pagination(tmp_path):
    doc = Document(fixture_pdf(7))
    path = tmp_path / "thumbnails.pdf"
    export_contact_sheet(doc, [6, 1, 2, 3, 4, 5, 0], 2, path)
    reader = PdfReader(path)
    assert len(reader.pages) == 2
    first_text = reader.pages[0].extract_text()
    assert first_text.index("Page 7") < first_text.index("Page 2")
    assert len(reader.pages[0].images) >= 1
    assert "Page 1" in reader.pages[1].extract_text()


@pytest.mark.parametrize("kind", ["png", "jpg"])
def test_archive_settings_set_grayscale_dimensions_and_dpi(tmp_path, kind):
    doc = Document(fixture_pdf())
    path = tmp_path / "images.zip"
    export_rendered_archive(doc, [2, 0], kind, 108, True, 65, path)
    with ZipFile(path) as zipped:
        assert zipped.namelist() == [f"001-page-3.{kind}", f"002-page-1.{kind}"]
        with Image.open(io.BytesIO(zipped.read(zipped.namelist()[0]))) as image:
            assert image.mode == "L" and image.size == (600, 750)
            assert image.info["dpi"][0] == pytest.approx(108, abs=0.1)


def test_review_reports_include_exact_pages_and_neutralize_spreadsheet_formulas(tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.add_annotation(1, Text(rect=(10, 10, 20, 20), text='=HYPERLINK("https://example.test")'))
    writer.add_annotation(0, Link(rect=(10, 10, 20, 20), url="https://example.test"))
    writer.add_outline_item("Part two", 1)
    doc = Document(serialize(writer))
    rows = {}
    for kind in ("pages", "links", "notes", "bookmarks"):
        path = tmp_path / f"{kind}.csv"
        export_report(doc, kind, path)
        with path.open(encoding="utf-8-sig", newline="") as report:
            rows[kind] = list(csv.reader(report))
    assert rows["pages"][1][0:2] == ["1", "1"]
    assert rows["links"][1] == ["1", "https://example.test"]
    assert rows["notes"][1][0:2] == ["2", "1"]
    assert rows["notes"][1][2].startswith("'=")
    assert rows["bookmarks"][1] == ["2", "0", "Part two"]


def test_publish_menu_split_command_creates_archive(editor, tmp_path, monkeypatch):
    app, errors = editor
    path = tmp_path / "chunks.zip"
    monkeypatch.setattr("forge_pdf.app.simpledialog.askstring", lambda *args, **kw: "2")
    monkeypatch.setattr("forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(path))
    menu = app.build_page_menu(app)
    exports = app.nametowidget(menu.entrycget(5, "menu"))
    batch = app.nametowidget(exports.entrycget(1, "menu"))
    assert batch.entrycget(1, "label") == "Split at specific page numbers…"
    batch.invoke(1)
    with ZipFile(path) as archive:
        assert len(archive.namelist()) == 2
    assert not errors and not app.doc.dirty
