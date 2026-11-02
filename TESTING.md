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

## Source-preserving OCR review stage

Synthetic source scans verify extracted text, unchanged 100% rendering, retained
links, bookmarks and metadata, and refusal of rotated/cropped/text/form inputs.
The OCR engine tests require FORGE_PDF_TEST_OCR_DIR to point at a complete
app-scoped bundle; CI without it skips engine integration tests. Tk dialog tests
run in Windows CI. Independent viewer, other DPI, rotated/cropped, and screen
reader acceptance remain open. Do not present this as tagged PDF accessibility.

## Forms review stage

Synthetic AcroForm tests exercise custom checkbox on-state names and ordinary
radio groups, including widget appearance changes, serialized values, reopen
and Undo. The Tk dialog and field picker are tested with a synthetic radio
group. Independent-viewer appearance validation, complex choice fields and XFA
remain open.

## Bookmark editing review stage

Synthetic two-page outlines verify top-level rename/removal, destination preservation
and Undo. Nested outlines are refused without changing the source. Windows Tk
tests exercise the Browse bookmarks Rename and Remove controls. Reordering and
nested-outline editing remain open.

## Page-count performance review stage

A synthetic 500-page blank PDF (62,115 bytes) measured 100 repeated count
reads at about 1.7 seconds before caching and 0.000009 seconds afterward
on one Windows 11 x64 machine. Tests verify count after delete, append, Undo
and Redo. This measurement does not establish overall large-file responsiveness
or justify raising the 50 MB/500-page limits.


## 1.3.0 release checks

The Windows tag workflow builds from the annotated release tag, expands the pinned
app-scoped OCR bundle, runs the suite and the portable launch/save/session check,
and uploads release assets and checksums. Release acceptance on one Windows 11 x64
device also covered synthetic form controls and the packaged OCR engine. Other
Windows versions, independent viewer appearance, screen reader output and hostile
PDF isolation have not been accepted.
