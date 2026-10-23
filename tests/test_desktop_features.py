import threading
import gc
from concurrent.futures import Future
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import reportlab
from PIL import Image

from forge_pdf.app import Editor


def wait_preview(app):
    deadline = time.monotonic() + 10
    while app.preview_pending or app.pending_resize:
        app.update()
        if time.monotonic() > deadline:
            raise AssertionError("Preview did not complete")
        time.sleep(0.005)
    app.update()


@pytest.fixture
def editor():
    app = Editor()
    app.update()
    errors = []
    app.error = lambda error: errors.append(str(error))
    app.load(Path(__file__).resolve().parents[1] / "examples" / "Welcome.pdf")
    wait_preview(app)
    yield app, errors
    app.destroy()


def point(app, x, y):
    return SimpleNamespace(
        x=int(app.offset_x + x * app.scale_x), y=int(app.offset_y + y * app.scale_y)
    )


def test_stamp_preview_uses_selected_bytes_and_commits_once(editor, tmp_path, monkeypatch):
    app, errors = editor
    image = tmp_path / "stamp.png"
    Image.new("RGB", (20, 20), (0, 220, 0)).save(image)
    selected = image.read_bytes()
    monkeypatch.setattr("forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(image))
    app.choose_stamp()
    Image.new("RGB", (20, 20), (220, 0, 0)).save(image)
    assert app.stamp_data == selected
    app.press(point(app, 20, 20))
    app.drag(point(app, 60, 60))
    assert len(app.canvas.find_withtag("selection")) == 2
    assert (app.stamp_thumbnail.width(), app.stamp_thumbnail.height()) == (40, 40)
    app.release(point(app, 60, 60))
    app.release(point(app, 60, 60))
    wait_preview(app)
    assert len(app.doc.undo_stack) == 1
    assert app.doc.render(0).getpixel((40, 40))[1] > 180
    assert not errors


def test_session_ui_preserves_dirty_state_and_reopens_without_external_reads(
    editor, tmp_path, monkeypatch
):
    app, errors = editor
    app.doc.rotate(0)
    app.refresh()
    wait_preview(app)
    edited = app.doc.data
    target = tmp_path / "session.forgepdf"
    monkeypatch.setattr("forge_pdf.app.filedialog.asksaveasfilename", lambda **kw: str(target))
    assert app.save_session_dialog()
    assert app.doc.dirty
    monkeypatch.setattr("forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(target))
    monkeypatch.setattr(app, "discard_ok", lambda: True)
    app.open_session_dialog()
    wait_preview(app)
    assert app.doc.data == edited and app.doc.dirty
    app.history(False)
    wait_preview(app)
    assert app.doc.data != edited and not errors


def test_local_font_picker_and_keyboard_search(editor, monkeypatch):
    from tkinter import ttk

    app, errors = editor
    font = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    monkeypatch.setattr("forge_pdf.app.filedialog.askopenfilename", lambda **kw: str(font))
    app.text_entry.delete(0, "end")
    app.text_entry.insert(0, "Café Ω")
    app.choose_font()
    app.check_glyphs()
    app.set_mode("text")
    app.press(point(app, 40, 100))
    wait_preview(app)
    assert app.doc.search("Café Ω")
    app.find_dialog()
    dialog = app.search_window
    entry = next(child for child in dialog.winfo_children() if isinstance(child, ttk.Entry))
    entry.insert(0, "Café Ω")
    buttons = next(child for child in dialog.winfo_children() if isinstance(child, ttk.Frame))
    next(child for child in buttons.winfo_children() if child.cget("text") == "Find").invoke()
    deadline = time.monotonic() + 10
    while not app.search_results:
        app.update()
        assert time.monotonic() < deadline
        time.sleep(0.005)
    wait_preview(app)
    assert app.search_results[0]["page"] == 0 and "1 of 1" in app.search_info.get()
    assert app.next_match(-1) == "break"
    assert not errors


def test_preview_worker_keeps_event_loop_alive_and_discards_stale_image(editor):
    app, errors = editor
    app.doc.rotate(0)
    old_image = app.doc.render(0)
    first = Future()
    actual_submit = app.preview_executor.submit
    calls = []

    def delayed(data, params):
        calls.append(params)
        return first if len(calls) == 1 else actual_submit(data, params)

    with patch.object(app.preview_executor, "submit", delayed):
        app.refresh()
        live = []
        app.after(1, lambda live=live: live.append(True))
        app.show_page(1)
        deadline = time.monotonic() + 2
        while not live:
            app.update()
            assert time.monotonic() < deadline
        params = calls[0]
        first.set_result(
            (
                params["generation"],
                old_image,
                792,
                612,
                1,
                params["cw"],
                params["ch"],
                params["view"],
            )
        )
        wait_preview(app)
    assert app.page == 1
    assert app.photo.width() == 612
    assert len(calls) == 2 and calls[1]["page"] == 1
    assert not errors


def test_repeated_editors_close_active_processes_without_background_gui_gc():
    baseline = {thread.ident for thread in threading.enumerate()}
    source = Path(__file__).resolve().parents[1] / "examples" / "Welcome.pdf"
    before = source.read_bytes()
    for _ in range(6):
        app = Editor()
        app.update()
        app.load(source)
        future = app.preview_future
        assert future is not None and future.process.is_alive()
        live = []
        app.after(1, lambda live=live: live.append(True))
        deadline = time.monotonic() + 2
        while not live:
            app.update()
            assert time.monotonic() < deadline
        assert {thread.ident for thread in threading.enumerate()} == baseline
        app.destroy()
        assert not future.process.is_alive() and future.memory is None
        del app
        gc.collect()
    assert source.read_bytes() == before


def test_compact_layout_retains_page_actions_and_keyboard_focus(editor):
    from tkinter import ttk

    app, errors = editor
    app.geometry("740x520")
    app.update()
    wait_preview(app)
    app.toggle_sidebar()
    app.update()
    assert not app.sidebar.winfo_manager()
    assert app.workspace.winfo_width() > 650

    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from children(child)

    actions = [
        child
        for child in children(app)
        if isinstance(child, ttk.Menubutton) and child.cget("text") == "Page actions"
    ]
    assert len(actions) == 1 and actions[0].winfo_ismapped()
    assert app.canvas.cget("takefocus") == "1"
    assert not errors


def test_closing_find_reaps_active_search_and_allows_another(editor):
    from tkinter import ttk

    app, errors = editor

    def start_find(query):
        app.find_dialog()
        dialog = app.search_window
        entry = next(w for w in dialog.winfo_children() if isinstance(w, ttk.Entry))
        entry.insert(0, query)
        buttons = next(w for w in dialog.winfo_children() if isinstance(w, ttk.Frame))
        next(w for w in buttons.winfo_children() if w.cget("text") == "Find").invoke()
        return dialog, buttons, app.search_future

    dialog, buttons, first = start_find("Welcome")
    assert first.process.is_alive()
    next(w for w in buttons.winfo_children() if w.cget("text") == "Close").invoke()
    assert not first.process.is_alive() and first.memory is None
    assert app.search_window is None and app.winfo_exists()
    dialog, buttons, second = start_find("PDF")
    deadline = time.monotonic() + 10
    while app.search_snapshot is None:
        app.update()
        assert time.monotonic() < deadline
        time.sleep(0.005)
    assert second is not first and app.search_results
    assert not errors
