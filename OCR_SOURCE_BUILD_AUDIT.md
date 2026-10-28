# Source-built Windows OCR engine

The Windows release engine replaces only the optional app-scoped OCR executable. It uses the official Tesseract 5.5.3 tag at commit `db0ec62f81b0737fbbe184d8fea40af5738f8eef` and the official tessdata_fast English model at commit `87416418657359cb625c412a48b6e1d6d41c29bd`. The model SHA-256 is `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. The PDF config SHA-256 is `88630f865cdaa38ce52ad1688f51ed55596f125f85536ec29b1b11fed721545b`.

## Isolated MinGW build

The official MSYS2 archive `msys2-base-x86_64-20260927.tar.zst` had SHA-256 `8a2095647afbf799d113d0cae35f7544589d059819042635504e75bd2179bd02`, matching its official release digest. It was extracted to a temporary directory without changing system defaults. Its signed UCRT64 packages supplied GCC 16.2.0-6, MinGW CRT/headers/libwinpthread `14.0.0.r569.g34eeafb7d-1`, CMake 4.4.4-4 and Ninja 1.13.2-1.

The existing vcpkg registry baseline `3af1d1e60af2b2abf55760538cd607829029b07a` and triplet `x64-mingw-static` built Leptonica 1.85.0 with default features off. The installed package graph included giflib 5.2.2, libjpeg-turbo 3.1.2, liblzma 5.8.1, libpng 1.6.50, libwebp 1.6.0, OpenJPEG 2.5.4, libtiff 4.7.1 and zlib 1.3.1. vcpkg CMake helpers were build-time tools.

Tesseract was configured Release with training tools, graphics, curl, libarchive, OpenMP, LTO and native CPU tuning disabled. The executable was linked with `-static -static-libgcc -static-libstdc++`. The resulting `tesseract.exe` is 13,176,231 bytes, SHA-256 `8d6d753e54c31b9cdd938328a5f0f6e5ad076bb78a74bc6a22da4e6bf667913f`. Its PE imports are `KERNEL32.dll` and Windows `api-ms-win-crt-*` API sets. No OCR, GCC, MinGW or MSVC runtime DLL is bundled or imported. The linker map SHA-256 is `b4c3dfc531c1bfa6010cef5051ff2517d6de3284721bace7570e5578ece959d3`; it names static `libgcc.a`, `libgcc_eh.a`, `libstdc++.a`, MinGW CRT, `libpthread.a` and the image libraries above. `libmsvcrt.a` appears as an import archive in the map, but the PE does not import `msvcrt.dll`.

The candidate includes pinned upstream notices for Tesseract, tessdata_fast, all nine image-library packages, GCC GPL and Runtime Library Exception, MinGW CRT and winpthreads. The build script verifies each file's SHA-256 and rejects any OCR DLL at any depth. The standalone OCR folder has no OCR DLL. The GCC Runtime Library Exception and MSYS2 package license declarations are evidence for this route; the complete notice set and pinned hashes are packaged with the Windows release.

## Review evidence and acceptance

The private engine bundle is Library file `libfile_06ee09fcc4f08191b2d05961a7c42acf`, version 0, SHA-256 `24d2cbba90a0b437c20a5d2ee2995f912e6a535fb5951ed869ab5e7911f36cd4`. Build logs, exact installed status and ABI inventory, CMake cache, link map and PE imports are Library file `libfile_173ab7bdd49c8191a4a4023c8aad4dfc`, version 0, SHA-256 `e7dd782e18bb187526c8f2dee8c20ea61a26f9676b7530a60e1e4cfd945fd35b`. The companion review report is Library file `libfile_48efede3a8448191bf7aa5ee6ee6de2b`, version 0.

On one Windows 11 x64 device, the standalone engine converted a synthetic image to a searchable PDF containing `FORGE OCR SAMPLE`. An isolated copy of the existing packaged Forge PDF preview, with only its OCR executable replaced, opened an image-only synthetic PDF and saved an OCR image copy. Independent pypdf readback found no source text and extracted `FORGE OCR SAMPLE` from the output; the original file hash stayed unchanged. This validates that packaged image-copy OCR path, not source-preserving OCR, forms, highlights, other Windows versions or accessibility. The existing private preview ZIP remains intact.

The prior MSVC static-runtime executable, SHA-256 `2df0d8207b34b59dd95f93c0e5cda5eae8d626519d4dc7206a899cc23a82c5b8`, is a historical private candidate. Its Build Tools redistribution evidence gap motivated this alternative. The older installer-derived 55-DLL preview is also superseded and private.

## v1.3.0 release evidence and limits

The exact draft-head Windows preview at commit `699dd305d652fd88f9b92a2b83ad154cc97fce89` built and launched on one Windows 11 x64 device. Its ZIP SHA-256 is `2a48866eb55173462699a74fd8762a47e18c9e5e0df0b6055919e89b4bd79d55`. Four packaging tests and 28 focused form, native-highlight and OCR model tests passed; eight OCR integration tests passed against the engine extracted from this ZIP. The packaged form picker toggled a synthetic checkbox and changed a choice field to Gold in the visible app. These are bounded checks; Windows 10, ARM, arbitrary PDFs, independent viewer acceptance, screen readers and hostile-document isolation remain unverified. The tagged release artifact and public download must be checked separately against the tagged commit.

The vendored `vendor/ocr-bundle.zip` is the exact 6,999,972-byte source-built engine/model/notice bundle with SHA-256 `24d2cbba90a0b437c20a5d2ee2995f912e6a535fb5951ed869ab5e7911f36cd4`. The build extracts it and rechecks executable, model, config and notice SHA-256 digests before packaging. No OCR DLL is permitted. The Windows release distributes GCC GPL and Runtime Library Exception, MinGW CRT component terms and winpthreads notice alongside the nine image-library and Tesseract/model notices.
