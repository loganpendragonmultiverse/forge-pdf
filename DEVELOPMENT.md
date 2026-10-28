# Development

Forge PDF is a native Tk desktop app with a separate PDF document model.
`app.py` owns interaction and view state; `document.py` owns transactional edits.
pypdf edits document structure, PDFium renders pages and flattens visible annotations,
and ReportLab generates content overlays. Cryptography provides AES PDF decryption.

## Local checks

```powershell
python -m pip install -r requirements-lock.txt -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip_audit -r requirements-lock.txt
python -m build
python tools/build_windows.py
```

Windows CI tests Python 3.11 and 3.14. CodeQL checks the Python source. Tag builds
produce the portable Windows ZIP, wheel, source distribution, and checksums.
Public release assets must be the artifacts from the matching tag build.

## Constraints

Never upload private PDFs or store them in fixtures. `examples/Welcome.pdf` is synthetic.
Keep original input files protected. Whiteout must never be marketed as secure redaction.
Footer clearing is transactional across all pages and must remain a single undo action.
Retain the no-network runtime boundary and all binary dependency notices.

The maintainer reviews contributions before merge. Releases reconcile source versions,
changelog, GitHub assets, and the Forge project page. No recurring maintenance is promised.

## 1.1.0 - 2026-10-16

Use **More page actions → Export page ranges** for one-based selections such as `1,3-5`.
Ranges ascend within each term; terms retain their entered order (`3,1-2` exports pages 3, 1,
then 2). Duplicate, malformed, empty, and out-of-range selections are rejected. Review every
output page in the ordered list; selecting an item previews that source page. Continue to save
one new PDF, or cancel at selection, review, or save. Source files stay protected, and exporting
does not clear unsaved edits or alter undo/redo history.

Subset export is not secure redaction. Retained pages may contain hidden content, annotations,
links, or other PDF objects. Review exported PDFs before sharing.

## 1.2.0 - bounded offline editor additions

Document search is literal, read-only, capped at 1000 matches; it is not OCR. Local TrueType
fonts are embedded only for inserted text, with glyph diagnostics. PNG/JPEG stamps preserve
selected bytes and preview a bounded thumbnail before committing a visible-page overlay.

Explicit sessions use ZIP/JSON/PDF bytes, never pickle or extracted paths. Validate members,
duplicate names, declared sizes, payload totals, schema types, PDF/page limits and view state.
Read original destination identities without auto-opening stored paths. Preserve all previous
source/alias protection and transactional edits. A session is unencrypted and retains Undo
content; it does not mark a PDF export saved.

All PDFium calls within each process share one reentrant lock. Worker inputs use bounded shared memory and results use a private pipe; no document data is written to temporary disk files. The GUI creates no background Python threads, preventing Tk finalization on a worker thread. Closing cancels only its own worker processes. One preview worker process coalesces requests;
only matching generations paint, and all Tk/ImageTk operations stay on the main thread.
Search uses a separate memory-only worker process and discards results if document bytes changed. Keep gesture
capture stable while previews are pending. Test real event-loop responsiveness and stale results.

Use tools/native-pdf.Dockerfile for optional headless Linux development checks; it does not
establish Windows package acceptance. Required Windows CI and exact portable-artifact smoke,
plus synthetic crop/rotation/link/form/annotation comparisons, remain release gates.

## 1.3.0 Windows OCR release

The release workflow expands `vendor/ocr-bundle.zip` and passes that folder to
`tools/build_windows.py --ocr-bundle`. The builder verifies the engine, English
model, PDF config and OCR notices by SHA-256, and refuses extra OCR DLLs.
Keep the source-build receipt and full component notices with the Windows ZIP.
The OCR engine never uploads documents. Update its pinned hashes and notice
inventory together if the engine or language data changes.
