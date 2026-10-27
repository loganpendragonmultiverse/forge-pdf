"""Synthetic desktop path through the added form and navigation controls."""

import time
import tkinter as tk

from pypdf import PdfReader

from forge_pdf.app import Editor
from forge_pdf.document import Document

from test_professional_workflows import controls_pdf


def test_choice_checkbox_and_bookmark_navigation(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(controls_pdf())
        app.path = tmp_path / "controls.pdf"
        app.refresh()
        deadline = time.monotonic() + 10
        while app.preview_pending and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert not app.preview_pending
        values = iter(("tier", "Gold", "agree"))
        monkeypatch.setattr("forge_pdf.app.simpledialog.askstring", lambda *a, **kw: next(values))
        app.fill_choice_field_dialog()
        app.toggle_checkbox_dialog()
        assert app.doc.choice_fields()["tier"][0] == "Gold"
        assert app.doc.checkbox_fields()["agree"]
        app.doc.add_bookmark("Controls", 0)
        app.browse_bookmarks()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        listing = next(w for w in dialog.winfo_children() if isinstance(w, tk.Listbox))
        assert "Controls" in listing.get(0)
        listing.selection_set(0)
        button = next(w for w in dialog.winfo_children() if w.winfo_class() == "TButton")
        button.invoke()
        assert app.page == 0
        app.edit_form_fields_dialog()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        listing = next(w for w in dialog.winfo_children() if isinstance(w, tk.Listbox))
        choice_index = next(i for i in range(listing.size()) if listing.get(i).startswith("tier"))
        listing.selection_clear(0, "end")
        listing.selection_set(choice_index)
        listing.event_generate("<<ListboxSelect>>")
        app.update()
        from tkinter import ttk

        choice = next(w for w in dialog.winfo_children() if isinstance(w, ttk.Combobox))
        choice.set("Silver")
        controls = next(w for w in dialog.winfo_children() if isinstance(w, ttk.Frame))
        next(w for w in controls.winfo_children() if w.cget("text") == "Apply value").invoke()
        assert app.doc.choice_fields()["tier"][0] == "Silver"
    finally:
        app.destroy()


def test_rasterized_redacted_export_dialog(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(controls_pdf())
        app.path = tmp_path / "controls.pdf"
        target = tmp_path / "redacted.pdf"
        prompts = []

        def confirm(*args, **kwargs):
            prompts.append(args[1])
            return True

        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", confirm)
        monkeypatch.setattr("forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(target))
        app.set_mode("raster_redact")
        assert app.export_redacted((20, 20, 100, 100))
        assert target.exists()
        assert "unencrypted" in prompts[0]
        assert app.mode.get() == "view"
        assert not PdfReader(target).get_fields()
    finally:
        app.destroy()
