"""Release-level checks for print, OCR, revision and archive workflows."""

import io
import os
from pathlib import Path
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from forge_pdf.document import Document, serialize
from forge_pdf.production import bookmark_groups, compare_text, export_tiff, print_layout
from test_document import fixture_pdf
from test_ocr import make_scan


@pytest.mark.parametrize(
    "layout,count,sheets",
    [("two-up", 3, 2), ("four-up", 5, 2), ("booklet", 1, 2), ("booklet", 5, 4)],
)
def test_print_sheet_sizes_and_preserved_input(tmp_path, layout, count, sheets):
    doc = Document(fixture_pdf(count))
    before = doc.data
    out = tmp_path / "out.pdf"
    print_layout(doc, list(range(count)), layout, "Letter", out)
    new = PdfReader(out)
    assert len(new.pages) == sheets
    expected = (612, 792) if layout == "four-up" else (792, 612)
    assert all((p.mediabox.width, p.mediabox.height) == expected for p in new.pages)
    assert doc.data == before and not doc.undo_stack


@pytest.mark.parametrize("gray", [True, False])
def test_tiff_frame_order(tmp_path, gray):
    doc = Document(fixture_pdf(3))
    path = tmp_path / "out.tif"
    export_tiff(doc, [2, 0], gray, path)
    with Image.open(path) as image:
        assert image.n_frames == 2
        for idx, num in enumerate([2, 0]):
            image.seek(idx)
            assert image.mode == ("L" if gray else "RGB")
            with doc.render(num, 1.5) as original:
                assert image.tobytes() == original.convert(image.mode).tobytes()


def test_bookmark_sections_and_revision_report(tmp_path):
    doc = Document(fixture_pdf(4))
    doc.add_bookmark("Later", 2)
    doc.add_bookmark("Same page", 2)
    assert bookmark_groups(doc) == [[0, 1], [2, 3]]
    path = tmp_path / "changes.txt"
    compare_text(doc, Document(fixture_pdf(3)), path)
    assert "Page 4 (removed)" in path.read_text()
    assert "1 page positions differ" in path.read_text()


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_mixed_ocr_preserves_text_and_scan_pixels(tmp_path, angle):
    bundle = os.environ.get("FORGE_PDF_TEST_OCR_DIR")
    if not bundle:
        pytest.skip("Bundled OCR engine required")
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(fixture_pdf(1))))
    w.append(PdfReader(io.BytesIO(make_scan())))
    page = w.pages[1]
    page.cropbox.left = 8
    page.rotate(angle)
    w.add_blank_page(400, 500)
    doc = Document(serialize(w))
    out = tmp_path / "mixed.pdf"
    progress = []
    doc.export_searchable_layer_copy(
        out, ocr_dir=Path(bundle), mixed=True, progress=lambda i, n: progress.append(i)
    )
    result = Document.open(out)
    assert result.page_text(0) == doc.page_text(0)
    if angle == 0:
        assert "FORGE" in result.page_text(1).upper()
    assert progress == [0, 1, 2, 3] and result.count == 3
    for i in range(3):
        with result.render(i) as after, doc.render(i) as before:
            assert before.size == after.size and before.tobytes() == after.tobytes()


def test_ocr_original_blocked_before_worker(tmp_path, monkeypatch):
    from forge_pdf.app import Editor

    app = Editor()
    try:
        path = tmp_path / "original.pdf"
        path.write_bytes(make_scan())
        app.doc = Document.open(path)
        app.path = path
        alias = tmp_path / "alias.pdf"
        os.link(path, alias)
        (tmp_path / "Support/ocr/tessdata").mkdir(parents=True)
        (tmp_path / "Support/ocr/tessdata/eng.traineddata").touch()
        monkeypatch.setattr("forge_pdf.app.sys.executable", str(tmp_path / "python.exe"))
        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", lambda *a, **k: True)
        monkeypatch.setattr("forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(alias))
        errors = []
        monkeypatch.setattr(app, "error", lambda e: errors.append(str(e)))
        assert not app.export_ocr() and "different name" in errors[0]
    finally:
        app.destroy()
