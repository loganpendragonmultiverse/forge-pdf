"""Opt-in recovery UI lifecycle on a synthetic document."""

import time

from forge_pdf.app import Editor
from forge_pdf.document import Document
from forge_pdf.enhancements import is_recovery_snapshot, open_session, save_session

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
        assert is_recovery_snapshot(destination)
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


def test_delete_stopped_snapshot_requires_explicit_selection(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(fixture_pdf())
        app.path = tmp_path / "synthetic.pdf"
        destination = tmp_path / "recovery.forgepdf"
        ordinary = tmp_path / "ordinary.forgepdf"
        save_session(app.doc, destination, 0, 1.0, include_history=False, recovery=True)
        save_session(app.doc, ordinary, 0, 1.0, include_history=False)
        prompts = []
        monkeypatch.setattr(
            "forge_pdf.app.messagebox.askyesno", lambda *a, **kw: prompts.append(a) or True
        )
        monkeypatch.setattr("forge_pdf.app.messagebox.showerror", lambda *a, **kw: None)
        monkeypatch.setattr("forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(ordinary))
        assert not app.delete_recovery()
        assert ordinary.exists()
        assert not prompts
        monkeypatch.setattr(
            "forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(destination)
        )
        assert app.delete_recovery()
        assert not destination.exists()
        assert ordinary.exists()
        assert len(prompts) == 1
    finally:
        app.destroy()


def test_changed_recovery_snapshot_is_not_deleted(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(fixture_pdf())
        app.path = tmp_path / "synthetic.pdf"
        target = tmp_path / "recovery.forgepdf"
        save_session(app.doc, target, 0, 1.0, include_history=False, recovery=True)
        monkeypatch.setattr("forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(target))
        errors = []
        monkeypatch.setattr(app, "error", lambda exc: errors.append(str(exc)))

        def replace_during_confirmation(*args, **kwargs):
            target.write_bytes(b"replacement")
            return True

        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", replace_during_confirmation)
        assert not app.delete_recovery()
        assert target.read_bytes() == b"replacement"
        assert "changed before deletion" in errors[0]
    finally:
        app.destroy()


def test_recovery_never_overwrites_ordinary_session_or_replaced_snapshot(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(fixture_pdf())
        app.path = tmp_path / "synthetic.pdf"
        target = tmp_path / "selected.forgepdf"
        save_session(app.doc, target, 0, 1.0, include_history=False)
        before = target.read_bytes()
        errors = []
        monkeypatch.setattr(app, "error", lambda exc: errors.append(str(exc)))
        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", lambda *a, **kw: True)
        monkeypatch.setattr("forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(target))
        assert not app.enable_recovery()
        assert target.read_bytes() == before
        assert app.recovery_path is None

        target.unlink()
        assert app.enable_recovery()
        target.write_bytes(before)
        app.write_recovery()
        assert app.recovery_path is None
        assert target.read_bytes() == before
        assert "updates stopped" in app.status.cget("text")
    finally:
        app.destroy()
