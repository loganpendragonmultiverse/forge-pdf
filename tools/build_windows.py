"""Build a portable directory and retain dependency notices alongside it."""

import argparse
import importlib.metadata as metadata
import shutil
import hashlib
import os
import subprocess
import sys
import tkinter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


ENGLISH_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
OCR_ENGINE_SHA256 = "8d6d753e54c31b9cdd938328a5f0f6e5ad076bb78a74bc6a22da4e6bf667913f"
OCR_CONFIG_SHA256 = "88630f865cdaa38ce52ad1688f51ed55596f125f85536ec29b1b11fed721545b"
OCR_NOTICE_SHA256 = {
    "toolchain/GCC-COPYING.RUNTIME": "9d6b43ce4d8de0c878bf16b54d8e7a10d9bd42b75178153e3af6a815bdc90f74",
    "toolchain/GCC-COPYING3": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
    "toolchain/MinGW-CRT-COPYING": "99a69660981156c21336fdb5661f89341b013c94e4bf9e1c7467b4745718397f",
    "toolchain/MinGW-CRT-Mingw.txt": "f38e6194bd3bfa1b654f118e5acefe0aead437bbe669eee43957ccc65a7127f1",
    "toolchain/MinGW-CRT-runtime.txt": "1db8da07b436c68833c0673ffee3d9fcb2526047f3820b81661865dfedc79a1f",
    "toolchain/Winpthreads-COPYING": "63263614cdd29f2f93cba85e992f041b31f9fc7b4033692f31269489a8a1b177",
    "LICENSE": "3ddf9be5c28fe27dad143a5dc76eea25222ad1dd68934a047064e56ed2fa40c5",
    "tessdata_fast-LICENSE.txt": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "dependencies/giflib.txt": "0c9b7990ecdca88b676db232c226548ac408b279f550d424d996f0d83591dd8e",
    "dependencies/leptonica.txt": "87829abb5bbb00b55a107365da89e9a33f86c4250169e5a1e5588505be7d5806",
    "dependencies/libjpeg-turbo.txt": "2189dc45a8fe96204069f8124caa53a148dfdc193f50f584c6ca7849a6072872",
    "dependencies/liblzma.txt": "616a3ad264ce29b8f1cb97e53037b139d406899ca8d1f799651e17bfa09830b8",
    "dependencies/libpng.txt": "16d9daaafbf63a31a5bdc91d4600972548fef5aaa1244202393288dbd079c49a",
    "dependencies/libwebp.txt": "050b5ba2c8eb0bd3b996e12ef79312a1c62237f2de1b3c609843f00bb74744f3",
    "dependencies/openjpeg.txt": "a6af136f3e15038a666b61f376612a07d9a4e48cb7c01adbf3e33b3f14ab49b6",
    "dependencies/tiff.txt": "0e27c2382d7b8147972bbb746e04059a1152c8d0fda9d03ef1399d1a433c4ade",
    "dependencies/zlib.txt": "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243",
}


def verify_ocr_notices(ocr_bundle: Path) -> None:
    missing = [name for name in OCR_NOTICE_SHA256 if not (ocr_bundle / "doc" / name).is_file()]
    if missing:
        raise ValueError(f"OCR bundle is missing required notices: {', '.join(missing)}")
    for name, digest in OCR_NOTICE_SHA256.items():
        if hashlib.sha256((ocr_bundle / "doc" / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"OCR notice does not match the pinned source build: {name}")


def verify_ocr_bundle(ocr_bundle: Path) -> None:
    verify_ocr_notices(ocr_bundle)
    if list(ocr_bundle.rglob("*.dll")):
        raise ValueError("Unexpected OCR DLL; only the audited static engine is allowed.")
    for name, digest in (
        ("tesseract.exe", OCR_ENGINE_SHA256),
        ("tessdata/eng.traineddata", ENGLISH_SHA256),
        ("tessdata/configs/pdf", OCR_CONFIG_SHA256),
    ):
        target = ocr_bundle / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"OCR bundle file does not match the pinned source build: {name}")


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
        verify_ocr_bundle(ocr_bundle)
        model = ocr_bundle / "tessdata" / "eng.traineddata"
        ocr_target = support / "ocr"
        ocr_target.mkdir()
        shutil.copy2(ocr_bundle / "tesseract.exe", ocr_target / "tesseract.exe")
        (ocr_target / "tessdata").mkdir()
        shutil.copy2(model, ocr_target / "tessdata" / model.name)
        (ocr_target / "tessdata" / "configs").mkdir()
        shutil.copy2(
            ocr_bundle / "tessdata" / "configs" / "pdf",
            ocr_target / "tessdata" / "configs" / "pdf",
        )
        shutil.copytree(ocr_bundle / "doc", licenses / "ocr", dirs_exist_ok=True)
        shutil.copy2(
            ROOT / "tools" / "notices" / "liblzma-COPYING.0BSD.txt",
            licenses / "ocr" / "dependencies" / "liblzma-COPYING.0BSD.txt",
        )


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this Windows preview on Windows.")
    try:
        tkinter.Tcl().eval("info patchlevel")
    except tkinter.TclError as exc:
        raise SystemExit(f"Tcl/Tk is unavailable; Windows preview build stopped: {exc}") from exc
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview", action="store_true", help="Build a separately named local preview"
    )
    parser.add_argument("--ocr-bundle", type=Path, help="Verified app-scoped OCR binary folder")
    args = parser.parse_args()
    name = "Forge PDF Preview" if args.preview else "Forge PDF"
    archive_name = "Forge-PDF-Preview-Windows" if args.preview else "Forge-PDF-1.3.0-Windows"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--windowed",
            "--name",
            name,
            "--paths",
            str(ROOT / "src"),
            "--collect-all",
            "pypdfium2",
            "--collect-all",
            "pypdfium2_raw",
            "--collect-all",
            "reportlab",
            str(ROOT / "tools" / "desktop_entry.py"),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""),
        },
        check=True,
    )
    add_support(ROOT / "dist" / name, args.ocr_bundle)
    archive = shutil.make_archive(str(ROOT / "dist" / archive_name), "zip", ROOT / "dist", name)
    print(archive)


if __name__ == "__main__":
    main()
