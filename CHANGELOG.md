# Changelog

## 1.5.0 - 2026-11-11

- Organize Page actions into eight short submenus and keep all existing commands available.
- Create blank PDFs with paper and orientation choices, create PDFs from PNG/JPEG
  files, and insert image pages into an open document.
- Reverse page order, group odd or even pages first, move a range, and duplicate
  selected pages.
- Crop by dragging, apply exact margins to ranges, and reset to the full page.
- Draw rectangles and ellipses with outlined or filled styles, lines and arrows.
  Choose text, highlight and drawing colors and set line thickness.
- Save the current page as PNG or JPEG, copy its embedded text, and save a lossless
  compressed PDF copy.
- Fit height, toggle full screen, and preview in grayscale or inverted colors.
- Inspect document information and embedded URI links, or clear the four common metadata fields.
- Stop local recovery snapshots when imported pages came from a password-protected PDF.

## 1.4.0 - 2026-11-09

- Add full-document reordering, range deletion, and ordered page insertion from another PDF.
  Appending and inserting now prompt for a password when the other PDF requires one.
- Rotate selected ranges left, right, or 180 degrees.
- Apply headers, footers, page numbers, and translucent text watermarks in one Undo step.
- Split selected pages into separate PDFs, export rendered PNG or JPEG pages to a ZIP, and
  save embedded text to UTF-8.
- Add Fit width and first/last page navigation.
- Preserve internal links between retained pages in a subset export, and keep the active
  page stationary when a move fails.
- Keep text-control Undo/Redo shortcuts from editing the document, report effective preview
  zoom when rendering is capped, and derive Windows archive names from the package version.

## 1.3.0 - 2026-10-28

- Add offline English OCR image-copy and limited source-preserving text-layer exports with progress and cancellation. The Windows ZIP includes a pinned, source-built Tesseract engine and notices.
- Fill supported text, choice, checkbox and radio forms; edit common metadata and simple top-level bookmarks.
- Add native text notes and highlights, including review, editing, recoloring and removal where supported.
- Add page-range rotation, page labels, richer literal search and AES-256 encrypted-copy export.
- Add opt-in history-free recovery snapshots and atomic output writes.
- Add bounded rasterized redacted export that rebuilds pages from pixels; the output loses source text, links, forms and accessibility structure.
- Preserve original files and document limits; retain explicit exclusions for signature validation, XFA, tagged output and object-preserving redaction.

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
