# Security

Only open PDFs you trust. PDFium and PDF parsers process complex native/binary data;
this application is not a security sandbox. Keep dependency versions current.

Whiteout covers content visually. It leaves underlying content extractable and is not
appropriate for removing secrets. There is no secure-redaction feature in this release.

Work is held in memory. Save writes a temporary sibling file, then places the output.
A crash during a first-time write can leave a partial new output; originals are protected.
There is no autosave or recovery journal. Closing with edits prompts to save or discard.

No telemetry, uploads, cloud accounts, or background network functions are implemented.
Do not post sensitive PDFs in bug reports. Report vulnerabilities privately through
https://github.com/loganpendragonmultiverse/forge-pdf/security/advisories/new.
