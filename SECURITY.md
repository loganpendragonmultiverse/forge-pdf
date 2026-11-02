# Security

Only open PDFs you trust. PDFium and PDF parsers process complex native/binary data;
this application is not a security sandbox. Keep dependency versions current.

Whiteout covers content visually. It leaves underlying content extractable and is not
appropriate for removing secrets. Rasterized redacted export removes source PDF objects from a new image-only copy,
but it loses searchability, links, forms and accessibility structure. Original
files and earlier sessions or recovery copies can still contain the material.

Work is held in memory. Save writes a temporary sibling file, then places the output.
New copies are published atomically after writing. Originals are protected.
An optional local recovery snapshot can be enabled for the current document; it
does not contain Undo history and must be managed by the user. Closing with edits prompts to save or discard.

No telemetry, uploads, cloud accounts, or background network functions are implemented.
Do not post sensitive PDFs in bug reports. Report vulnerabilities privately through
https://github.com/loganpendragonmultiverse/forge-pdf/security/advisories/new.
