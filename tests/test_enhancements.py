import io
import json
import os
import zipfile
from pathlib import Path

import pytest
import reportlab
from PIL import Image
from pypdf import PdfReader
from pypdf.generic import RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document
from forge_pdf.enhancements import (
    open_session,
    save_session,
    session_payload,
    stamp_image,
    text_font,
)


def sample(tmp_path):
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(300, 200))
    canvas.drawString(30, 150, "Literal .[x] and SEARCH")
    canvas.showPage()
    canvas.drawString(30, 150, "search again")
    canvas.save()
    source = tmp_path / "source.pdf"
    source.write_bytes(stream.getvalue())
    return Document.open(source), source


def font_path():
    return Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


def test_search_is_literal_bounded_and_read_only(tmp_path):
    document, source = sample(tmp_path)
    before = source.read_bytes()
    assert len(document.search("search")) == 2
    assert document.search(".[x]")[0]["page"] == 0
    assert document.search("not present") == []
    assert len(document.search("search", limit=1)) == 1
    assert not document.dirty and not document.undo_stack and source.read_bytes() == before
    for query in ("", " " * 10, "x" * 257):
        with pytest.raises(ValueError):
            document.search(query)
    with pytest.raises(ValueError):
        document.search("search", limit=True)


def test_search_case_word_boundaries_and_offsets():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(300, 200))
    canvas.drawString(30, 150, "Alpha alphabet alpha")
    canvas.save()
    document = Document(stream.getvalue())
    assert len(document.search("alpha")) == 3
    assert len(document.search("alpha", whole_word=True)) == 2
    match = document.search("Alpha", case_sensitive=True, whole_word=True)
    assert len(match) == 1 and match[0]["start"] == 0 and match[0]["end"] == 5
    with pytest.raises(ValueError, match="options"):
        document.search("Alpha", case_sensitive=1)


def test_inserted_local_font_glyphs_survive_export_and_undo(tmp_path):
    document, source = sample(tmp_path)
    before = document.data
    document.overlay(0, "text", (25, 50, 25, 50), "Café Ω", 16, font_path=font_path())
    assert "Café Ω" in PdfReader(io.BytesIO(document.data)).pages[0].extract_text()
    target = tmp_path / "font-copy.pdf"
    document.save_copy(target)
    assert "Café Ω" in PdfReader(target).pages[0].extract_text()
    assert source.read_bytes() == before
    document.undo()
    assert document.data == before
    with pytest.raises(ValueError, match="glyph"):
        text_font(chr(0x10FFFF), font_path())
    with pytest.raises(ValueError, match="TrueType"):
        text_font("Ω", None)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_image_stamp_uses_visible_rotated_crop_coordinates(tmp_path, rotation):
    document, source = sample(tmp_path)
    writer = document.writer()
    writer.pages[0].cropbox = RectangleObject((20, 20, 280, 180))
    writer.pages[0].rotate(rotation)
    document.commit(writer)
    before = document.data
    image = tmp_path / "stamp.png"
    Image.new("RGBA", (20, 20), (0, 220, 0, 255)).save(image)
    image_before = image.read_bytes()
    document.overlay(0, "image", (20, 20, 60, 60), image_path=image_before)
    pixel = document.render(0).getpixel((40, 40))
    assert pixel[1] > 180 and pixel[0] < 30 and pixel[2] < 30
    assert image.read_bytes() == image_before
    output = tmp_path / "stamped.pdf"
    document.save_copy(output)
    reopened = Document.open(output)
    assert reopened.render(0).getpixel((40, 40)) == pixel
    document.undo()
    assert document.data == before
    assert source.exists()


def test_image_validation_and_transactional_failure(tmp_path):
    document, _ = sample(tmp_path)
    before = document.data
    gif = tmp_path / "unsupported.gif"
    Image.new("RGB", (10, 10)).save(gif)
    with pytest.raises(ValueError, match="PNG"):
        stamp_image(gif)
    png = tmp_path / "stamp.png"
    Image.new("RGB", (10, 10)).save(png)
    with pytest.raises(ValueError, match="inside"):
        document.overlay(0, "image", (-1, 0, 10, 10), image_path=png)
    assert document.data == before and not document.undo_stack


def test_session_restores_embedded_edits_history_and_source_protection(tmp_path):
    document, source = sample(tmp_path)
    original = source.read_bytes()
    document.rotate(0)
    edited = document.data
    session = tmp_path / "notes.forgepdf"
    save_session(document, session, 1, 0.75)
    assert document.dirty
    restored, page, zoom = open_session(session)
    assert restored.data == edited and restored.dirty and (page, zoom) == (1, 0.75)
    assert source.read_bytes() == original
    restored.undo()
    assert restored.data == original
    with pytest.raises(ValueError, match="original"):
        restored.save_copy(source, overwrite=True)
    alias = tmp_path / "original-alias.pdf"
    os.link(source, alias)
    with pytest.raises(ValueError, match="original"):
        restored.save_copy(alias, overwrite=True)
    with pytest.raises(FileExistsError):
        save_session(document, session, 0, 1)
    assert source.read_bytes() == original


def rewrite_session(tmp_path, data, alter):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {item.filename: archive.read(item) for item in archive.infolist()}
    metadata = json.loads(files["session.json"])
    alter(metadata, files)
    files["session.json"] = json.dumps(metadata).encode()
    path = tmp_path / "changed.forgepdf"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


@pytest.mark.parametrize(
    "alter",
    [
        lambda metadata, files: metadata.update(history=True),
        lambda metadata, files: metadata.update(page=-1),
        lambda metadata, files: metadata.update(zoom=float("inf")),
        lambda metadata, files: metadata.update(sources=["../outside.pdf"]),
        lambda metadata, files: metadata.update(
            sources=[str(Path.cwd()) + "/bad" + chr(0) + ".pdf"]
        ),
        lambda metadata, files: metadata.update(source_identities=[[True, 1]]),
        lambda metadata, files: files.update({"../outside.pdf": b"not extracted"}),
        lambda metadata, files: metadata.update(session_version=2),
    ],
)
def test_session_rejects_invalid_metadata_or_unexpected_members(tmp_path, alter):
    document, _ = sample(tmp_path)
    path = rewrite_session(tmp_path, session_payload(document, 0, 1), alter)
    with pytest.raises(ValueError):
        open_session(path)
    assert not (tmp_path.parent / "outside.pdf").exists()


def test_session_loading_never_opens_recorded_external_paths(tmp_path, monkeypatch):
    document, _ = sample(tmp_path)
    data = session_payload(document, 0, 1)
    outside = tmp_path / "does-not-exist" / "original.pdf"
    path = rewrite_session(
        tmp_path, data, lambda metadata, files: metadata.update(sources=[str(outside)])
    )
    restored, _, _ = open_session(path)
    assert outside in restored.sources
    assert not outside.exists()
    assert restored.data == document.data


def test_preflight_reports_objects_and_actual_limits(tmp_path):
    document, _ = sample(tmp_path)
    report = document.export_preflight()
    assert report["pages"] == 2 and report["links"] == 0
    assert any("not secure redaction" in warning for warning in report["warnings"])
    assert any("unencrypted" in warning for warning in report["warnings"])
