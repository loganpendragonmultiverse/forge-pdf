"""The OCR progress dialog stays responsive and reports save or cancellation."""

import time
import tkinter as tk

from forge_pdf.app import Editor
from forge_pdf.document import Document
from test_ocr import make_scan


class FakeOcrFuture:
    def __init__(self):
        self.progress = (0, 1)
        self.finished = False
        self.cancelled = False

    def done(self):
        return self.finished

    def result(self):
        return True

    def cancel(self):
        self.cancelled = True


def test_ocr_progress_dialog_and_cancel(tmp_path, monkeypatch):
    app = Editor()
    try:
        app.doc = Document(make_scan())
        app.path = tmp_path / "scan.pdf"
        bundle = tmp_path / "Support" / "ocr" / "tessdata"
        bundle.mkdir(parents=True)
        (bundle / "eng.traineddata").write_bytes(b"language available")
        monkeypatch.setattr("forge_pdf.app.sys.executable", str(tmp_path / "python.exe"))
        monkeypatch.setattr("forge_pdf.app.messagebox.askyesno", lambda *a, **k: True)
        monkeypatch.setattr(
            "forge_pdf.app.filedialog.asksaveasfilename",
            lambda **k: str(tmp_path / "searchable.pdf"),
        )
        future = FakeOcrFuture()
        monkeypatch.setattr(app.ocr_executor, "submit", lambda data, params: future)
        assert app.export_ocr()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        future.progress = (1, 1)
        app.update()
        assert dialog.winfo_exists()
        future.finished = True
        time.sleep(0.12)
        app.update()
        assert not dialog.winfo_exists()
        assert "OCR copy saved" in app.status.cget("text")

        future = FakeOcrFuture()
        assert app.export_ocr()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        button = next(w for w in dialog.winfo_children() if w.winfo_class() == "TButton")
        button.invoke()
        assert future.cancelled
        assert "cancelled" in app.status.cget("text")
    finally:
        app.destroy()
