# Third-party components

Original Forge PDF source is MIT. Runtime dependencies retain their respective licenses:

- Python and Tk/Tcl: PSF and Tcl/Tk license terms.
- pypdf: BSD-3-Clause, https://github.com/py-pdf/pypdf
- pypdfium2: Apache-2.0 OR BSD-3-Clause; PDFium and its bundled dependencies retain
  their additional notices, https://github.com/pypdfium2-team/pypdfium2
- Pillow: MIT-CMU/HPND and bundled codec notices, https://github.com/python-pillow/Pillow
- ReportLab: BSD and bundled font notices, https://docs.reportlab.com/
- charset-normalizer: MIT, https://github.com/jawah/charset_normalizer
- PyInstaller bootloader: GPL with its distribution exception,
  https://pyinstaller.org/en/stable/license.html

The Windows build script copies installed package license trees into `licenses/` beside
the executable. Those files, including PDFium third-party notices and Python/Tcl/Tk notices,
must accompany any later binary distribution. Development tools are not application features.

- cryptography: Apache-2.0 OR BSD-3-Clause, including bundled OpenSSL notices.
- cffi and pycparser: MIT/BSD-style notices included in the binary support folder.

Optional offline OCR preview bundle:

- Tesseract 5.5.3 source: Apache-2.0. The reviewed Windows executable and DLLs
  were extracted from UB Mannheim's 5.5.3.20260724 installer, linked from
  upstream package guidance: https://github.com/UB-Mannheim/tesseract/wiki
- English `tessdata_fast` trained model: Apache-2.0,
  https://github.com/tesseract-ocr/tessdata_fast
- The extracted Windows engine also contains Leptonica, ICU, and other native DLLs with
  their own licenses. Inventory and include every required dependency notice before any
  public binary release. Normal release builds reject `--ocr-bundle` until this
  inventory is complete. The current local OCR bundle is a private review preview only.
