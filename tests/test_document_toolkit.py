import io
import os

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link, Text
from pypdf.generic import RectangleObject

from forge_pdf.document import DRAW_TOOLS, Document, serialize
from test_desktop_features import editor as editor
from test_desktop_features import point, wait_preview
from test_document import fixture_pdf, texts


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_matches_visible_region_and_reset_restores_media(rotation):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(1)))
    page = writer.pages[0]
    page.cropbox = RectangleObject((10, 20, 380, 480))
    page.rotate(rotation)
    doc = Document(serialize(writer))
    original = doc.data
    before = doc.render(0)
    w, h = before.size
    doc.crop_pages([0], (30, 35, 40, 80), margins=True)
    expected = before.crop((30, 35, w - 40, h - 80))
    assert ImageChops.difference(doc.render(0), expected).getbbox() is None
    assert "Original page 1" in doc.page_text(0)
    doc.reset_crops([0])
    assert doc.render(0).size == ((500, 400) if rotation % 180 else (400, 500))
    doc.undo()
    doc.undo()
    assert doc.data == original


def test_crop_failure_does_not_commit_any_page():
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(2)))
    writer.pages[1].cropbox = RectangleObject((0, 0, 35, 35))
    doc = Document(serialize(writer))
    original = doc.data
    with pytest.raises(ValueError, match="page 2"):
        doc.crop_pages([0, 1], (20, 20, 20, 20), margins=True)
    assert doc.data == original and not doc.undo_stack


def test_create_blank_and_import_images_with_exif_and_protected_sources(tmp_path):
    blank = Document.blank(2, "Legal", landscape=True)
    assert blank.dirty and blank.count == 2 and blank.size(0) == (1008, 612)
    wide = tmp_path / "wide.png"
    rotated = tmp_path / "rotated.jpg"
    Image.new("RGBA", (120, 60), (220, 0, 0, 255)).save(wide)
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (120, 60), (0, 170, 0)).save(rotated, exif=exif)
    image_pdf = Document.from_images([wide, rotated])
    assert image_pdf.dirty and image_pdf.size(0) == (792, 612)
    assert image_pdf.size(1) == (612, 792)
    assert image_pdf.render(0).getpixel((396, 306))[0] > 200
    assert image_pdf.render(1).getpixel((306, 396))[1] > 150
    blank.insert_pages(image_pdf, [1, 0], 1)
    assert blank.count == 4 and blank.size(1) == (612, 792)
    alias = tmp_path / "alias.pdf"
    os.link(rotated, alias)
    with pytest.raises(ValueError, match="different name"):
        blank.save_copy(alias, overwrite=True)


def test_duplicate_ranges_in_order_and_undo():
    doc = Document(fixture_pdf())
    initial = doc.data
    doc.duplicate_pages([2, 0], 1)
    assert [text.splitlines()[0] for text in texts(doc)] == [
        "Original page 1",
        "Original page 3",
        "Original page 1",
        "Original page 2",
        "Original page 3",
    ]
    doc.rotate(1)
    assert PdfReader(io.BytesIO(doc.data)).pages[4].rotation == 0
    doc.undo()
    doc.undo()
    assert doc.data == initial


@pytest.mark.parametrize("kind", DRAW_TOOLS)
def test_drawing_visible_with_retained_annotation_and_undo(kind):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf(1)))
    writer.pages[0].rotate(90)
    writer.add_annotation(0, Text(rect=(60, 70, 100, 110), text="Native note"))
    doc = Document(serialize(writer))
    original = doc.data
    end_y = 20 if kind in ("line", "arrow") else 70
    doc.overlay(0, kind, (20, 20, 80, end_y), color="#00b000", stroke=4)
    image = doc.render(0)
    assert any(g > 120 and r < 100 for r, g, b in image.crop((12, 12, 85, 75)).get_flattened_data())
    assert doc.notes(0) == ["Native note"]
    doc.undo()
    assert doc.data == original


@pytest.mark.parametrize("kind", ["png", "jpg"])
def test_direct_image_exports_have_correct_format_and_keep_history(tmp_path, kind):
    doc = Document(fixture_pdf())
    doc.rotate(1)
    snapshot = doc.data, doc.saved, doc.undo_stack.copy()
    target = tmp_path / f"page.{kind}"
    doc.export_page_image(1, target, kind)
    with Image.open(target) as image:
        assert image.format == ("PNG" if kind == "png" else "JPEG")
        assert image.size == (1000, 800)
    assert (doc.data, doc.saved, doc.undo_stack) == snapshot


def test_compression_retains_appearance_links_and_bookmarks(tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(fixture_pdf()))
    writer.add_annotation(0, Link(rect=(40, 40, 70, 70), url="https://example.test/resource"))
    writer.add_outline_item("Second page", 1)
    doc = Document(serialize(writer))
    assert doc.external_links() == [(1, "https://example.test/resource")]
    before = doc.data
    out = tmp_path / "compressed.pdf"
    old, new = doc.export_compressed(out)
    result = Document.open(out)
    assert old >= new == out.stat().st_size
    assert result.external_links() == doc.external_links()
    assert result.bookmarks() == doc.bookmarks()
    assert result.page_text(0) == doc.page_text(0)
    assert ImageChops.difference(doc.render(0), result.render(0)).getbbox() is None
    assert doc.data == before and not doc.undo_stack


def test_page_menu_groups_clipboard_drawing_and_view_controls(editor):
    app, errors = editor
    menu = app.build_page_menu(app)
    assert menu.index("end") == 7
    assert all(menu.type(index) == "cascade" for index in range(8))
    assert [menu.entrycget(index, "label") for index in range(8)] == [
        "Create PDF",
        "Organize pages",
        "Crop",
        "Marks and drawing",
        "Forms and annotations",
        "Export and OCR",
        "View and navigate",
        "Document and bookmarks",
    ]
    assert app.doc.page_text(0).strip()
    app.copy_page_text()
    assert app.clipboard_get().strip() == app.doc.page_text(0).strip()
    data = app.doc.data
    app.set_mode("arrow")
    app.press(point(app, 20, 20))
    app.drag(point(app, 80, 20))
    assert app.canvas.type(app.canvas.find_withtag("selection")[0]) == "line"
    app.release(point(app, 80, 20))
    wait_preview(app)
    assert len(app.doc.undo_stack) == 1
    app.history(False)
    assert app.doc.data == data
    app.set_fit("height")
    app.set_preview_tone("inverted")
    wait_preview(app)
    assert app.fit == "height" and app.preview_tone == "inverted"
    assert app.doc.data == data and not errors
