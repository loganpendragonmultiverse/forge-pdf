# Third-party components

Original Forge PDF source is MIT. Runtime dependencies retain their respective licenses:

- Python and Tk/Tcl: PSF and Tcl/Tk license terms.
- pypdf: BSD-3-Clause, https://github.com/py-pdf/pypdf
- pypdfium2: Apache-2.0 OR BSD-3-Clause; PDFium and its bundled dependencies retain their additional notices, https://github.com/pypdfium2-team/pypdfium2
- Pillow: MIT-CMU/HPND and bundled codec notices, https://github.com/python-pillow/Pillow
- ReportLab: BSD and bundled font notices, https://docs.reportlab.com/
- charset-normalizer: MIT, https://github.com/jawah/charset_normalizer
- PyInstaller bootloader: GPL with its distribution exception, https://pyinstaller.org/en/stable/license.html
- cryptography: Apache-2.0 OR BSD-3-Clause, including bundled OpenSSL notices.
- cffi and pycparser: MIT/BSD-style notices included in the binary support folder.

The Windows build script copies installed package license trees into `Support/licenses/` beside the executable. Those files, including PDFium third-party notices and Python/Tcl/Tk notices, must accompany any later binary distribution.

## Bundled offline OCR on Windows

The optional app-scoped English OCR bundle is a source-built Tesseract 5.5.3 executable and tessdata_fast model. Tesseract and the model are Apache-2.0. The static image-library graph is Leptonica 1.85.0, giflib 5.2.2, libjpeg-turbo 3.1.2, liblzma 5.8.1, libpng 1.6.50, libwebp 1.6.0, OpenJPEG 2.5.4, libtiff 4.7.1 and zlib 1.3.1. Their source notices are copied to `Support/licenses/ocr/dependencies/`; Tesseract and model licenses are in `Support/licenses/ocr/`.

The MinGW candidate uses GCC 16.2.0 and MinGW-w64 UCRT64. Its linked GCC runtime and C++ library are GPL-3.0-or-later with GCC Runtime Library Exception 3.1. MinGW CRT files use Zope Public License 2.1 and component-specific terms; winpthreads uses MIT and BSD-3-Clause terms. The bundled `Support/licenses/ocr/toolchain/` directory carries the GCC GPL and exception, MinGW CRT notices and winpthreads notice. The compiler and package identities, executable hash, PE imports and link-map inventory are recorded in `OCR_SOURCE_BUILD_AUDIT.md`.

This software is based in part on the work of the Independent JPEG Group. The libjpeg-turbo terms are reproduced in `Support/licenses/ocr/dependencies/libjpeg-turbo.txt`. This distribution includes software developed by the University of California, Berkeley through libtiff's LZW component; the full libtiff and Berkeley notices are reproduced in `Support/licenses/ocr/dependencies/tiff.txt`.

The MinGW executable imports Windows UCRT API-set DLLs and `KERNEL32.dll`. It contains no bundled OCR DLL or MSVC static runtime. The older MSVC and installer-derived OCR previews were private review artifacts and are not distributed.
