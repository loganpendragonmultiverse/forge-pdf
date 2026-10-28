"""Prevent private OCR previews from omitting pinned component notices."""

import pytest
import hashlib
import re

from tools import build_windows


def test_private_ocr_bundle_requires_all_notices(tmp_path, monkeypatch):
    doc = tmp_path / "doc"
    doc.mkdir()
    with pytest.raises(ValueError, match="GCC-COPYING.RUNTIME"):
        build_windows.verify_ocr_notices(tmp_path)
    (doc / "LICENSE").write_text("Tesseract")
    (doc / "tessdata_fast-LICENSE.txt").write_text("tessdata")
    dependency = doc / "dependencies"
    dependency.mkdir()
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
    ):
        (dependency / f"{name}.txt").write_text(name)
    for name in build_windows.OCR_NOTICE_SHA256:
        if name.startswith("toolchain/"):
            target = doc / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(name)
    monkeypatch.setattr(
        build_windows,
        "OCR_NOTICE_SHA256",
        {
            name: hashlib.sha256((doc / name).read_bytes()).hexdigest()
            for name in build_windows.OCR_NOTICE_SHA256
        },
    )
    build_windows.verify_ocr_notices(tmp_path)
    (dependency / "liblzma.txt").write_text("changed")
    with pytest.raises(ValueError, match="liblzma.txt"):
        build_windows.verify_ocr_notices(tmp_path)
    (dependency / "liblzma.txt").write_text("liblzma")
    (dependency / "openjpeg.txt").unlink()
    with pytest.raises(ValueError, match="openjpeg.txt"):
        build_windows.verify_ocr_notices(tmp_path)


def test_private_ocr_bundle_rejects_extra_dll_and_changed_engine(tmp_path, monkeypatch):
    doc = tmp_path / "doc"
    doc.mkdir()
    for name in build_windows.OCR_NOTICE_SHA256:
        target = doc / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(name)
    monkeypatch.setattr(
        build_windows,
        "OCR_NOTICE_SHA256",
        {
            name: hashlib.sha256(name.encode()).hexdigest()
            for name in build_windows.OCR_NOTICE_SHA256
        },
    )
    for name, content, constant in (
        ("tesseract.exe", b"engine", "OCR_ENGINE_SHA256"),
        ("tessdata/eng.traineddata", b"model", "ENGLISH_SHA256"),
        ("tessdata/configs/pdf", b"config", "OCR_CONFIG_SHA256"),
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        monkeypatch.setattr(build_windows, constant, hashlib.sha256(content).hexdigest())
    build_windows.verify_ocr_bundle(tmp_path)
    (tmp_path / "unexpected.dll").write_bytes(b"unreviewed")
    with pytest.raises(ValueError, match="Unexpected OCR DLL"):
        build_windows.verify_ocr_bundle(tmp_path)
    (tmp_path / "unexpected.dll").unlink()
    (tmp_path / "doc" / "nested.dll").write_bytes(b"unreviewed")
    with pytest.raises(ValueError, match="Unexpected OCR DLL"):
        build_windows.verify_ocr_bundle(tmp_path)
    (tmp_path / "doc" / "nested.dll").unlink()
    (tmp_path / "tesseract.exe").write_bytes(b"changed")
    with pytest.raises(ValueError, match="tesseract.exe"):
        build_windows.verify_ocr_bundle(tmp_path)


def test_private_ocr_bundle_requires_mingw_toolchain_notices(tmp_path):
    for name in (
        "toolchain/GCC-COPYING.RUNTIME",
        "toolchain/GCC-COPYING3",
        "toolchain/MinGW-CRT-COPYING",
        "toolchain/MinGW-CRT-Mingw.txt",
        "toolchain/MinGW-CRT-runtime.txt",
        "toolchain/Winpthreads-COPYING",
    ):
        assert name in build_windows.OCR_NOTICE_SHA256
        with pytest.raises(ValueError, match=name.split("/")[-1]):
            build_windows.verify_ocr_notices(tmp_path)


def test_private_ocr_pins_are_sha256_hex_digests():
    pins = {
        "engine": build_windows.OCR_ENGINE_SHA256,
        "model": build_windows.ENGLISH_SHA256,
        "config": build_windows.OCR_CONFIG_SHA256,
        **build_windows.OCR_NOTICE_SHA256,
    }
    for name, digest in pins.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"Invalid SHA-256 pin: {name}"
