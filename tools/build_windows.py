"""Build a portable directory and retain dependency notices alongside it."""

import argparse
import importlib.metadata as metadata
import shutil
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


ENGLISH_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"


def verify_ocr_notices(ocr_bundle: Path) -> None:
    required = [
        "LICENSE",
        "tessdata_fast-LICENSE.txt",
        *(
            f"dependencies/{name}.txt"
            for name in (
                "giflib",
                "leptonica",
                "libjpeg-turbo",
                "liblzma",
                "libpng",
                "libwebp",
                "openjpeg",
                "tiff",
                "zlib",
            )
        ),
    ]
    missing = [name for name in required if not (ocr_bundle / "doc" / name).is_file()]
    if missing:
        raise ValueError(f"OCR bundle is missing required notices: {', '.join(missing)}")


def add_support(destination: Path, ocr_bundle: Path | None = None):
    support = destination / "Support"
    support.mkdir(exist_ok=True)
    for name in [
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "OCR_SOURCE_BUILD_AUDIT.md",
        "SECURITY.md",
        "TESTING.md",
        "DEVELOPMENT.md",
        "CHANGELOG.md",
    ]:
        shutil.copy2(ROOT / name, support / name)
    shutil.copytree(ROOT / "examples", support / "examples", dirs_exist_ok=True)
    licenses = support / "licenses"
    licenses.mkdir(exist_ok=True)
    for package in [
        "pypdf",
        "pypdfium2",
        "Pillow",
        "reportlab",
        "charset-normalizer",
        "pyinstaller",
        "cryptography",
        "cffi",
        "pycparser",
    ]:
        dist = metadata.distribution(package)
        for file in dist.files or []:
            if any(
                word in str(file).lower() for word in ["license", "copyright", "notice", "copying"]
            ):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses / package / str(file).replace("../", "").replace("..\\", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    tclroot = Path(sys.base_prefix) / "tcl"
    for source in tclroot.rglob("*"):
        if source.is_file() and source.name.lower() in ("license.terms", "license", "license.txt"):
            target = licenses / "tcl-tk" / source.relative_to(tclroot)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if ocr_bundle is not None:
        model = ocr_bundle / "tessdata" / "eng.traineddata"
        if hashlib.sha256(model.read_bytes()).hexdigest() != ENGLISH_SHA256:
            raise ValueError("OCR English model does not match the pinned checksum.")
        if not (ocr_bundle / "tesseract.exe").is_file():
            raise ValueError("OCR engine is missing.")
        ocr_target = support / "ocr"
        ocr_target.mkdir()
        for source in ocr_bundle.glob("*.dll"):
            shutil.copy2(source, ocr_target / source.name)
        shutil.copy2(ocr_bundle / "tesseract.exe", ocr_target / "tesseract.exe")
        (ocr_target / "tessdata").mkdir()
        shutil.copy2(model, ocr_target / "tessdata" / model.name)
        (ocr_target / "tessdata" / "configs").mkdir()
        shutil.copy2(
            ocr_bundle / "tessdata" / "configs" / "pdf",
            ocr_target / "tessdata" / "configs" / "pdf",
        )
        verify_ocr_notices(ocr_bundle)
        shutil.copytree(ocr_bundle / "doc", licenses / "ocr", dirs_exist_ok=True)
        shutil.copy2(
            ROOT / "tools" / "notices" / "liblzma-COPYING.0BSD.txt",
            licenses / "ocr" / "dependencies" / "liblzma-COPYING.0BSD.txt",
        )


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows preview on Windows.")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview", action="store_true", help="Build a separately named local preview"
    )
    parser.add_argument("--ocr-bundle", type=Path, help="Verified app-scoped OCR binary folder")
    args = parser.parse_args()
    if args.ocr_bundle and not args.preview:
        raise SystemExit(
            "Bundled OCR is limited to review previews until source-build notices, "
            "compatibility, and release approval are verified."
        )
    name = "Forge PDF Preview" if args.preview else "Forge PDF"
    archive_name = "Forge-PDF-Preview-Windows" if args.preview else "Forge-PDF-1.2.0-Windows"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--windowed",
            "--name",
            name,
            "--collect-all",
            "pypdfium2",
            "--collect-all",
            "pypdfium2_raw",
            "--collect-all",
            "reportlab",
            str(ROOT / "tools" / "desktop_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    add_support(ROOT / "dist" / name, args.ocr_bundle)
    archive = shutil.make_archive(str(ROOT / "dist" / archive_name), "zip", ROOT / "dist", name)
    print(archive)


if __name__ == "__main__":
    main()
