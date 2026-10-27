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

Optional offline OCR source-built private preview bundle:

- Tesseract 5.5.3 source: Apache-2.0,
  https://github.com/tesseract-ocr/tesseract
- English `tessdata_fast` trained model: Apache-2.0,
  https://github.com/tesseract-ocr/tessdata_fast
- Static dependency sources: Leptonica 1.85.0, giflib 5.2.2,
  libjpeg-turbo 3.1.2, liblzma 5.8.1, libpng 1.6.50, libwebp 1.6.0,
  OpenJPEG 2.5.4, libtiff 4.7.1 and zlib 1.3.1. Each component's
  copyright/license text is copied to `Support/licenses/ocr/dependencies/`.
  Tesseract's and tessdata_fast's notices are in `Support/licenses/ocr/`.
  Source pins, hashes and build settings are in `OCR_SOURCE_BUILD_AUDIT.md`.
- This software is based in part on the work of the Independent JPEG Group.
  The libjpeg-turbo terms are reproduced in
  `Support/licenses/ocr/dependencies/libjpeg-turbo.txt`.
- This distribution includes software developed by the University of
  California, Berkeley, through libtiff's LZW component. The full libtiff
  and Berkeley notices are reproduced in
  `Support/licenses/ocr/dependencies/tiff.txt`.
- The source-built executable imports only the Windows system DLL
  `KERNEL32.dll`; no UB Mannheim or ICU DLL is in the new preview.
  The older installer-derived 55-DLL preview is superseded, retained only
  as a private review artifact and must not be publicly distributed.
  Normal release builds reject `--ocr-bundle` until the independent
  notice and compatibility gates are complete.
