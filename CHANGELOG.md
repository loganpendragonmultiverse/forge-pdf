# Changelog

## 1.2.0 — 2026-10-23

- Add literal document search with next/previous navigation, including keyboard shortcuts.
- Add local TrueType fonts for new text, with missing-glyph feedback.
- Add PNG/JPEG stamps with immutable selected data, placement preview and transparent export.
- Add explicit unencrypted editing sessions with self-contained PDFs, bounded Undo and original-file protection.
- Coalesce asynchronous previews through one worker with serialized PDFium access and stale-result guards.
- Improve compact desktop controls, focus access and wrapped hints; retain page actions with the sidebar hidden.
- Add export object summaries and synthetic save/reopen checks across cropped/rotated pages.
- Preserve visual-whiteout limitations, existing editing operations, no-network runtime and source protection.


- Update audited runtime pins to Pillow 13.0.0 and pypdf 6.21.2.

## 1.1.0 - 2026-10-16

- Updated pypdf to 6.19.0 and raised its supported minimum to include the PDF parser security fixes.

Use **More page actions → Export page ranges** for one-based selections such as `1,3-5`.
Ranges ascend within each term; terms retain their entered order (`3,1-2` exports pages 3, 1,
then 2). Duplicate, malformed, empty, and out-of-range selections are rejected. Review every
output page in the ordered list; selecting an item previews that source page. Continue to save
one new PDF, or cancel at selection, review, or save. Source files stay protected, and exporting
does not clear unsaved edits or alter undo/redo history.

Subset export is not secure redaction. Retained pages may contain hidden content, annotations,
links, or other PDF objects. Review exported PDFs before sharing.

## 1.0.0 — 2026-09-09

Initial public release following local desktop testing.

- Whiteout, highlight, and add text on PDF pages, including pages with annotations.
- Adjustable Clear footer across every page with a 5px default and one-step undo.
- Rotate, reorder, duplicate, delete, insert blank pages, merge, and export a page.
- Page-boundary scrolling, right-click actions, Go to page, and 100% default zoom.
- Reliable drag capture with silent tiny clicks and scroll preservation after edits.
- Password opening, source-preserving copies, and undo/redo.
- Portable Windows app, Python source, tests, CI, CodeQL, and dependency notices.

Whiteout is visual cover, not secure redaction. Saved password-opened copies are unencrypted.
