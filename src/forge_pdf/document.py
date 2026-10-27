"""Transactional PDF edits. Originals are never written by this module."""

from __future__ import annotations

import io
import math
import os
import re
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageDraw
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.annotations import Text as TextNote
from pypdf.constants import PageLabelStyle
from pypdf.generic import ArrayObject, NameObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .enhancements import serialized_pdfium, stamp_image, text_font, fit_stamp_size

MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 500
HISTORY_BYTES = 100 * 1024 * 1024


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


class Document:
    def __init__(self, data: bytes, source: Path | None = None):
        read_pdf(data)
        self.data = data
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
        return len(PdfReader(io.BytesIO(self.data)).pages)

    @property
    def dirty(self) -> bool:
        return self.data != self.saved

    def writer(self) -> PdfWriter:
        return PdfWriter(clone_from=io.BytesIO(self.data))

    def commit(self, writer: PdfWriter) -> None:
        candidate = serialize(writer)
        read_pdf(candidate)
        self.undo_stack.append(self.data)
        while len(self.undo_stack) > 30 or sum(map(len, self.undo_stack)) > HISTORY_BYTES:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.data = candidate

    def undo(self) -> None:
        if self.undo_stack:
            self.redo_stack.append(self.data)
            self.data = self.undo_stack.pop()

    def redo(self) -> None:
        if self.redo_stack:
            self.undo_stack.append(self.data)
            self.data = self.redo_stack.pop()

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
        if self.count == 1:
            raise ValueError("Keep at least one page in the document.")
        writer = self.writer()
        del writer.pages[index]
        self.commit(writer)

    def move(self, index: int, destination: int) -> None:
        if not 0 <= destination < self.count:
            return
        writer = self.writer()
        page = writer.pages[index]
        del writer.pages[index]
        writer.insert_page(page, destination)
        self.commit(writer)

    def append(self, path: Path) -> None:
        other = Document.open(path)
        if self.count + other.count > MAX_PAGES:
            raise ValueError("The combined document would exceed 500 pages.")
        writer = self.writer()
        writer.append(PdfReader(io.BytesIO(other.data)), import_outline=False)
        self.commit(writer)
        self.sources.add(path.resolve())
        self.source_identities.update(other.source_identities)

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

    def export_pages(self, indices: list[int], path: Path, overwrite: bool = False) -> None:
        count = self.count
        if not indices or any(
            not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < count
            for index in indices
        ):
            raise ValueError("Select at least one valid page.")
        if len(set(indices)) != len(indices):
            raise ValueError("Select each page only once.")
        writer = PdfWriter()
        reader = PdfReader(io.BytesIO(self.data))
        for index in indices:
            writer.add_page(reader.pages[index])
        extracted = Document(serialize(writer))
        extracted.sources = self.sources.copy()
        extracted.source_identities = self.source_identities.copy()
        extracted.save_copy(path, overwrite=overwrite)

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
    ):
        writer = self.mark_writer(index)
        page = writer.pages[index]
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
            canvas.setFillColorRGB(0.08, 0.13, 0.20)
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
                canvas.setFillColorRGB(1, 0.80, 0.12)
                canvas.setFillAlpha(0.32)
            canvas.rect(x, height - y2, x2 - x, y2 - y, fill=1, stroke=0)
        else:
            raise ValueError("Unknown editing tool.")
        canvas.save()
        page.merge_transformed_page(PdfReader(stream).pages[0], Transformation(matrices[rotation]))
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
            if (
                field.get("/FT") == "/Btn"
                and not field.get("/Ff", 0) & (1 | (1 << 15) | (1 << 16))
                and "/Yes" in states
                and "/Off" in states
            ):
                result[name] = field.get("/V") == "/Yes"
        return result

    def set_checkbox(self, name: str, checked: bool) -> None:
        if name not in self.checkbox_fields() or type(checked) is not bool:
            raise ValueError("Choose an editable Yes/Off checkbox.")
        writer = self.writer()
        writer.update_page_form_field_values(
            None, {name: "/Yes" if checked else "/Off"}, auto_regenerate=False
        )
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

    def notes(self, index: int) -> list[str]:
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError("Choose a page in this document.")
        page = read_pdf(self.data).pages[index]
        return [
            str(ref.get_object().get("/Contents", ""))
            for ref in page.get("/Annots", [])
            if ref.get_object().get("/Subtype") == "/Text"
        ]

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
