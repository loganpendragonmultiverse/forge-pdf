"""Opt-in recovery UI lifecycle on a synthetic document."""

import time

from forge_pdf.app import Editor
from forge_pdf.document import Document
from forge_pdf.enhancements import open_session

from test_recovery import fixture_pdf


def test_recovery_opt_in_idle_write_and_delete(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(fixture_pdf())
        app.path = tmp_path / "synthetic.pdf"
        destination = tmp_path / "recovery.forgepdf"
        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", lambda *a, **kw: True)
        monkeypatch.setattr(
            "forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(destination)
        )
        assert app.enable_recovery()
        assert destination.exists()
        app.change(lambda: app.doc.add_bookmark("After", 0))
        deadline = time.monotonic() + 5
        while app.recovery_after and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert app.recovery_after is None
        restored, _, _ = open_session(destination)
        assert restored.data == app.doc.data
        app.delete_recovery()
        assert app.recovery_path is None
        assert not destination.exists()
    finally:
        app.destroy()
