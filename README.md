# Forge PDF

A free, offline desktop PDF editor for quick changes without an account, subscription,
or upload. White out a line, add a replacement, remove a footer, or put pages in order.

[Download for Windows](https://github.com/loganpendragonmultiverse/forge-pdf/releases/latest)
· [Project page](https://www.loganpendragonforge.com/open-source/forge-pdf/)

## Quick start

1. Download **Forge-PDF-1.2.0-Windows.zip** from the release page and extract it once.
2. Open the **Forge PDF** folder and double-click **Forge PDF.exe**. No installation or Python setup is needed.
3. Open a PDF, select **Whiteout**, and drag over the area you want to cover.
4. Use **Add text** to place new text, then **Save a copy** under a different name.

Keep `_internal` beside the executable. Help, licenses, and a synthetic practice PDF
are in `Support/`. The source archives on GitHub are for developers; the Windows ZIP
is the ready-to-run application.

**Whiteout and Clear footer are visual covers, not secure redaction. Covered text
and images remain in the PDF and can be extracted. Do not use them to remove secrets.**

## Features

- Find literal document text across pages with case and whole-word options, a result list,
  and next/previous matches. Image-only pages need external OCR.
- Add text with a selected local TrueType font and check the entered text for missing glyphs.
- Place PNG/JPEG image stamps with a drag preview and preserved transparency.
- Explicitly save/reopen a self-contained editing session, including bounded Undo history.
- Optionally enable a local recovery snapshot for the current document. New copies and
  sessions are published atomically after their bytes are written.
- Render previews on a single worker; obsolete previews cannot replace newer pages.
- Use two toolbar rows, a hideable pages panel and wrapped hints in smaller desktop windows.
- Review an export summary of pages, links, form fields and annotations before sharing.
- Fill existing editable text form fields, edit title/author/subject/keywords, and add a bookmark for the current page.
- Fill simple choice fields and Yes/Off checkboxes; browse bookmarks; add and delete native
  text notes. Edit existing text notes and browse notes across the document. Rotate selected
  page ranges as one Undoable edit.
- Use **Edit form fields** to choose supported fields from a list and edit them with
  text, option, or checkbox controls.
- Add a numbered or prefixed page-label range when the source has no custom labels;
  the pages panel displays the resulting labels.
- Save an AES-256 password-encrypted PDF copy through **Page actions → Save encrypted copy**.
- Use **Page actions → Rasterized redacted export** to drag a blacked-out area into a
  new image-only PDF. The export rebuilds every page from rendered pixels and discards
  source text, forms, links, annotations, bookmarks, attachments and metadata.

- Drag-to-whiteout and highlight, with click-to-place text in sizes from 8 to 72 points.
- Clear footer on every page: choose a height, defaulting to 5 pixels at 100% zoom.
  The whole batch is one undoable edit, including on rotated pages.
- Rotate left/right, reorder, duplicate, delete, insert blank pages, merge PDFs, and export one page.
- Right-click a page for quick actions. Deleted pages can be restored with Undo.
- Scroll past the bottom or top to change pages; PDFs open at 100% zoom.
- Go to page, fit page, Ctrl+wheel zoom, and preserved scroll position after edits.
- Undo/redo, dirty-document prompts, and Save a copy that refuses to overwrite source PDFs.
- Edit pages with links or visible annotations. Open password-protected PDFs with the password.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Open PDF |
| Ctrl+S | Save a copy |
| Ctrl+Z / Ctrl+Y | Undo / redo document edits |
| Ctrl+G | Go to page |
| Ctrl+F | Find document text |
| F3 / Shift+F3 | Next / previous search match |
| Ctrl+Shift+S | Save editing session |
| Ctrl+Shift+O | Open editing session |
| Page Up / Page Down | Previous / next page |
| Ctrl+mouse wheel | Zoom |
| Delete, with page list focused | Delete selected page |
| Escape | Cancel selection and return to Browse |

## Continuing an editing session

Use **Session → Save editing session** to write a .forgepdf file. It contains the current
PDF, up to 30 Undo snapshots within a 100 MB combined PDF payload budget, and original-file
names/identities used to prevent overwriting. Older Undo snapshots may be omitted to fit.
Redo history and selected font/image resource paths are not saved. Added content is already
embedded in the PDF; sessions do not turn existing paragraphs or stamps into editable layers.

Sessions are **unencrypted**, including documents originally opened with a password.
Their Undo snapshots can retain earlier or deleted content. Review them before sharing.
Opening a session restores its embedded PDF and view without reading recorded external
files. Save an edited PDF separately; saving a session does not mark a PDF copy as exported.
For opt-in recovery, choose **Session → Enable local recovery** and a local `.forgepdf`
destination. Forge PDF writes the current document there after edits, with a short idle
delay and without Undo snapshots. Open it using **Open editing session** after a crash.
**Stop local recovery** stops updates but keeps the file. **Delete a local recovery snapshot**
can remove the active snapshot or one you explicitly choose later, after confirmation.
Forge PDF accepts only snapshots marked as recovery by this version for that command;
ordinary editing sessions and older unmarked recovery files must be managed separately.
Recovery files are unencrypted, include original filenames,
and remain on disk until deleted. Recovery is unavailable for password-opened PDFs;
do not enable it for other sensitive documents.
There is no default autosave, account connection or network upload.

For a smaller window, use **Pages** to hide the sidebar. **Page actions** retains its commands.
Use **Add text → Local font** and **Check glyphs** before placing new text. Choose an image
under **Image stamp**, then drag its placement rectangle and review the preview before release.
**Page actions → Export checks** is an object summary with review reminders, not a fidelity
certificate. Continue reviewing exported links, forms, annotations and page ordering.

## Run from source

Requires Python 3.11 or newer with Tk. Windows is the supported desktop platform.
The source may run elsewhere, but macOS and Linux desktop behavior is not verified.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt -e ".[dev]"
.venv\Scripts\python -m forge_pdf
```

`Launch Forge PDF.cmd` launches an existing development environment. It does not
install anything automatically. See [DEVELOPMENT.md](DEVELOPMENT.md) for build commands.

## Limitations

- Adds content over existing pages; does not rewrite existing paragraphs, perform OCR,
  preserve vector/text content during redacted export, validate signatures, or support every AcroForm control. Form filling
  requires existing editable fields; complex choice options, radio groups, custom checkbox
  states, field creation, and XFA forms are unsupported.
- Whiteout retains underlying PDF content. It is inappropriate for hiding confidential data.
- Rasterized redacted export supports up to 20 pages and bounded page dimensions. It
  removes PDF objects from the new copy, but loses all searchable text, form behavior,
  links, accessibility structure and vector quality. The new PDF is unencrypted.
  The open source document and any
  prior editing sessions may still hold the unredacted material. Inspect the exported
  image-only PDF and manage original copies separately before sharing.
- On an edited page, visible annotations and form fields become page content before
  new marks are added. Links remain interactive; untouched pages retain their annotations.
- Editing signed PDFs invalidates their cryptographic signatures. A normal **Save a copy** of
  a password-opened PDF is unencrypted; use **Save encrypted copy** to set a new password.
  Editing sessions remain unencrypted. Dynamic form appearances and malformed PDFs can fail.
- Added text defaults to Helvetica/Western European characters. Choose a local .ttf font
  for other glyphs. Font files are limited to 20 MB; glyph presence does not establish
  complex-script shaping, font licensing or arbitrary-font compatibility. Text must fit.
- Image stamps accept PNG/JPEG up to 20 MB and 16 million pixels. They fit inside the
  selected rectangle with their aspect ratio retained. Stamps are visual images, not signatures.
- Text search is literal and defaults to case-insensitive, capped at 1000 matches and
  256 query characters. Optional case and whole-word matching is available. Search
  does not perform OCR or highlight exact glyph positions on the canvas.
- Supports up to 50 MB and 500 pages, including merged output. Complex files can pause
  the interface during processing. This app is intended for modest everyday documents.
- Undo keeps up to 30 edits within a 100 MB snapshot budget. Recovery is opt-in and
  may miss the most recent edit if the app exits before the idle snapshot completes.
- Page manipulation can affect bookmarks, links, and advanced PDF structures. Review
  saved copies against originals when preservation or print fidelity matters.
- Page-label editing currently refuses PDFs that already contain custom labels, to avoid
  silently rewriting their label structure.
- The Windows executable is unsigned. The release includes checksums for integrity checks.

## Privacy

The editor makes no network requests, uploads no files, runs no PDF scripts, and
stores work in memory until you explicitly save a PDF copy, editing session or enable
local recovery. It is not a sandbox for hostile PDFs. Installation
and development dependency audits use the network. See [SECURITY.md](SECURITY.md).

## Contributing and license

MIT-licensed source; dependencies retain their own licenses and bundled notices.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [CONTRIBUTING.md](CONTRIBUTING.md),
and [TESTING.md](TESTING.md). Contributions go through maintainer-reviewed pull requests.
There is no promised maintenance schedule. Report reproducible issues using synthetic,
non-sensitive PDFs through [GitHub Issues](https://github.com/loganpendragonmultiverse/forge-pdf/issues).

## 1.1.0 - 2026-10-16

Use **More page actions → Export page ranges** for one-based selections such as `1,3-5`.
Ranges ascend within each term; terms retain their entered order (`3,1-2` exports pages 3, 1,
then 2). Duplicate, malformed, empty, and out-of-range selections are rejected. Review every
output page in the ordered list; selecting an item previews that source page. Continue to save
one new PDF, or cancel at selection, review, or save. Source files stay protected, and exporting
does not clear unsaved edits or alter undo/redo history.

Subset export is not secure redaction. Retained pages may contain hidden content, annotations,
links, or other PDF objects. Review exported PDFs before sharing.
