# Forge PDF

A free, offline desktop PDF editor for quick changes without an account, subscription,
or upload. White out a line, add a replacement, remove a footer, or put pages in order.

[Download for Windows](https://github.com/loganpendragonmultiverse/forge-pdf/releases/latest)
· [Project page](https://www.loganpendragonforge.com/open-source/forge-pdf/)

## Quick start

1. Download **Forge-PDF-1.0.0-Windows.zip** from the release page and extract it once.
2. Open the **Forge PDF** folder and double-click **Forge PDF.exe**. No installation or Python setup is needed.
3. Open a PDF, select **Whiteout**, and drag over the area you want to cover.
4. Use **Add text** to place new text, then **Save a copy** under a different name.

Keep `_internal` beside the executable. Help, licenses, and a synthetic practice PDF
are in `Support/`. The source archives on GitHub are for developers; the Windows ZIP
is the ready-to-run application.

**Whiteout and Clear footer are visual covers, not secure redaction. Covered text
and images remain in the PDF and can be extracted. Do not use them to remove secrets.**

## Features

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
| Page Up / Page Down | Previous / next page |
| Ctrl+mouse wheel | Zoom |
| Delete, with page list focused | Delete selected page |
| Escape | Cancel selection and return to Browse |

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
  securely redact, validate signatures, or provide interactive form filling.
- Whiteout retains underlying PDF content. It is inappropriate for hiding confidential data.
- On an edited page, visible annotations and form fields become page content before
  new marks are added. Links remain interactive; untouched pages retain their annotations.
- Editing signed PDFs invalidates their cryptographic signatures. Password-opened edited
  copies are saved without encryption. Dynamic form appearances and malformed PDFs can fail.
- Added text uses Helvetica and Western European characters and must fit on the page.
- Supports up to 50 MB and 500 pages, including merged output. Complex files can pause
  the interface during processing. This app is intended for modest everyday documents.
- Undo keeps up to 30 edits within a 100 MB snapshot budget. No autosave or crash recovery.
- Page manipulation can affect bookmarks, links, and advanced PDF structures. Review
  saved copies against originals when preservation or print fidelity matters.
- The Windows executable is unsigned. The release includes checksums for integrity checks.

## Privacy

The editor makes no network requests, uploads no files, runs no PDF scripts, and
stores work in memory until you save. It is not a sandbox for hostile PDFs. Installation
and development dependency audits use the network. See [SECURITY.md](SECURITY.md).

## Contributing and license

MIT-licensed source; dependencies retain their own licenses and bundled notices.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), [CONTRIBUTING.md](CONTRIBUTING.md),
and [TESTING.md](TESTING.md). Contributions go through maintainer-reviewed pull requests.
There is no promised maintenance schedule. Report reproducible issues using synthetic,
non-sensitive PDFs through [GitHub Issues](https://github.com/loganpendragonmultiverse/forge-pdf/issues).
