"""Synthetic fixtures for local professional PDF workflows."""

import io

import pytest
from pypdf import PdfReader
from pypdf import PdfWriter
from pypdf.generic import NameObject, RectangleObject
from reportlab.pdfgen.canvas import Canvas

from forge_pdf.document import Document


def form_pdf():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    canvas.drawString(40, 440, "Synthetic form")
    canvas.acroForm.textfield(name="customer", x=40, y=380, width=200, height=25)
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def controls_pdf():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    canvas.acroForm.checkbox(name="agree", x=40, y=380, checked=False)
    canvas.acroForm.choice(
        name="tier",
        options=["Bronze", "Silver", "Gold"],
        value="Bronze",
        x=40,
        y=300,
        width=120,
        height=20,
    )
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def radio_pdf():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(400, 500))
    canvas.acroForm.radio(name="delivery", value="Email", selected=True, x=40, y=380)
    canvas.acroForm.radio(name="delivery", value="Print", selected=False, x=90, y=380)
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def test_fill_text_field_and_undo():
    doc = Document(form_pdf())
    original = doc.data
    assert doc.text_fields() == {"customer": ""}
    doc.fill_text_field("customer", "Ada Example")
    reader = PdfReader(io.BytesIO(doc.data))
    assert reader.get_fields()["customer"].get("/V") == "Ada Example"
    with pytest.raises(ValueError, match="editable"):
        doc.fill_text_field("missing", "x")
    doc.undo()
    assert doc.data == original


def test_metadata_bookmark_and_encrypted_copy(tmp_path):
    doc = Document(form_pdf())
    doc.set_metadata(
        {"/Title": "Example", "/Author": "Tester", "/Subject": "QA", "/Keywords": "sample"}
    )
    doc.add_bookmark("Form", 0)
    assert doc.metadata()["/Title"] == "Example"
    reader = PdfReader(io.BytesIO(doc.data))
    assert reader.outline[0].title == "Form"
    target = tmp_path / "protected.pdf"
    with pytest.raises(ValueError, match="nonempty"):
        doc.save_copy(target, password="")
    assert not target.exists()
    doc.save_copy(target, password="synthetic-secret")
    protected = PdfReader(target)
    assert protected.is_encrypted
    assert protected.decrypt("wrong") == 0
    assert protected.decrypt("synthetic-secret")
    assert protected.metadata.title == "Example"
    assert protected.get_fields()["customer"]
    assert not doc.dirty


def test_choice_and_checkbox_are_undoable():
    doc = Document(controls_pdf())
    assert doc.choice_fields() == {"tier": ("Bronze", ["Bronze", "Silver", "Gold"])}
    assert doc.checkbox_fields() == {"agree": False}
    doc.fill_choice_field("tier", "Gold")
    doc.set_checkbox("agree", True)
    reader = PdfReader(io.BytesIO(doc.data))
    assert reader.get_fields()["tier"].get("/V") == "Gold"
    assert reader.get_fields()["agree"].get("/V") == "/Yes"
    assert reader.pages[0]["/Annots"][0].get_object().get("/AS") == "/Yes"
    with pytest.raises(ValueError, match="listed option"):
        doc.fill_choice_field("tier", "Diamond")
    doc.undo()
    assert doc.checkbox_fields() == {"agree": False}


def test_custom_checkbox_state_updates_appearance_and_undo():
    writer = PdfWriter(clone_from=io.BytesIO(controls_pdf()))
    checkbox = writer.pages[0]["/Annots"][0].get_object()
    appearances = checkbox["/AP"].get_object()["/N"].get_object()
    appearances[NameObject("/Agreed")] = appearances.pop(NameObject("/Yes"))
    stream = io.BytesIO()
    writer.write(stream)
    doc = Document(stream.getvalue())
    original = doc.data
    assert doc.checkbox_fields() == {"agree": False}
    before = doc.render(0, 1)
    doc.set_checkbox("agree", True)
    after = doc.render(0, 1)
    try:
        assert before.tobytes() != after.tobytes()
    finally:
        before.close()
        after.close()
    reopened = PdfReader(io.BytesIO(doc.data))
    assert reopened.get_fields()["agree"]["/V"] == "/Agreed"
    assert reopened.pages[0]["/Annots"][0].get_object()["/AS"] == "/Agreed"
    assert doc.checkbox_fields() == {"agree": True}
    doc.undo()
    assert doc.data == original
    doc.set_checkbox("agree", True)
    doc.set_checkbox("agree", False)
    assert doc.checkbox_fields() == {"agree": False}


