# Testing

Run `python -m pytest -q`, `python -m ruff check .`, and `python -m ruff format --check .`.
Run `python -m pip_audit -r requirements-lock.txt` for runtime dependency advisories.
Build distributions with `python -m build` and the Windows app with `python tools/build_windows.py`.

The suite covers PDF save/reopen, original protection, undo/redo, transactional failure,
rotation/cropping, annotation appearances and retained links, password opening, page
operations, and footer coverage. Tk interaction tests exercise tiny clicks, repeated
drags, duplicate release events, render deferral during selection, scroll boundaries,
trackpad deltas, cancellation, quick delete, 100% opening, and footer dialog behavior.

Tk tests require an interactive desktop session. CI runs them on Windows. Unit results
do not establish physical-device compatibility or visual fidelity for every possible PDF.

For desktop acceptance, open the synthetic practice file. Test Whiteout with a simple
click followed by a real drag, apply Clear footer and Undo, scroll to the next page,
right-click a page to delete and restore it, and save/reopen the result. Inspect the
window at its default and minimum sizes. Compare saved PDFs against originals.

No macOS/Linux desktop, screen-reader, large-file responsiveness, or hostile-document
sandbox verification is claimed. Use synthetic fixtures for bug reports.
