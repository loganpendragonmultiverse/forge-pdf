"""Transactional PDF edits. Originals are never written by this module."""

from __future__ import annotations

import io
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable
from zipfile import ZipFile, ZIP_DEFLATED

import pypdfium2 as pdfium
from PIL import ImageDraw
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.annotations import Highlight as PdfHighlight, Text as TextNote
from pypdf.constants import PageLabelStyle
from pypdf.generic import ArrayObject, FloatObject, NameObject, RectangleObject, TextStringObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .enhancements import serialized_pdfium, stamp_image, text_font, fit_stamp_size

MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 500
HISTORY_BYTES = 100 * 1024 * 1024
PAGE_SIZES = {
    "Letter": (612, 792),
    "A4": (595.28, 841.89),
    "Legal": (612, 1008),
    "A5": (419.53, 595.28),
}
DRAW_TOOLS = ("rectangle", "filled rectangle", "ellipse", "filled ellipse", "line", "arrow")


def read_pdf(data: bytes) -> PdfReader:
    if len(data) > MAX_BYTES:
        raise ValueError("Forge PDF supports PDFs up to 50 MB.")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs must be opened through Open PDF before editing.")
    if not 0 < len(reader.pages) <= MAX_PAGES:
        raise ValueError("Please use a PDF containing 1 to 500 pages.")
    return reader


def serialize(writer: PdfWriter) -> bytes:
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def parse_page_ranges(selection: str, page_count: int) -> list[int]:
    """Return zero-based indices in the user's explicit order; reject duplicates."""
    indices: list[int] = []
    seen: set[int] = set()
    if len(selection) > 8192:
        raise ValueError("The page selection is too long.")
    for part in selection.split(","):
        match = re.fullmatch(r"\s*([0-9]+)(?:\s*-\s*([0-9]+))?\s*", part)
        if not match:
            raise ValueError("Use one-based pages and ascending ranges, for example 1,3-5.")
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= page_count:
            raise ValueError(f"Choose ascending page ranges within 1 to {page_count}.")
        for number in range(first, last + 1):
            if number in seen:
                raise ValueError("Select each page only once; duplicate pages are not allowed.")
            seen.add(number)
            indices.append(number - 1)
    return indices


def visible_page(page):
    left, bottom = float(page.cropbox.left), float(page.cropbox.bottom)
    right, top = float(page.cropbox.right), float(page.cropbox.top)
    rotation = page.rotation % 360
    width, height = right - left, top - bottom
    if rotation in (90, 270):
        width, height = height, width
    # Map visible-page overlay coordinates back into the original PDF space.
    # Existing content, link rectangles, crop boxes and rotation stay untouched.
    matrices = {
        0: (1, 0, 0, 1, left, bottom),
        90: (0, 1, -1, 0, right, bottom),
        180: (-1, 0, 0, -1, right, top),
        270: (0, -1, 1, 0, left, top),
    }
    return width, height, Transformation(matrices[rotation])


