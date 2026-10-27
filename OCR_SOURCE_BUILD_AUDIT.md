# Source-built Windows OCR candidate (private review)

The private source-built OCR preview uses Tesseract 5.5.3, compiled on Windows 11
with the preinstalled Visual Studio 2022 Build Tools 17.14/MSVC 14.44.35207.
The Tesseract source is the official tag `5.5.3`, commit
`db0ec62f81b0737fbbe184d8fea40af5738f8eef`. Dependencies came from
the Microsoft vcpkg registry at baseline
`3af1d1e60af2b2abf55760538cd607829029b07a`, using
`x64-windows-static`, Leptonica with default features disabled, and
`WIN32_MT_BUILD=ON`. Tesseract training tools, curl, archive and graphics
features were disabled. This is an isolated application build, not a
system-wide installation.

Pinned dependency versions: giflib 5.2.2, libjpeg-turbo 3.1.2, Leptonica
1.85.0, liblzma 5.8.1, libpng 1.6.50, libwebp 1.6.0, OpenJPEG 2.5.4,
libtiff 4.7.1 and zlib 1.3.1. The private bundle contains each dependency's
vcpkg copyright notice under `doc/dependencies/`, Tesseract's license,
and the tessdata_fast license. The English model is from official
`tessdata_fast` commit `87416418657359cb625c412a48b6e1d6d41c29bd`,
SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.

The resulting `tesseract.exe` is 5,341,696 bytes, SHA-256
`2df0d8207b34b59dd95f93c0e5cda5eae8d626519d4dc7206a899cc23a82c5b8`.
`dumpbin /dependents` reports only `KERNEL32.dll`; no external native
DLLs or C++ redistributable are required by this executable. The bundle
has 14 files totalling 9,502,965 bytes. `tesseract --version` reports
5.5.3 and all five synthetic OCR tests passed against this bundle on
Windows.

This evidence does not certify legal redistribution or all target Windows
versions. Keep the candidate private until the complete packaged app is
tested, notices are independently reviewed, and the release gate is approved.
The older UB Mannheim installer-derived preview with 55 DLLs remains
private and must not be published.

## Rebuild inputs

The vcpkg manifest is `tools/ocr-vcpkg.json`. Build the official Tesseract
tag with CMake's Visual Studio 2022 x64 generator, the vcpkg toolchain and
triplet `x64-windows-static`, setting `WIN32_MT_BUILD=ON`,
`BUILD_TRAINING_TOOLS=OFF`, `GRAPHICS_DISABLED=ON`,
`DISABLE_ARCHIVE=ON` and `DISABLE_CURL=ON`. Install the Release target
into a temporary staging directory. Package only its `tesseract.exe`,
the pinned English model, PDF config and the licenses described above.
The manifest and source pins are build inputs; the binary itself is not
checked into Git.
