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

## 1.1.0 - 2026-10-16

Use **More page actions → Export page ranges** for one-based selections such as `1,3-5`.
Ranges ascend within each term; terms retain their entered order (`3,1-2` exports pages 3, 1,
then 2). Duplicate, malformed, empty, and out-of-range selections are rejected. Review every
output page in the ordered list; selecting an item previews that source page. Continue to save
one new PDF, or cancel at selection, review, or save. Source files stay protected, and exporting
does not clear unsaved edits or alter undo/redo history.

Subset export is not secure redaction. Retained pages may contain hidden content, annotations,
links, or other PDF objects. Review exported PDFs before sharing.

## 1.2.0 acceptance

The suite covers literal search, local-font glyph errors and Unicode save/reopen, transparent
image stamps under all four rotations with cropped pages, session Undo/state restoration,
source and hardlink protection, malformed session metadata/member refusal and no automatic
external-file loads. Desktop tests cover actual saved sessions, font selection, search,
immutable stamp previews, compact page actions and delayed/stale preview workers.

Headless Linux Tk results are development evidence only. Windows 3.11/3.14 checks and a launch/
load/save/session smoke of the exact portable ZIP are required before release. Compare rendered
synthetic pages and inspect retained links/forms/annotation appearances. A successful object
preflight or test fixture is not a guarantee for arbitrary documents, fonts or accessibility tools.
Screen-reader, physical small-device, large-file responsiveness and hostile-PDF isolation remain
unverified. Do not advertise whiteout, subset export or image stamps as security redaction.
