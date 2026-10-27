"""Prevent private OCR previews from omitting pinned component notices."""

import pytest

from tools.build_windows import verify_ocr_notices


def test_private_ocr_bundle_requires_all_notices(tmp_path):
    doc = tmp_path / "doc"
    doc.mkdir()
    with pytest.raises(ValueError, match="tessdata_fast-LICENSE.txt"):
        verify_ocr_notices(tmp_path)
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
    verify_ocr_notices(tmp_path)
    (dependency / "openjpeg.txt").unlink()
    with pytest.raises(ValueError, match="openjpeg.txt"):
        verify_ocr_notices(tmp_path)
