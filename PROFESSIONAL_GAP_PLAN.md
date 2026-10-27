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

1. Fill existing editable AcroForm text, simple choice and Yes/Off checkbox fields, with
   a field picker. XFA, radio groups, custom checkbox states and signature fields remain
   unsupported.
2. Edit common document metadata; add and browse bookmarks; add, edit, delete and browse
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
| P1 | OCR | Stage 5 adds bounded offline English searchable image-copy export with an app-scoped engine. Synthetic scanned text extracts. Next: portable UI acceptance, selectable languages, source-preserving text layers, progress/cancel, and native DLL license inventory. No document upload. |
| P1 | Full forms | Existing text, simple choice and Yes/Off checkbox fields are supported with a field picker in stages 3–4. Next: complex choice options, custom button states, radio groups and appearance validation in independent viewers. XFA needs a separate decision. |
| P1 | Annotation editing | Text notes can be edited and browsed across pages; native highlight annotations can be added and deleted. Later page-content edits may flatten them. Next: editable highlight geometry/colors and drawings with preservation through other edits. |
| P1 | Bookmark navigation | Stage 3 adds browsing and page navigation. Next: rename, reorder and delete outline items; preserve destinations during page edits. |
| P2 | Search | Stage 4 adds case/whole-word options and a browsable result list. Next: position-highlighted glyphs, optional OCR index and measured bounded search over larger files. |
| P2 | Page tools | Stage 3 adds batch rotate; stage 4 adds a bounded page-label range for documents without existing custom labels. Next: split, editing existing label structures, headers/watermarks and stronger link/bookmark preservation after organization. |
| P2 | Export and accessibility | Image/text export, PDF/A or tagged PDF only with independent conformance validation, structure checks, alt text and reading-order support. |
| P2 | Performance | Async transactional edits with cancellation, memory budgets and measured large-file behavior before changing the 50 MB/500 page limits. |

Digital signature validation needs a separate trust-store and revocation design. A visual
image stamp is not a digital signature. No change here claims signature validation.

## Offline OCR dependency decision

The approved review preview contains an app-scoped Tesseract engine and English model.
It does not install Tesseract system-wide. Tesseract is [Apache-2.0 licensed](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE).
[OCRmyPDF's Windows instructions](https://ocrmypdf.readthedocs.io/en/latest/installation.html)
call for a separate Tesseract installation and recommend Ghostscript for some PDF/A flows.
Recommendation: use the [official Tesseract 5.5.3 Windows release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3)
as an app-scoped engine with its required runtime DLLs and `tessdata_fast` English model,
rather than requiring a machine-wide third-party installation. The official Windows
installer asset is 26,573,224 bytes (about 26.6 MB decimal). The
[English traineddata](https://github.com/tesseract-ocr/tessdata_fast) is 4,113,088 bytes
(about 4.1 MB); optional French, German and Spanish models are roughly 1.1, 1.5 and
2.3 MB respectively. These are asset sizes before final ZIP compression and bundled
DLL/license accounting. The current OCR review ZIP is 77,559,819 bytes. English is the
only bundled language; optional language selection requires further implementation.
Both the engine and fast models are Apache-2.0; retain their notices and review licenses
of every packaged DLL.

The approved app-scoped preview passed a synthetic scanned text extraction test. Before
release, complete native DLL license inventory and add progress/cancel controls. The
current export is a rasterized searchable image copy, so source PDF structure is lost.
Keep
Ghostscript out of the default runtime until a specific export need and licensing review
justify it. No PDF content should be sent to a remote OCR service.