class Document:
    def __init__(self, data: bytes, source: Path | None = None):
        reader = read_pdf(data)
        self.data = data
        self._page_count = len(reader.pages)
        self.saved = data
        self.opened_encrypted = False
        self.sources = {source.resolve()} if source else set()
        self.source_identities = set()
        if source and source.exists():
            stat = source.stat()
            self.source_identities.add((stat.st_dev, stat.st_ino))
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []

    @classmethod
    def blank(cls, count: int, paper: str, landscape: bool = False) -> Document:
        if type(count) is not int or not 1 <= count <= MAX_PAGES or paper not in PAGE_SIZES:
            raise ValueError("Choose a paper size and 1 to 500 pages.")
        dimensions = PAGE_SIZES[paper]
        width, height = dimensions[::-1] if landscape else dimensions
        writer = PdfWriter()
        for _ in range(count):
            writer.add_blank_page(width, height)
        document = cls(serialize(writer))
        document.saved = b""
        return document

    @classmethod
    def from_images(cls, paths: list[Path]) -> Document:
        if not 1 <= len(paths) <= 20:
            raise ValueError("Choose 1 to 20 PNG or JPEG files.")
        writer = PdfWriter()
        sources = set()
        identities = set()
        total_bytes = 0
        for path in paths:
            path = path.resolve()
            info = path.stat()
            sources.add(path)
            identities.add((info.st_dev, info.st_ino))
            image = stamp_image(path, orient=True)
            dimensions = PAGE_SIZES["Letter"]
            width, height = dimensions[::-1] if image.width > image.height else dimensions
            image.thumbnail((round(width * 2), round(height * 2)))
            stream = io.BytesIO()
            canvas = Canvas(stream, pagesize=(width, height))
            draw_width, draw_height = fit_stamp_size(image.size, width - 36, height - 36)
            canvas.drawImage(
                ImageReader(image),
                (width - draw_width) / 2,
                (height - draw_height) / 2,
                draw_width,
                draw_height,
                mask="auto",
            )
            canvas.save()
            image.close()
            total_bytes += stream.tell()
            if total_bytes > MAX_BYTES:
                raise ValueError("The generated pages exceed 50 MB. Select fewer images.")
            writer.add_page(PdfReader(stream).pages[0])
        document = cls(serialize(writer))
        document.saved = b""
        document.sources = sources
        document.source_identities = identities
        return document

    @classmethod
    def open(cls, path: Path, password: str | None = None) -> Document:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Forge PDF supports PDFs up to 50 MB.")
        data = path.read_bytes()
        reader = PdfReader(io.BytesIO(data))
        encrypted = reader.is_encrypted
        if encrypted:
            if not reader.decrypt(password or ""):
                raise ValueError("Password required or incorrect password.")
            data = serialize(PdfWriter(clone_from=reader))
        document = cls(data, path)
        document.opened_encrypted = encrypted
        return document

    @property
    def count(self) -> int:
        return self._page_count

    @property
    def dirty(self) -> bool:
        return self.data != self.saved

    def writer(self) -> PdfWriter:
        return PdfWriter(clone_from=io.BytesIO(self.data))

    def commit(self, writer: PdfWriter) -> None:
        candidate = serialize(writer)
        reader = read_pdf(candidate)
        self.undo_stack.append(self.data)
        while len(self.undo_stack) > 30 or sum(map(len, self.undo_stack)) > HISTORY_BYTES:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.data = candidate
        self._page_count = len(reader.pages)

    def undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append(self.data)
            self.data = self.undo_stack.pop()
            self._page_count = len(read_pdf(self.data).pages)

    def redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append(self.data)
            self.data = self.redo_stack.pop()
            self._page_count = len(read_pdf(self.data).pages)

    def rotate(self, index: int, degrees: int = 90) -> None:
        writer = self.writer()
        writer.pages[index].rotate(degrees)
        self.commit(writer)

    def rotate_pages(self, indices: list[int], degrees: int = 90) -> None:
        if degrees not in (-90, 90, 180) or not indices or len(set(indices)) != len(indices):
            raise ValueError("Select distinct pages and a 90 or 180 degree rotation.")
        if any(type(index) is not int or not 0 <= index < self.count for index in indices):
            raise ValueError("Choose pages in this document.")
        writer = self.writer()
        for index in indices:
            writer.pages[index].rotate(degrees)
        self.commit(writer)

    def page_labels(self) -> list[str]:
        return list(read_pdf(self.data).page_labels)

    def set_page_labels(
        self,
        first: int,
        last: int,
        prefix: str = "",
        style: str = "decimal",
        start: int = 1,
    ) -> None:
        styles = {
            "decimal": PageLabelStyle.DECIMAL,
            "roman": PageLabelStyle.LOWERCASE_ROMAN,
            "letters": PageLabelStyle.UPPERCASE_LETTER,
        }
        if (
            type(first) is not int
            or type(last) is not int
            or not 0 <= first <= last < self.count
            or not isinstance(prefix, str)
            or len(prefix) > 100
            or style not in styles
            or type(start) is not int
            or not 1 <= start <= 100000
        ):
            raise ValueError("Choose valid pages, prefix, style and starting number.")
        if read_pdf(self.data).trailer["/Root"].get("/PageLabels") is not None:
            raise ValueError("Editing existing custom page labels is not supported yet.")
        writer = self.writer()
        writer.set_page_label(first, last, style=styles[style], prefix=prefix, start=start)
        if last + 1 < self.count:
            writer.set_page_label(
                last + 1,
                self.count - 1,
                style=PageLabelStyle.DECIMAL,
                prefix="",
                start=last + 2,
            )
        self.commit(writer)

    def delete(self, index: int) -> None:
        self.delete_pages([index])

    def delete_pages(self, indices: list[int]) -> None:
        self.validate_pages(indices)
        if len(indices) == self.count:
            raise ValueError("Keep at least one page in the document.")
        writer = self.writer()
        for index in sorted(indices, reverse=True):
            writer.remove_page(index)
        self.commit(writer)

    def reorder_pages(self, order: list[int]) -> None:
        self.validate_pages(order)
        if len(order) != self.count:
            raise ValueError("Include every page exactly once when reordering.")
        current = list(range(self.count))
        if order == current:
            return
        writer = self.writer()
        for destination, index in enumerate(order):
            position = current.index(index)
            if position != destination:
                page = writer.pages[position]
                del writer.pages[position]
                writer.insert_page(page, destination)
                current.insert(destination, current.pop(position))
        self.commit(writer)

    def move(self, index: int, destination: int) -> None:
        if not 0 <= destination < self.count:
            return
        self.validate_pages([index])
        order = list(range(self.count))
        order.insert(destination, order.pop(index))
        self.reorder_pages(order)

    def duplicate_pages(self, indices: list[int], position: int) -> None:
        self.validate_pages(indices)
        if (
            type(position) is not int
            or not 0 <= position <= self.count
            or self.count + len(indices) > MAX_PAGES
        ):
            raise ValueError(
                "Choose an insertion point and keep the document at 500 pages or fewer."
            )
        reader = read_pdf(self.data)
        if reader.trailer["/Root"].get("/AcroForm") is not None:
            raise ValueError(
                "Range duplication is unavailable for documents with interactive forms."
            )
        writer = self.writer()
        writer.merge(position, reader, pages=indices, import_outline=False)
        self.commit(writer)

    def crop_pages(
        self,
        indices: list[int],
        bounds: tuple[float, float, float, float],
        *,
        margins: bool = False,
    ) -> None:
        self.validate_pages(indices)
        if len(bounds) != 4 or not all(math.isfinite(value) and value >= 0 for value in bounds):
            raise ValueError("Choose finite, nonnegative crop coordinates.")
        writer = self.writer()
        for index in indices:
            page = writer.pages[index]
            if page.user_unit != 1:
                raise ValueError(f"Page {index + 1} uses a custom PDF unit and cannot be cropped.")
            width, height, transform = visible_page(page)
            left, top, right, bottom = bounds
            if margins:
                right, bottom = width - right, height - bottom
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError(f"The crop must leave visible content on page {index + 1}.")
            a, b = (
                transform.apply_on((left, height - top)),
                transform.apply_on((right, height - bottom)),
            )
            page.cropbox = RectangleObject(
                (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            )
        self.commit(writer)

    def reset_crops(self, indices: list[int]) -> None:
        self.validate_pages(indices)
        writer = self.writer()
        for index in indices:
            page = writer.pages[index]
            page.cropbox = RectangleObject(page.mediabox)
        self.commit(writer)

    def append(self, path: Path) -> None:
        other = Document.open(path)
        self.insert_pages(other, list(range(other.count)), self.count)

    def insert_pages(self, source: Document, indices: list[int], position: int) -> None:
        source.validate_pages(indices)
        if type(position) is not int or not 0 <= position <= self.count:
            raise ValueError("Choose where to insert the pages.")
        if self.count + len(indices) > MAX_PAGES:
            raise ValueError("The combined document would exceed 500 pages.")
        writer = self.writer()
        writer.merge(position, read_pdf(source.data), pages=indices, import_outline=False)
        self.commit(writer)
        self.sources.update(source.sources)
        self.source_identities.update(source.source_identities)
        self.opened_encrypted |= source.opened_encrypted

    @serialized_pdfium
    def render(self, index: int, scale: float = 1.0):
        with pdfium.PdfDocument(self.data) as pdf:
            pdf.init_forms()
            page = pdf[index]
            try:
                width, height = page.get_size()
                scale = min(scale, 3000 / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    return bitmap.to_pil().convert("RGB").copy()
                finally:
                    bitmap.close()
            finally:
                page.close()

    @serialized_pdfium
    def size(self, index: int) -> tuple[float, float]:
        with pdfium.PdfDocument(self.data) as pdf:
            page = pdf[index]
            try:
                return page.get_size()
            finally:
                page.close()

    @serialized_pdfium
    def mark_writer(self, index: int) -> PdfWriter:
        original = self.writer()
        annotations = original.pages[index].get("/Annots", [])
        if not any(a.get_object().get("/Subtype") != "/Link" for a in annotations):
            return original
        # Flatten the selected page's visible annotation appearances below new marks.
        # Keep links as interactive objects, and leave other pages alone.
        links = [a.get_object() for a in annotations if a.get_object().get("/Subtype") == "/Link"]
        with pdfium.PdfDocument(self.data) as pdf:
            pdf.init_forms()
            page = pdf[index]
            try:
                result = pdfium.raw.FPDFPage_Flatten(page, pdfium.raw.FLAT_NORMALDISPLAY)
                if result == pdfium.raw.FLATTEN_FAIL:
                    raise ValueError(
                        "This page's annotation appearance could not be prepared for editing."
                    )
            finally:
                page.close()
            stream = io.BytesIO()
            pdf.save(stream)
        writer = PdfWriter(clone_from=io.BytesIO(stream.getvalue()))
        if links:
            writer.pages[index][NameObject("/Annots")] = ArrayObject(
                [a.clone(writer) for a in links]
            )
        else:
            writer.pages[index].pop("/Annots", None)
        return writer

    def duplicate(self, index: int) -> None:
        if self.count >= MAX_PAGES:
            raise ValueError("The document already has 500 pages.")
        writer = self.writer()
        # A fresh reader prevents shared page objects between the two copies.
        reader = PdfReader(io.BytesIO(self.data))
        writer.insert_page(reader.pages[index], index + 1)
        self.commit(writer)

    def insert_blank(self, index: int) -> None:
        if self.count >= MAX_PAGES:
            raise ValueError("The document already has 500 pages.")
        writer = self.writer()
        width, height = self.size(index)
        writer.insert_blank_page(width=width, height=height, index=index + 1)
        self.commit(writer)

    def export_page(self, index: int, path: Path, overwrite: bool = False) -> None:
        self.export_pages([index], path, overwrite=overwrite)

    def validate_pages(self, indices: list[int]) -> None:
        if not indices or any(
            type(index) is not int or not 0 <= index < self.count for index in indices
        ):
            raise ValueError("Select at least one valid page.")
        if len(set(indices)) != len(indices):
            raise ValueError("Select each page only once.")

    @staticmethod
    def subset_pdf(reader: PdfReader, indices: list[int]) -> bytes:
        writer = PdfWriter()
        writer.append(reader, pages=indices, import_outline=False)
        output = serialize(writer)
        read_pdf(output)
        return output

    def export_pages(self, indices: list[int], path: Path, overwrite: bool = False) -> None:
        self.validate_pages(indices)
        path = self.export_destination(path, ".pdf")
        write_copy_bytes(path, self.subset_pdf(read_pdf(self.data), indices), overwrite)

    def export_destination(self, path: Path, suffix: str) -> Path:
        path = path.resolve()
        if path.suffix.lower() != suffix:
            raise ValueError(f"Use the {suffix} file extension.")
        self.check_destination(path)
        return path

    def export_text(self, indices: list[int], path: Path, overwrite: bool = False) -> None:
        self.validate_pages(indices)
        path = self.export_destination(path, ".txt")
        reader = read_pdf(self.data)
        output = io.BytesIO()
        for index in indices:
            text = reader.pages[index].extract_text() or ""
            output.write(f"--- Page {index + 1} ---\n{text.rstrip()}\n\n".encode("utf-8"))
            if output.tell() > 20 * 1024 * 1024:
                raise ValueError("Text export exceeds 20 MB. Select fewer pages.")
        write_copy_bytes(path, output.getvalue(), overwrite)

    def page_text(self, index: int) -> str:
        self.validate_pages([index])
        text = read_pdf(self.data).pages[index].extract_text() or ""
        if len(text) > 2_000_000:
            raise ValueError("The extracted text exceeds the clipboard limit.")
        return text

    def external_links(self) -> list[tuple[int, str]]:
        links = []
        for index, page in enumerate(read_pdf(self.data).pages, 1):
            for ref in page.get("/Annots") or ():
                link = ref.get_object()
                action = link.get("/A")
                if link.get("/Subtype") == "/Link" and action is not None:
                    action = action.get_object()
                    if action.get("/S") == "/URI" and action.get("/URI"):
                        links.append((index, str(action["/URI"])[:2048]))
                        if len(links) >= 1000:
                            return links
        return links

    def export_page_image(self, index: int, path: Path, kind: str, overwrite: bool = False) -> None:
        self.validate_pages([index])
        if kind not in ("png", "jpg"):
            raise ValueError("Choose PNG or JPEG.")
        path = self.export_destination(path, "." + kind)
        write_copy_bytes(path, self.page_image_bytes(index, kind), overwrite)

    def page_image_bytes(self, index: int, kind: str) -> bytes:
        with self.render(index, 2) as image, io.BytesIO() as output:
            image.save(output, format="PNG" if kind == "png" else "JPEG", quality=90)
            return output.getvalue()

    def export_compressed(self, path: Path, overwrite: bool = False) -> tuple[int, int]:
        path = self.export_destination(path, ".pdf")
        writer = self.writer()
        for page in writer.pages:
            page.compress_content_streams()
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        candidate = serialize(writer)
        output = self.data
        if len(candidate) < len(output):
            read_pdf(candidate)
            output = candidate
        write_copy_bytes(path, output, overwrite)
        return len(self.data), len(output)

    def export_page_archive(
        self, indices: list[int], path: Path, kind: str, overwrite: bool = False
    ) -> None:
        self.validate_pages(indices)
        if len(indices) > 20:
            raise ValueError("Select up to 20 pages per archive.")
        if kind not in ("pdf", "png", "jpg"):
            raise ValueError("Choose PDF, PNG or JPEG.")
        path = self.export_destination(path, ".zip")
        reader = read_pdf(self.data)
        output = io.BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for number, index in enumerate(indices, 1):
                if kind == "pdf":
                    data = self.subset_pdf(reader, [index])
                else:
                    data = self.page_image_bytes(index, kind)
                archive.writestr(f"{number:03d}-page-{index + 1}.{kind}", data)
                if output.tell() > 100 * 1024 * 1024:
                    raise ValueError("The archive exceeds 100 MB. Select fewer pages.")
        write_copy_bytes(path, output.getvalue(), overwrite)

    def export_raster_redacted(
        self,
        index: int,
        box: tuple[float, float, float, float],
        path: Path,
        overwrite: bool = False,
    ) -> None:
        """Rebuild every page from rendered pixels, blacking a selected visible area.

        This discards all source PDF objects, including searchable text, forms,
        annotations, links, outlines, metadata, attachments, and signatures.
        """
        if self.count > 20:
            raise ValueError("Rasterized redacted export supports up to 20 pages.")
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
            raise ValueError("Choose a finite redaction rectangle.")
        left, right = sorted((box[0], box[2]))
        top, bottom = sorted((box[1], box[3]))
        width, height = self.size(index)
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("Draw the complete redaction rectangle inside the visible page.")
        path = path.resolve()
        if path.suffix.lower() != ".pdf":
            raise ValueError("Save the document with a .pdf extension.")
        self.check_destination(path)
        stream = io.BytesIO()
        canvas = Canvas(stream, pagesize=(width, height), pageCompression=1)
        for number in range(self.count):
            page_width, page_height = self.size(number)
            if page_width * page_height * 4 > 4_000_000:
                raise ValueError("A page is too large for bounded rasterized export.")
            image = self.render(number, scale=2.0)
            if number == index:
                sx, sy = image.width / page_width, image.height / page_height
                draw = ImageDraw.Draw(image)
                draw.rectangle(
                    (
                        math.floor(left * sx),
                        math.floor(top * sy),
                        math.ceil(right * sx),
                        math.ceil(bottom * sy),
                    ),
                    fill=(0, 0, 0),
                )
            canvas.setPageSize((page_width, page_height))
            canvas.drawImage(ImageReader(image), 0, 0, page_width, page_height)
            canvas.showPage()
            image.close()
        canvas.save()
        output = stream.getvalue()
        if len(output) > MAX_BYTES:
            raise ValueError("Rasterized output exceeds the 50 MB PDF limit.")
        write_copy_bytes(path, output, overwrite=overwrite)

    def export_searchable_image_copy(
        self,
        path: Path,
        overwrite: bool = False,
        ocr_dir: Path | None = None,
        language: str = "eng",
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Create an offline image copy with Tesseract's invisible searchable text.

        This export intentionally discards source PDF objects and never changes the
        open document. It is bounded because each page is rendered in memory.
        """
        if self.count > 20:
            raise ValueError("OCR image export supports up to 20 pages.")
        path = path.resolve()
        if path.suffix.lower() != ".pdf":
            raise ValueError("Save the document with a .pdf extension.")
        self.check_destination(path)
        bundle = ocr_dir or Path(sys.executable).resolve().parent / "Support" / "ocr"
        executable = bundle / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
        if not re.fullmatch(r"[a-z0-9_]{2,32}", language):
            raise ValueError("Choose an installed OCR language code.")
        trained = bundle / "tessdata" / f"{language}.traineddata"
        if not executable.is_file() or not trained.is_file():
            raise ValueError(f"Offline OCR language {language} is unavailable in this build.")
        writer = PdfWriter()
        if progress:
            progress(0, self.count)
        with tempfile.TemporaryDirectory(prefix="forge-pdf-ocr-") as directory:
            temporary = Path(directory)
            for index in range(self.count):
                if cancelled and cancelled():
                    raise ValueError("OCR cancelled.")
                width, height = self.size(index)
                if width * height * 4 > 4_000_000:
                    raise ValueError("A page is too large for bounded OCR export.")
                image = self.render(index, scale=2.0)
                try:
                    source = temporary / "page.png"
                    result = temporary / "result"
                    image.save(source, format="PNG")
                    process = subprocess.Popen(
                        [str(executable), str(source), str(result), "-l", language, "pdf"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={**os.environ, "TESSDATA_PREFIX": str(bundle / "tessdata")},
                        cwd=temporary,
                    )
                    started = time.monotonic()
                    try:
                        while True:
                            if cancelled and cancelled():
                                raise ValueError("OCR cancelled.")
                            if time.monotonic() - started > 120:
                                raise TimeoutError("OCR page exceeded the 120-second limit.")
                            try:
                                _, stderr = process.communicate(timeout=0.1)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                    except BaseException:
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise
                    if process.returncode:
                        raise ValueError(
                            f"OCR engine failed on page {index + 1}: {stderr.decode(errors='replace')[:300]}"
                        )
                    if not result.with_suffix(".pdf").is_file():
                        raise ValueError(
                            "OCR engine did not create a PDF; check its language and PDF configuration files."
                        )
                    reader = PdfReader(result.with_suffix(".pdf"))
                    if len(reader.pages) != 1:
                        raise ValueError("OCR did not return one page.")
                    writer.add_page(reader.pages[0])
                    source.unlink()
                    result.with_suffix(".pdf").unlink()
                    if progress:
                        progress(index + 1, self.count)
                finally:
                    image.close()
        if cancelled and cancelled():
            raise ValueError("OCR cancelled.")
        output = serialize(writer)
        if len(output) > MAX_BYTES:
            raise ValueError("OCR output exceeds the 50 MB PDF limit.")
        write_copy_bytes(path, output, overwrite=overwrite)

    def export_searchable_layer_copy(
        self,
        path: Path,
        overwrite: bool = False,
        ocr_dir: Path | None = None,
        language: str = "eng",
        progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Add invisible OCR text to a copy of simple, image-based PDF pages.

        The original PDF is cloned so graphics, links and outlines are retained.
        Refuse complex geometry, forms, signatures and pages with existing text
        rather than risk a misleading or misaligned OCR layer.
        """
        if self.count > 20:
            raise ValueError("OCR text-layer export supports up to 20 pages.")
        path = path.resolve()
        if path.suffix.lower() != ".pdf":
            raise ValueError("Save the document with a .pdf extension.")
        self.check_destination(path)
        bundle = ocr_dir or Path(sys.executable).resolve().parent / "Support" / "ocr"
        executable = bundle / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
        if not re.fullmatch(r"[a-z0-9_]{2,32}", language):
            raise ValueError("Choose an installed OCR language code.")
        if (
            not executable.is_file()
            or not (bundle / "tessdata" / f"{language}.traineddata").is_file()
        ):
            raise ValueError(f"Offline OCR language {language} is unavailable in this build.")
        writer = self.writer()
        root = writer._root_object
        if "/AcroForm" in root or "/Perms" in root:
            raise ValueError("OCR text-layer export does not support forms or signed PDFs.")
        for page in writer.pages:
            box = page.mediabox
            crop = page.cropbox
            if (
                page.get("/Rotate", 0) % 360
                or page.get("/UserUnit", 1) != 1
                or tuple(float(v) for v in box) != tuple(float(v) for v in crop)
                or float(box.left) != 0
                or float(box.bottom) != 0
            ):
                raise ValueError(
                    "OCR text-layer export needs unrotated, uncropped pages at origin zero."
                )
            if page.extract_text().strip():
                raise ValueError(
                    "OCR text-layer export needs pages without existing searchable text."
                )
            resources = page.get("/Resources")
            xobjects = resources.get_object().get("/XObject", {}) if resources else {}
            if not any(
                item.get_object().get("/Subtype") == "/Image"
                for item in (
                    xobjects.get_object() if hasattr(xobjects, "get_object") else xobjects
                ).values()
            ):
                raise ValueError("OCR text-layer export needs an image on every page.")
        if progress:
            progress(0, self.count)
        with tempfile.TemporaryDirectory(prefix="forge-pdf-ocr-") as directory:
            temporary = Path(directory)
            for index, page in enumerate(writer.pages):
                if cancelled and cancelled():
                    raise ValueError("OCR cancelled.")
                width, height = self.size(index)
                if width * height * 4 > 4_000_000:
                    raise ValueError("A page is too large for bounded OCR export.")
                image = self.render(index, scale=2.0)
                try:
                    source = temporary / "page.png"
                    result = temporary / "layer"
                    image.save(source, format="PNG")
                    dpi = round(image.width * 72 / width)
                    process = subprocess.Popen(
                        [
                            str(executable),
                            str(source),
                            str(result),
                            "-l",
                            language,
                            "--dpi",
                            str(dpi),
                            "-c",
                            "textonly_pdf=1",
                            "pdf",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={**os.environ, "TESSDATA_PREFIX": str(bundle / "tessdata")},
                        cwd=temporary,
                    )
                    started = time.monotonic()
                    try:
                        while True:
                            if cancelled and cancelled():
                                raise ValueError("OCR cancelled.")
                            if time.monotonic() - started > 120:
                                raise TimeoutError("OCR page exceeded the 120-second limit.")
                            try:
                                _, stderr = process.communicate(timeout=0.1)
                                break
                            except subprocess.TimeoutExpired:
                                continue
                    except BaseException:
                        process.terminate()
                        try:
                            process.communicate(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.communicate()
                        raise
                    if process.returncode or not result.with_suffix(".pdf").is_file():
                        message = (
                            stderr.decode(errors="replace")[:300]
                            if process.returncode
                            else "no PDF"
                        )
                        raise ValueError(f"OCR engine failed on page {index + 1}: {message}")
                    layer_reader = PdfReader(result.with_suffix(".pdf"))
                    if len(layer_reader.pages) != 1:
                        raise ValueError("OCR did not return one text-layer page.")
                    layer = layer_reader.pages[0]
                    layer_width, layer_height = (
                        float(layer.mediabox.width),
                        float(layer.mediabox.height),
                    )
                    if abs(layer_width - width) > 1 or abs(layer_height - height) > 1:
                        raise ValueError("OCR text layer does not match source page size.")
                    if layer.get("/Resources", {}).get("/XObject"):
                        raise ValueError(
                            "OCR engine returned image content instead of a text-only layer."
                        )
                    page.merge_transformed_page(
                        layer, Transformation().scale(width / layer_width, height / layer_height)
                    )
                    source.unlink()
                    result.with_suffix(".pdf").unlink()
                    if progress:
                        progress(index + 1, self.count)
                finally:
                    image.close()
        if cancelled and cancelled():
            raise ValueError("OCR cancelled.")
        output = serialize(writer)
        if len(output) > MAX_BYTES:
            raise ValueError("OCR output exceeds the 50 MB PDF limit.")
        write_copy_bytes(path, output, overwrite=overwrite)

    def clear_footer(self, pixels: int = 5) -> None:
        if not isinstance(pixels, int) or isinstance(pixels, bool) or not 1 <= pixels <= 10000:
            raise ValueError("Enter a footer height from 1 to 10000 pixels.")
        # At the editor's 100% scale, one pixel equals one PDF point.
        # Stage every page independently, then make the whole batch one undoable edit.
        working = Document(self.data)
        for index in range(working.count):
            width, height = working.size(index)
            working.overlay(index, "whiteout", (0, max(0, height - pixels), width, height))
            working.undo_stack.clear()
        self.commit(working.writer())

    def overlay(
        self,
        index: int,
        kind: str,
        box: tuple,
        text: str = "",
        size: int = 16,
        font_path: Path | None = None,
        image_path: Path | bytes | None = None,
        color: str | None = None,
        stroke: float = 2,
    ):
        writer = self.writer() if kind in DRAW_TOOLS else self.mark_writer(index)
        page = writer.pages[index]
        width, height, transform = visible_page(page)
        stream = io.BytesIO()
        canvas = Canvas(stream, pagesize=(width, height))
        x, y, x2, y2 = box
        if not all(math.isfinite(value) for value in (x, y, x2, y2)):
            raise ValueError("Choose finite page coordinates.")
        if kind == "text":
            if not text.strip():
                raise ValueError("Enter some text first.")
            font = text_font(text, font_path)
            if not 8 <= size <= 72:
                raise ValueError("Choose a text size between 8 and 72 points.")
            lines = text.splitlines()
            if (
                x < 0
                or y < 0
                or x + max(stringWidth(line, font, size) for line in lines) > width
                or y + len(lines) * size * 1.25 > height
            ):
                raise ValueError(
                    "The text does not fit here. Use a smaller size or click farther left/up."
                )
            canvas.setFillColor(HexColor(color or "#142133"))
            canvas.setFont(font, size)
            for n, line in enumerate(lines):
                canvas.drawString(x, height - y - size - n * size * 1.25, line)
        elif kind == "image":
            if image_path is None:
                raise ValueError("Choose a PNG or JPEG stamp first.")
            if not 0 <= x < x2 <= width or not 0 <= y < y2 <= height:
                raise ValueError("Draw the complete image-stamp rectangle inside the page.")
            image = stamp_image(image_path)
            stamp_width, stamp_height = fit_stamp_size(image.size, x2 - x, y2 - y)
            canvas.drawImage(
                ImageReader(image),
                x + (x2 - x - stamp_width) / 2,
                height - y2 + (y2 - y - stamp_height) / 2,
                stamp_width,
                stamp_height,
                mask="auto",
            )
        elif kind in ("highlight", "whiteout"):
            x, x2 = sorted((max(0, min(width, x)), max(0, min(width, x2))))
            y, y2 = sorted((max(0, min(height, y)), max(0, min(height, y2))))
            if x2 - x <= 0 or y2 - y <= 0:
                return
            if kind == "whiteout":
                canvas.setFillColorRGB(1, 1, 1)
            else:
                canvas.setFillColor(HexColor(color or "#ffcc1f"))
                canvas.setFillAlpha(0.32)
            canvas.rect(x, height - y2, x2 - x, y2 - y, fill=1, stroke=0)
        elif kind in DRAW_TOOLS:
            if not 0.5 <= stroke <= 12:
                raise ValueError("Choose a line thickness from 0.5 to 12 points.")
            paint = HexColor(color or "#245bb2")
            canvas.setStrokeColor(paint)
            canvas.setFillColor(paint)
            canvas.setLineWidth(stroke)
            if kind in ("line", "arrow"):
                if x == x2 and y == y2:
                    return
                canvas.line(x, height - y, x2, height - y2)
                if kind == "arrow":
                    angle = math.atan2(y - y2, x2 - x)
                    length = min(max(6, 4 * stroke), math.hypot(x2 - x, y2 - y) / 2)
                    for offset in (-math.pi / 6, math.pi / 6):
                        canvas.line(
                            x2,
                            height - y2,
                            x2 - length * math.cos(angle + offset),
                            height - y2 - length * math.sin(angle + offset),
                        )
            else:
                left, right = sorted((x, x2))
                bottom, top = sorted((height - y, height - y2))
                if left == right or bottom == top:
                    return
                fill = int(kind.startswith("filled"))
                if kind.endswith("ellipse"):
                    canvas.ellipse(left, bottom, right, top, stroke=1, fill=fill)
                else:
                    canvas.rect(left, bottom, right - left, top - bottom, stroke=1, fill=fill)
        else:
            raise ValueError("Unknown editing tool.")
        canvas.save()
        page.merge_transformed_page(PdfReader(stream).pages[0], transform)
        self.commit(writer)

    def mark_pages(
        self,
        indices: list[int],
        kind: str,
        text: str = "",
        size: int = 16,
        start: int = 1,
        font_path: Path | None = None,
    ) -> None:
        self.validate_pages(indices)
        if kind not in ("header", "footer", "watermark", "numbers"):
            raise ValueError("Choose a header, footer, watermark or page numbers.")
        if type(size) is not int or not 8 <= size <= 72:
            raise ValueError("Choose a text size between 8 and 72 points.")
        if type(start) is not int or not 1 <= start <= 100000:
            raise ValueError("Choose a starting number between 1 and 100000.")
        if kind != "numbers" and (not text.strip() or len(text) > 200 or not text.isprintable()):
            raise ValueError("Enter one line containing 1 to 200 printable characters.")
        font = text_font("0123456789" if kind == "numbers" else text, font_path)
        writer = self.writer()
        for number, index in enumerate(indices, start):
            page = writer.pages[index]
            width, height, transform = visible_page(page)
            label = str(number) if kind == "numbers" else text
            if stringWidth(label, font, size) + 24 > width or size + 24 > height:
                raise ValueError(f"The mark does not fit on page {index + 1}. Use smaller text.")
            stream = io.BytesIO()
            canvas = Canvas(stream, pagesize=(width, height))
            canvas.setFont(font, size)
            if kind == "watermark":
                canvas.setFillColorRGB(0.18, 0.24, 0.32)
                canvas.setFillAlpha(0.23)
                y = (height - size) / 2
            elif kind == "header":
                y = height - size - 12
            else:
                y = 12
            canvas.drawCentredString(width / 2, y, label)
            canvas.save()
            page.merge_transformed_page(PdfReader(stream).pages[0], transform)
        self.commit(writer)

    def search(
        self,
        query: str,
        limit: int = 1000,
        case_sensitive: bool = False,
        whole_word: bool = False,
    ) -> list[dict]:
        """Bounded literal text search; image-only pages require external OCR."""
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ValueError("Enter 1 to 256 search characters.")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Search results are limited to 1 through 1000 matches.")
        if type(case_sensitive) is not bool or type(whole_word) is not bool:
            raise ValueError("Search options must be enabled or disabled.")
        matches = []
        literal = re.escape(query)
        if whole_word:
            literal = rf"(?<!\w){literal}(?!\w)"
        pattern = re.compile(literal, 0 if case_sensitive else re.IGNORECASE)
        for index, page in enumerate(read_pdf(self.data).pages):
            text = page.extract_text() or ""
            if len(text) > 2_000_000:
                raise ValueError("This page has too much extracted text for bounded search.")
            for match in pattern.finditer(text):
                excerpt = text[max(0, match.start() - 35) : match.end() + 60]
                matches.append(
                    {
                        "page": index,
                        "excerpt": " ".join(excerpt.split()),
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
                if len(matches) >= limit:
                    return matches
        return matches

    def text_fields(self) -> dict[str, str]:
        """Return editable AcroForm text fields by fully qualified name."""
        fields = read_pdf(self.data).get_fields() or {}
        result = {}
        for name, field in fields.items():
            if field.get("/FT") == "/Tx" and not field.get("/Ff", 0) & 1:
                result[name] = str(field.get("/V", ""))
        return result

    def fill_text_field(self, name: str, value: str) -> None:
        if name not in self.text_fields():
            raise ValueError("Choose an editable text form field.")
        if not isinstance(value, str) or len(value) > 10_000:
            raise ValueError("Form text must be at most 10,000 characters.")
        writer = self.writer()
        writer.update_page_form_field_values(None, {name: value}, auto_regenerate=False)
        self.commit(writer)

    def choice_fields(self) -> dict[str, tuple[str, list[str]]]:
        result = {}
        for name, field in (read_pdf(self.data).get_fields() or {}).items():
            options = field.get("/Opt", [])
            if (
                field.get("/FT") == "/Ch"
                and not field.get("/Ff", 0) & 1
                and isinstance(options, (list, ArrayObject))
                and options
                and all(isinstance(item, str) for item in options)
            ):
                result[name] = (str(field.get("/V", "")), [str(item) for item in options])
        return result

    def fill_choice_field(self, name: str, value: str) -> None:
        fields = self.choice_fields()
        if name not in fields or value not in fields[name][1]:
            raise ValueError("Choose a listed option for an editable choice field.")
        writer = self.writer()
        writer.update_page_form_field_values(None, {name: value}, auto_regenerate=False)
        self.commit(writer)

    def checkbox_fields(self) -> dict[str, bool]:
        result = {}
        for name, field in (read_pdf(self.data).get_fields() or {}).items():
            states = field.get("/_States_", [])
            if not isinstance(states, (list, ArrayObject)):
                continue
            on_states = [state for state in states if state != "/Off"]
            if (
                field.get("/FT") == "/Btn"
                and not field.get("/Ff", 0) & (1 | (1 << 15) | (1 << 16))
                and "/Off" in states
                and len(on_states) == 1
                and isinstance(on_states[0], str)
            ):
                result[name] = field.get("/V") == on_states[0]
        return result

    def set_checkbox(self, name: str, checked: bool) -> None:
        if name not in self.checkbox_fields() or type(checked) is not bool:
            raise ValueError("Choose an editable single-state checkbox.")
        states = (read_pdf(self.data).get_fields() or {})[name]["/_States_"]
        on_state = next(state for state in states if state != "/Off")
        writer = self.writer()
        writer.update_page_form_field_values(
            None, {name: on_state if checked else "/Off"}, auto_regenerate=False
        )
        self.commit(writer)

    def radio_fields(self) -> dict[str, tuple[str, list[str]]]:
        """Expose conventional editable radio groups and their on-state names."""
        result = {}
        for name, field in (read_pdf(self.data).get_fields() or {}).items():
            states = field.get("/_States_", [])
            if not isinstance(states, (list, ArrayObject)):
                continue
            options = list(dict.fromkeys(str(state) for state in states if state != "/Off"))
            if (
                field.get("/FT") == "/Btn"
                and field.get("/Ff", 0) & (1 << 15)
                and not field.get("/Ff", 0) & (1 | (1 << 16))
                and 2 <= len(options) <= 100
                and all(option.startswith("/") and len(option) <= 128 for option in options)
            ):
                result[name] = (str(field.get("/V", "")), options)
        return result

    def select_radio(self, name: str, value: str) -> None:
        fields = self.radio_fields()
        if name not in fields or value not in fields[name][1]:
            raise ValueError("Choose a listed option for an editable radio group.")
        writer = self.writer()
        writer.update_page_form_field_values(None, {name: value}, auto_regenerate=False)
        self.commit(writer)

    def metadata(self) -> dict[str, str]:
        info = read_pdf(self.data).metadata
        return {
            key: str(info.get(key, "")) if info else ""
            for key in ("/Title", "/Author", "/Subject", "/Keywords")
        }

    def set_metadata(self, values: dict[str, str]) -> None:
        allowed = {"/Title", "/Author", "/Subject", "/Keywords"}
        if (
            not isinstance(values, dict)
            or set(values) != allowed
            or any(not isinstance(value, str) or len(value) > 2_000 for value in values.values())
        ):
            raise ValueError("Enter title, author, subject and keywords (up to 2,000 characters).")
        writer = self.writer()
        writer.add_metadata(values)
        self.commit(writer)

    def clear_common_metadata(self) -> None:
        self.set_metadata(dict.fromkeys(("/Title", "/Author", "/Subject", "/Keywords"), ""))

    def add_bookmark(self, title: str, index: int) -> None:
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Enter a bookmark title up to 200 characters.")
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        writer = self.writer()
        writer.add_outline_item(title.strip(), index)
        self.commit(writer)

    def bookmarks(self) -> list[dict]:
        reader = read_pdf(self.data)
        result = []

        def visit(items, depth):
            if depth > 20:
                return
            for item in items:
                if len(result) >= 1000:
                    return
                if isinstance(item, list):
                    visit(item, depth + 1)
                    continue
                try:
                    page = reader.get_destination_page_number(item)
                except (KeyError, ValueError, TypeError):
                    continue
                if 0 <= page < len(reader.pages):
                    result.append({"title": str(item.title)[:200], "page": page, "depth": depth})

        visit(reader.outline, 0)
        return result

    def _top_level_bookmark_items(self, writer: PdfWriter) -> tuple[object, list]:
        root = writer.get_outline_root()
        items = list(root.children())
        shown = self.bookmarks()
        if (
            len(items) != len(shown)
            or len(items) > 1000
            or any("/First" in item for item in items)
            or any(item["depth"] != 0 for item in shown)
        ):
            raise ValueError("Bookmark editing supports only simple top-level outlines.")
        return root, items

    def rename_bookmark(self, index: int, title: str) -> None:
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Enter a bookmark title up to 200 characters.")
        writer = self.writer()
        _, items = self._top_level_bookmark_items(writer)
        if type(index) is not int or not 0 <= index < len(items):
            raise ValueError("Choose a bookmark in this document.")
        items[index][NameObject("/Title")] = TextStringObject(title.strip())
        self.commit(writer)

    def delete_bookmark(self, index: int) -> None:
        writer = self.writer()
        root, items = self._top_level_bookmark_items(writer)
        if type(index) is not int or not 0 <= index < len(items):
            raise ValueError("Choose a bookmark in this document.")
        root.remove_child(items[index])
        self.commit(writer)

    def notes(self, index: int) -> list[str]:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        page = read_pdf(self.data).pages[index]
        return [
            str(ref.get_object().get("/Contents", ""))
            for ref in page.get("/Annots", [])
            if ref.get_object().get("/Subtype") == "/Text"
        ]

    def all_notes(self) -> list[dict]:
        reader = read_pdf(self.data)
        result = []
        for page_index, page in enumerate(reader.pages):
            note_index = 0
            for ref in page.get("/Annots", []):
                note = ref.get_object()
                if note.get("/Subtype") == "/Text":
                    result.append(
                        {
                            "page": page_index,
                            "index": note_index,
                            "text": str(note.get("/Contents", "")),
                        }
                    )
                    note_index += 1
        return result

    def update_note(self, index: int, note_index: int, text: str) -> None:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("Enter note text up to 2,000 characters.")
        writer = self.writer()
        notes = [
            ref.get_object()
            for ref in writer.pages[index].get("/Annots", [])
            if ref.get_object().get("/Subtype") == "/Text"
        ]
        if type(note_index) is not int or not 0 <= note_index < len(notes):
            raise ValueError("Choose a note on this page.")
        notes[note_index][NameObject("/Contents")] = TextStringObject(text.strip())
        self.commit(writer)

    def add_note(self, index: int, x: float, y: float, text: str) -> None:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("Enter note text up to 2,000 characters.")
        width, height = self.size(index)
        if not all(math.isfinite(v) for v in (x, y)) or not 0 <= x < width or not 0 <= y < height:
            raise ValueError("Place the note inside the visible page.")
        writer = self.writer()
        page = writer.pages[index]
        left, bottom = float(page.cropbox.left), float(page.cropbox.bottom)
        right, top = float(page.cropbox.right), float(page.cropbox.top)
        matrices = {
            0: (1, 0, 0, 1, left, bottom),
            90: (0, 1, -1, 0, right, bottom),
            180: (-1, 0, 0, -1, right, top),
            270: (0, -1, 1, 0, left, top),
        }
        a, b, c, d, e, f = matrices[page.rotation % 360]
        corners = [(x, height - y), (min(x + 24, width), height - min(y + 24, height))]
        points = [(a * px + c * py + e, b * px + d * py + f) for px, py in corners]
        rect = (
            min(p[0] for p in points),
            min(p[1] for p in points),
            max(p[0] for p in points),
            max(p[1] for p in points),
        )
        writer.add_annotation(index, TextNote(rect=rect, text=text.strip()))
        self.commit(writer)

    def delete_note(self, index: int, note_index: int) -> None:
        writer = self.writer()
        annotations = writer.pages[index].get("/Annots", [])
        positions = [
            i for i, ref in enumerate(annotations) if ref.get_object().get("/Subtype") == "/Text"
        ]
        if type(note_index) is not int or not 0 <= note_index < len(positions):
            raise ValueError("Choose a note on this page.")
        del annotations[positions[note_index]]
        self.commit(writer)

    def add_native_highlight(self, index: int, box: tuple[float, float, float, float]) -> None:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box):
            raise ValueError("Draw a finite highlight rectangle.")
        x0, x1 = sorted((box[0], box[2]))
        y0, y1 = sorted((box[1], box[3]))
        width, height = self.size(index)
        if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
            raise ValueError("Draw the complete highlight rectangle inside the visible page.")
        writer = self.writer()
        page = writer.pages[index]
        left, bottom = float(page.cropbox.left), float(page.cropbox.bottom)
        right, top = float(page.cropbox.right), float(page.cropbox.top)
        matrices = {
            0: (1, 0, 0, 1, left, bottom),
            90: (0, 1, -1, 0, right, bottom),
            180: (-1, 0, 0, -1, right, top),
            270: (0, -1, 1, 0, left, top),
        }
        a, b, c, d, e, f = matrices[page.rotation % 360]
        visible = [(x0, height - y0), (x1, height - y0), (x0, height - y1), (x1, height - y1)]
        points = [(a * x + c * y + e, b * x + d * y + f) for x, y in visible]
        rect = (
            min(x for x, _ in points),
            min(y for _, y in points),
            max(x for x, _ in points),
            max(y for _, y in points),
        )
        quad = ArrayObject([FloatObject(v) for point in points for v in point])
        writer.add_annotation(
            index,
            PdfHighlight(rect=rect, quad_points=quad, highlight_color="fff176", printing=True),
        )
        self.commit(writer)

    def highlight_annotation_count(self, index: int) -> int:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        return sum(
            ref.get_object().get("/Subtype") == "/Highlight"
            for ref in read_pdf(self.data).pages[index].get("/Annots", [])
        )

    def recolor_native_highlight(self, index: int, highlight_index: int, color: str) -> None:
        """Recolor an annotation whose appearance is derived from its PDF color entry."""
        colors = {
            "yellow": "fff176",
            "green": "a5d6a7",
            "blue": "90caf9",
            "pink": "f48fb1",
        }
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        if color not in colors:
            raise ValueError("Choose yellow, green, blue or pink.")
        writer = self.writer()
        highlights = [
            ref.get_object()
            for ref in writer.pages[index].get("/Annots", [])
            if ref.get_object().get("/Subtype") == "/Highlight"
        ]
        if type(highlight_index) is not int or not 0 <= highlight_index < len(highlights):
            raise ValueError("Choose a native highlight on this page.")
        annotation = highlights[highlight_index]
        if "/AP" in annotation:
            raise ValueError(
                "This highlight has a custom appearance that cannot be recolored safely."
            )
        rgb = bytes.fromhex(colors[color])
        annotation[NameObject("/C")] = ArrayObject([FloatObject(channel / 255) for channel in rgb])
        self.commit(writer)

    def delete_native_highlight(self, index: int, highlight_index: int) -> None:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        writer = self.writer()
        annotations = writer.pages[index].get("/Annots", [])
        positions = [
            i
            for i, ref in enumerate(annotations)
            if ref.get_object().get("/Subtype") == "/Highlight"
        ]
        if type(highlight_index) is not int or not 0 <= highlight_index < len(positions):
            raise ValueError("Choose a native highlight on this page.")
        del annotations[positions[highlight_index]]
        self.commit(writer)

    def export_preflight(self) -> dict:
        reader = read_pdf(self.data)
        links = annotations = 0
        for page in reader.pages:
            for reference in page.get("/Annots", []):
                if reference.get_object().get("/Subtype") == "/Link":
                    links += 1
                else:
                    annotations += 1
        return {
            "pages": len(reader.pages),
            "bytes": len(self.data),
            "links": links,
            "other_annotations": annotations,
            "forms": len(reader.get_fields() or {}),
            "warnings": [
                "Visual whiteout and subset export are not secure redaction.",
                "Standard saved PDFs and editing sessions are unencrypted. Use Save encrypted copy for protected PDF output.",
                "Editing does not preserve valid digital signatures.",
                "Review links, forms and annotation appearances in the exported copy.",
            ],
        }

    def check_destination(self, path: Path) -> None:
        # Only stat the explicitly selected destination, never auto-open session source paths.
        resolved = path.resolve()
        original_names = {os.path.normcase(os.path.abspath(source)) for source in self.sources}
        if os.path.normcase(str(resolved)) in original_names:
            raise ValueError(
                "Choose a different name. Forge PDF keeps your original files untouched."
            )
        if resolved.exists():
            stat = resolved.stat()
            if (stat.st_dev, stat.st_ino) in self.source_identities:
                raise ValueError(
                    "Choose a different name. Forge PDF keeps your original files untouched."
                )

    def save_copy(self, path: Path, overwrite: bool = False, password: str | None = None) -> None:
        path = path.resolve()
        if path.suffix.lower() != ".pdf":
            raise ValueError("Save the document with a .pdf extension.")
        self.check_destination(path)
        read_pdf(self.data)
        output = self.data
        if password is not None:
            if not isinstance(password, str) or not password:
                raise ValueError("Enter a nonempty password for the encrypted copy.")
            writer = self.writer()
            writer.encrypt(password, algorithm="AES-256")
            output = serialize(writer)
        write_copy_bytes(path, output, overwrite)
        self.saved = self.data


def write_copy_bytes(path: Path, data: bytes, overwrite: bool = False) -> None:
    fd, name = tempfile.mkstemp(prefix=".forge-pdf-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if overwrite:
            os.replace(name, path)
        else:
            # A same-directory hard link publishes the fully written file atomically
            # and fails if the destination already exists. Copying into an "xb" file
            # could leave a truncated PDF or session after a crash.
            os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