def test_ambiguous_checkbox_appearance_is_not_offered():
    writer = PdfWriter(clone_from=io.BytesIO(controls_pdf()))
    checkbox = writer.pages[0]["/Annots"][0].get_object()
    appearances = checkbox["/AP"].get_object()["/N"].get_object()
    appearances[NameObject("/Maybe")] = appearances["/Yes"]
    stream = io.BytesIO()
    writer.write(stream)
    doc = Document(stream.getvalue())
    assert doc.checkbox_fields() == {}
    with pytest.raises(ValueError, match="single-state"):
        doc.set_checkbox("agree", True)


def test_radio_group_updates_all_widgets_and_undo():
    doc = Document(radio_pdf())
    original = doc.data
    assert doc.radio_fields() == {"delivery": ("/Email", ["/Email", "/Print"])}
    before = doc.render(0, 1)
    doc.select_radio("delivery", "/Print")
    after = doc.render(0, 1)
    try:
        assert before.tobytes() != after.tobytes()
    finally:
        before.close()
        after.close()
    reader = PdfReader(io.BytesIO(doc.data))
    assert reader.get_fields()["delivery"]["/V"] == "/Print"
    assert [ref.get_object()["/AS"] for ref in reader.pages[0]["/Annots"]] == ["/Off", "/Print"]
    assert doc.radio_fields()["delivery"][0] == "/Print"
    with pytest.raises(ValueError, match="listed option"):
        doc.select_radio("delivery", "/Missing")
    doc.undo()
    assert doc.data == original


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_native_notes_survive_reopen_and_can_be_deleted(rotation, tmp_path):
    writer = PdfWriter(clone_from=io.BytesIO(form_pdf()))
    writer.pages[0].cropbox = RectangleObject((20, 30, 380, 480))
    writer.pages[0].rotate(rotation)
    stream = io.BytesIO()
    writer.write(stream)
    doc = Document(stream.getvalue())
    doc.add_note(0, 40, 40, "Review this line")
    assert doc.notes(0) == ["Review this line"]
    reader = PdfReader(io.BytesIO(doc.data))
    assert "customer" in (reader.get_fields() or {})
    note = next(
        ref.get_object()
        for ref in reader.pages[0]["/Annots"]
        if ref.get_object().get("/Subtype") == "/Text"
    )
    expected = {
        0: (60, 416, 84, 440),
        90: (60, 70, 84, 94),
        180: (316, 70, 340, 94),
        270: (316, 416, 340, 440),
    }
    assert tuple(float(value) for value in note["/Rect"]) == expected[rotation]
    assert doc.all_notes() == [{"page": 0, "index": 0, "text": "Review this line"}]
    doc.update_note(0, 0, "Revised note")
    assert doc.notes(0) == ["Revised note"]
    doc.undo()
    assert doc.notes(0) == ["Review this line"]
    with pytest.raises(ValueError, match="note text"):
        doc.update_note(0, 0, " ")
    with pytest.raises(ValueError, match="Choose a note"):
        doc.update_note(0, 1, "Other")
    target = tmp_path / f"note-{rotation}.pdf"
    doc.save_copy(target)
    assert Document.open(target).notes(0) == ["Review this line"]
    doc.delete_note(0, 0)
    assert doc.notes(0) == []
    doc.undo()
    assert doc.notes(0) == ["Review this line"]


def test_bookmark_navigation_and_range_rotation():
    stream = io.BytesIO()
    canvas = Canvas(stream, pagesize=(300, 400))
    for _ in range(3):
        canvas.drawString(20, 300, "Synthetic page")
        canvas.showPage()
    canvas.save()
    doc = Document(stream.getvalue())
    doc.add_bookmark("First", 0)
    doc.add_bookmark("Last", 2)
    assert [(item["title"], item["page"]) for item in doc.bookmarks()] == [
        ("First", 0),
        ("Last", 2),
    ]
    history = len(doc.undo_stack)
    doc.rotate_pages([0, 2], 90)
    assert len(doc.undo_stack) == history + 1
    reader = PdfReader(io.BytesIO(doc.data))
    assert [page.rotation for page in reader.pages] == [90, 0, 90]
    doc.undo()
    assert [page.rotation for page in PdfReader(io.BytesIO(doc.data)).pages] == [0, 0, 0]
    doc.set_page_labels(0, 1, "Intro-", "roman", 1)
    assert doc.page_labels() == ["Intro-i", "Intro-ii", "3"]
    doc.undo()
    assert doc.page_labels() == ["1", "2", "3"]
    with pytest.raises(ValueError, match="valid pages"):
        doc.set_page_labels(2, 1)
