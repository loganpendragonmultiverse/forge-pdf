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


## Link and toolset evidence

The task-local build evidence archive retains the vcpkg installed-status
records with package ABI hashes, `tesseract.vcxproj`, the Release linker
command and the exact import list. The linker command names static
`TIFF.LIB`, `LZMA.LIB`, `JPEG.LIB`, `ZLIB.LIB`,
`LEPTONICA-1.85.0.LIB`, `GIF.LIB`, `OPENJP2.LIB`,
`LIBPNG16.LIB`, `LIBWEBPMUX.LIB`, `LIBWEBP.LIB` and
`LIBSHARPYUV.LIB` (with some repeated inputs). Thus liblzma is not
merely installed: TIFF's default LZMA feature brought it into the link.
The two vcpkg CMake helper packages are build-time tools, not runtime
libraries. The source-built package notices include every named static
dependency.

Release C and C++ projects used the MSVC `MultiThreaded` runtime setting
(`/MT`) from toolset 14.44.35207, and the executable has no imported
VC runtime DLL. Static linking still includes Microsoft runtime code;
redistribution is subject to the installed Visual Studio license terms.
Microsoft's [CRT library documentation](https://learn.microsoft.com/en-us/cpp/c-runtime-library/crt-library-features?view=msvc-170)
describes the static libraries and Windows UCRT relationship. This
audit records the toolset and leaves the applicable license determination
as an independent release gate; it does not infer permission solely from
the DLL import list.


## Exact private preview acceptance

The final review ZIP is 41,576,256 bytes, SHA-256
`e9339c98f1c250fa2ffd6367855bfdcb579791f35bdecef362a55bf4b32fe61a`.
It includes this audit, `THIRD_PARTY_NOTICES.md`, the Tesseract and
tessdata_fast licenses, and nine static dependency copyright files.
The extracted bundle contains no OCR DLLs. The extracted engine's SHA-256
matches the source-built executable above, and five synthetic OCR tests
passed against this exact ZIP.

On Windows 11 25H2 build 26200 x64, the exact extracted portable app
opened a synthetic image-only PDF, displayed the OCR loss warning and
progress, and saved a one-page searchable copy. Independent pypdf text
extraction returned `FORGE OCR SAMPLE`. The source PDF SHA-256 remained
`142a1f056fde6e0cebd0a06f1cc56756bb058ec0bfa0f06084988758a191da4ca`,
matching the pre-test review fixture. Code inspection found no HTTP/socket
upload call in the Forge PDF source; OCR invokes the bundled local executable.
No packet-level network capture was performed. The CI app tests ran on
Windows Server 2025 with Python 3.11 and 3.14, but did not execute this
bundled OCR binary. Other Windows versions and architectures are untested.
