# Professional PDF capability plan

Forge PDF is an offline, modest-document editor. This plan compares its actual capabilities
with current vendor feature lists, then orders work by user value, correctness risk, and fit
with the existing pypdf/PDFium/ReportLab architecture. Adobe lists OCR, redaction, comparison,
forms and batch actions; Foxit describes page organization and OCR; PDF-XChange describes
annotations and signing. These are capability references, not claims of equivalent quality.

Sources: [Adobe Acrobat features](https://www.adobe.com/acrobat/pricing/compare-versions.html),
[Adobe redaction documentation](https://helpx.adobe.com/acrobat/desktop/protect-documents/redact-pdfs/redact.html),
[Foxit OCR](https://www.foxit.com/), [Foxit page organization](https://www.foxit.com/blog/organizing-pdf-documents-lets-you-get-more-out-of-your-content/),
[PDF-XChange Editor](https://www.pdf-xchange.com/product/downloads).

## Implemented in draft PR #16

1. Fill existing editable AcroForm text, simple choice, single-state checkbox and
   ordinary radio-group fields, with a field picker. XFA, complex choices, push
   buttons and signature fields remain unsupported.
2. Edit common document metadata; add, browse, rename and remove simple top-level bookmarks; add, edit, delete and browse
   native text notes; add and delete native highlight annotations; rotate page ranges;
   and add page labels when no custom labels exist.
3. Search literal text with case and whole-word options and a browsable result list.
4. Save an AES-256 encrypted copy. Normal Save a copy, rasterized export, recovery snapshots
   and editing sessions remain unencrypted. The password is not persisted by Forge PDF.
5. Publish new files atomically and optionally keep a local recovery snapshot without Undo
   history. A password-opened document cannot enable recovery.
6. Export a bounded image-only PDF with a selected rectangle blacked out. The PDF is rebuilt
   from rendered pixels and source objects are discarded. Searchability, accessibility
   structure and vector fidelity are lost. Original and earlier session copies persist.

## Next priorities

| Priority | Capability | Concrete acceptance gate |
| --- | --- | --- |
| P0 | True redaction | Stage 3 provides a bounded rasterized export: every source page is rebuilt from pixels, the selected rectangle is blacked out, and source objects are absent from the new PDF. This loses text/vector fidelity and does not erase the open source document or old sessions. Next: precise object-preserving redaction, independent viewer/forensic validation and sensitive-copy lifecycle. Never label visual whiteout secure. |
| P0 | Crash recovery | Opt-in history-free snapshots and atomic writes are implemented. The current stage marks recovery files, rejects ordinary sessions as recovery destinations, stops updates if a snapshot is replaced, and allows explicit deletion of a selected marked snapshot. Next: corruption/restart UI acceptance and optional user-directed retention policy. No automatic cleanup. |
| P1 | OCR | Bounded offline searchable image-copy export, separate worker, per-page progress, cancellation and selection among installed language files are implemented. The source-built private preview passed synthetic OCR and a visible Windows export. A separate bounded text-layer copy now preserves original page objects for simple unrotated, uncropped image-only pages, with synthetic visual/text/navigation tests. Next: mixed and rotated pages, independent-viewer acceptance, and redistribution/compatibility gates. No document upload. |
| P1 | Full forms | Existing text and simple choice fields, single-state checkboxes with custom on-state names, and ordinary radio groups are supported with a field picker. Synthetic tests verify widget appearances, reopen and Undo. Next: complex choice options, push buttons and independent-viewer appearance validation. XFA needs a separate decision. |
| P1 | Annotation editing | Text notes can be edited and browsed across pages; native highlight annotations can be added and deleted. Later page-content edits may flatten them. Next: editable highlight geometry/colors and drawings with preservation through other edits. |
| P1 | Bookmark navigation | Browsing, page navigation, and rename/removal of simple top-level bookmarks are implemented with Undo. Synthetic tests verify retained destinations and refuse nested outlines. Next: nested editing, reorder and preservation checks after page organization. |
| P2 | Search | Stage 4 adds case/whole-word options and a browsable result list. Next: position-highlighted glyphs, optional OCR index and measured bounded search over larger files. |
| P2 | Page tools | Stage 3 adds batch rotate; stage 4 adds a bounded page-label range for documents without existing custom labels. Next: split, editing existing label structures, headers/watermarks and stronger link/bookmark preservation after organization. |
| P2 | Export and accessibility | Image/text export, PDF/A or tagged PDF only with independent conformance validation, structure checks, alt text and reading-order support. |
| P2 | Performance | Validated page count is now cached and updated after edits and Undo/Redo. A synthetic 500-page, 62 KB file showed 100 count reads falling from about 1.7 seconds to about 0.000009 seconds on one Windows 11 x64 machine. Next: async transactional edits, memory budgets and broader large-file measurements before changing the 50 MB/500 page limits. |

Digital signature validation needs a separate trust-store and revocation design. A visual
image stamp is not a digital signature. No change here claims signature validation.

## OCR distribution and measured compatibility

The private review preview now uses an app-scoped Tesseract 5.5.3 executable
compiled from the official tag with pinned static vcpkg dependencies. It
bundles English from tessdata_fast, the PDF config and component notices.
`OCR_SOURCE_BUILD_AUDIT.md` records commits, versions, hashes and imports.
The 55-DLL installer-derived preview is superseded and must remain private.

The exact 41,576,256-byte source-built ZIP was extracted and launched on
Windows 11 25H2, build 26200, x64. The GUI opened a synthetic scan, displayed
the information-loss warning and progress, saved a copy, and the copy
extracted the expected text. The source scan matched the pre-test review
fixture hash afterward. Five OCR tests passed against the exact ZIP's engine.
GitHub Actions tested the Python app on Windows Server 2025 `windows-latest` runners with
Python 3.11 and 3.14; those jobs do not exercise the bundled OCR executable.
No Windows on ARM, Windows 10 or older Windows 11 build has been accepted.

Release gates: independently review every redistributed notice and source
receipt; exercise a clean x64 Windows machine and supported Windows versions;
rerun exact artifact security and UI acceptance; then obtain release approval.
Normal release builds reject `--ocr-bundle` until that gate is changed
deliberately.

## Remaining architecture stages

1. **Source-preserving OCR:** a first bounded export clones simple image-based
   pages and merges Tesseract text-only PDF layers. It rejects forms, signatures,
   existing text, rotations, crop boxes and altered page origins. Synthetic tests
   verify extracted text, pixel-identical rendering at 100%, and retained links,
   bookmarks and metadata. Next: mixed text, rotations, crop boxes, deskew and
   reading-order validation in independent viewers. Keep the rasterized path for
   unsupported inputs. No cloud OCR.
2. **Richer forms:** ordinary radio groups and single-state checkboxes with
   custom on-state names are now supported. Next: multi-select and export/display
   choice options, more complex button appearances and validation in independent
   PDF viewers. XFA is a separate architecture decision because pypdf does not
   provide a complete XFA editing engine.
3. **Accessible output:** define a semantic document model, reading order,
   language and alt-text editor before writing tags. Test against a PDF/UA
   validator and screen readers; do not equate a searchable OCR layer with
   accessible structure. This may require a new writer library or a substantial
   extension to the existing output pipeline. Audit license compatibility
   before adding a runtime dependency.
4. **Native redaction:** evaluate a proven content-rewriting engine that
   removes selected text, image pixels, hidden layers and metadata as
   required, then test with extraction, object inspection and multiple
   viewers. The current pypdf/ReportLab overlay path cannot establish that
   guarantee. Preserve the image-only rasterized export as the bounded
   sensitive-copy option until a native engine passes those tests. Do not
   introduce a copyleft or commercial runtime into this MIT application
   without an explicit license/architecture decision.
5. **Scale and recovery:** measure memory, rendering latency and restart
   behavior on synthetic large files before increasing the 50 MB/500-page
   limits. Keep recovery cleanup user-controlled and test corrupt snapshots.

The remaining work within these stages is planned, not implemented. Signature validation
also requires a separate trust-store and revocation design. A visual stamp
does not establish a digital signature.
