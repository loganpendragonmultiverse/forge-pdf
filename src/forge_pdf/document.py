"""Transactional PDF edits. Originals are never written by this module."""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ArrayObject, NameObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 500
HISTORY_BYTES = 100 * 1024 * 1024


def read_pdf(data: bytes) -> PdfReader:
    if len(data) > MAX_BYTES:
        raise ValueError("This first build supports PDFs up to 50 MB.")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported in this first build.")
    if not 0 < len(reader.pages) <= MAX_PAGES:
        raise ValueError("Please use a PDF containing 1 to 500 pages.")
    return reader


def serialize(writer: PdfWriter) -> bytes:
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


class Document:
    def __init__(self, data: bytes, source: Path | None = None):
        read_pdf(data)
        self.data = data
        self.saved = data
        self.sources = {source.resolve()} if source else set()
        self.undo_stack: list[bytes] = []
        self.redo_stack: list[bytes] = []

    @classmethod
    def open(cls, path: Path, password: str | None = None) -> Document:
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("This first build supports PDFs up to 50 MB.")
        data = path.read_bytes()
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            if not reader.decrypt(password or ""):
                raise ValueError("Password required or incorrect password.")
            data = serialize(PdfWriter(clone_from=reader))
        return cls(data, path)

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

    def size(self, index: int) -> tuple[float, float]:
        with pdfium.PdfDocument(self.data) as pdf:
            page = pdf[index]
            try:
                return page.get_size()
            finally:
                page.close()

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
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(self.data)).pages[index])
        extracted = Document(serialize(writer))
        extracted.sources = self.sources.copy()
        extracted.save_copy(path, overwrite=overwrite)

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

    def overlay(self, index: int, kind: str, box: tuple, text: str = "", size: int = 16):
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
        if kind == "text":
            if not text.strip():
                raise ValueError("Enter some text first.")
            try:
                text.encode("cp1252")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "Text currently supports Western European characters only."
                ) from exc
            if not 8 <= size <= 72:
                raise ValueError("Choose a text size between 8 and 72 points.")
            lines = text.splitlines()
            if (
                x < 0
                or y < 0
                or x + max(stringWidth(line, "Helvetica", size) for line in lines) > width
                or y + len(lines) * size * 1.25 > height
            ):
                raise ValueError(
                    "The text does not fit here. Use a smaller size or click farther left/up."
                )
            canvas.setFillColorRGB(0.08, 0.13, 0.20)
            canvas.setFont("Helvetica", size)
            for n, line in enumerate(lines):
                canvas.drawString(x, height - y - size - n * size * 1.25, line)
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

    def save_copy(self, path: Path, overwrite: bool = False) -> None:
        path = path.resolve()
        if path.suffix.lower() != ".pdf":
            raise ValueError("Save the document with a .pdf extension.")
        if path in self.sources or any(
            path.exists() and os.path.samefile(path, source)
            for source in self.sources
            if source.exists()
        ):
            raise ValueError(
                "Choose a different name. Forge PDF keeps your original files untouched."
            )
        read_pdf(self.data)
        fd, name = tempfile.mkstemp(prefix=".forge-pdf-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(self.data)
                output.flush()
                os.fsync(output.fileno())
            if overwrite:
                os.replace(name, path)
            else:
                # Exclusive create prevents a race with another process's destination.
                with path.open("xb") as output:
                    try:
                        output.write(self.data)
                        output.flush()
                        os.fsync(output.fileno())
                    except BaseException:
                        output.close()
                        path.unlink(missing_ok=True)
                        raise
            self.saved = self.data
        finally:
            Path(name).unlink(missing_ok=True)
