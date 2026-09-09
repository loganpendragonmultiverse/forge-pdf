from pathlib import Path
from types import SimpleNamespace

import pytest

from forge_pdf.app import Editor


@pytest.fixture(scope="module")
def window():
    app = Editor()
    app.geometry("960x640")
    app.update()
    yield app
    app.destroy()


@pytest.fixture
def editor(window, monkeypatch):
    app = window
    app.doc = None
    app.wheel_delta = 0
    errors = []
    monkeypatch.setattr(app, "error", lambda exc: errors.append(str(exc)))
    app.update()
    app.load(Path(__file__).resolve().parents[1] / "examples" / "Welcome.pdf")
    app.update()
    app.set_mode("whiteout")
    yield app, errors
    app.cancel_drag()


def point(app, x, y):
    return SimpleNamespace(
        x=int(app.offset_x + x * app.scale_x), y=int(app.offset_y + y * app.scale_y)
    )


def test_click_jitter_and_repeated_drag_commit_once(editor):
    app, errors = editor
    original = app.doc.data
    for _ in range(7):
        app.press(point(app, 40, 40))
        app.release(point(app, 40, 40))
    assert app.doc.data == original
    assert not errors
    for n in range(5):
        app.press(point(app, 40, 40))
        app.drag(point(app, 100, 65))
        app.render()  # A resize callback cannot replace the canvas during a gesture.
        assert app.drag_start is not None
        app.release(point(app, 100, 65))
        app.release(point(app, 100, 65))  # Duplicate release cannot commit a second edit.
        assert len(app.doc.undo_stack) == n + 1
        assert app.canvas.grab_current() is None
    assert not errors


def test_scroll_across_pages_in_both_directions(editor):
    app, errors = editor
    app.canvas.yview_moveto(1)
    app.wheel(SimpleNamespace(delta=-120))
    assert app.page == 1
    assert app.canvas.yview()[0] == 0
    assert app.pages.curselection() == (1,)
    app.wheel(SimpleNamespace(delta=120))
    assert app.page == 0
    assert app.canvas.yview()[1] >= 0.999
    assert not errors


def test_trackpad_deltas_and_drag_do_not_change_pages(editor):
    app, _ = editor
    app.canvas.yview_moveto(1)
    for _ in range(3):
        app.wheel(SimpleNamespace(delta=-30))
    assert app.page == 0
    app.wheel(SimpleNamespace(delta=-30))
    assert app.page == 1
    app.press(point(app, 40, 40))
    app.wheel(SimpleNamespace(delta=120))
    assert app.page == 1
    app.set_mode("view")
    assert app.drag_start is None
    assert not app.doc.undo_stack


def test_quick_delete_undo_and_rotate_left(editor):
    app, errors = editor
    app.show_page(1)
    app.quick_delete()
    assert app.doc.count == 2
    app.history(False)
    assert app.doc.count == 3
    app.change(lambda: app.doc.rotate(app.page, -90))
    assert app.doc.size(app.page) == (792, 612)
    assert not errors


def test_drag_keeps_scrolled_view_and_100_percent_default(editor):
    app, errors = editor
    assert app.zoom == 1 and app.fit is False
    app.canvas.yview_moveto(0.25)
    original_scroll = app.canvas.yview()[0]
    app.press(SimpleNamespace(x=int(app.offset_x + 50), y=80))
    app.drag(SimpleNamespace(x=int(app.offset_x + 120), y=120))
    app.release(SimpleNamespace(x=int(app.offset_x + 120), y=120))
    assert abs(app.canvas.yview()[0] - original_scroll) < 0.002
    assert len(app.doc.undo_stack) == 1
    assert not errors


def test_footer_dialog_defaults_and_cancel(editor, monkeypatch):
    app, errors = editor
    captured = {}

    def cancel(*args, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr("forge_pdf.app.simpledialog.askinteger", cancel)
    app.clear_footer()
    assert captured["initialvalue"] == 5
    assert not app.doc.dirty
    monkeypatch.setattr("forge_pdf.app.simpledialog.askinteger", lambda *a, **k: 5)
    app.clear_footer()
    assert len(app.doc.undo_stack) == 1
    app.history(False)
    assert not app.doc.dirty
    assert not errors
