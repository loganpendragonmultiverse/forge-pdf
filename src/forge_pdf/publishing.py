"""Offline document creation, publishing, and review exports."""

from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .document import PAGE_SIZES, Document, read_pdf, visible_page, write_copy_bytes
from .enhancements import fit_stamp_size, text_font

TEXT_LIMIT = 200_000
ARCHIVE_LIMIT = 100 * 1024 * 1024
WORKSHEETS = ("Ruled", "Grid", "Dots")


def text_document(text: str, font_path: Path | None = None) -> Document:
    """Lay out plain text in a new Letter PDF, with hard wrapping for long tokens."""
    if len(text) > TEXT_LIMIT or not text.strip():
        raise ValueError("Enter between 1 and 200,000 characters of plain text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    if any(not character.isprintable() and character != "\n" for character in text):
        raise ValueError("Use plain text with line breaks and tabs.")
    font = text_font(text, font_path)
    size, leading, margin = 11, 15, 48
    width, height = PAGE_SIZES["Letter"]
    available = width - 2 * margin
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    rows_per_page = int((height - 2 * margin - size) // leading) + 1
    for row, line in enumerate(wrapped_lines(text, font, size, available)):
        page, position = divmod(row, rows_per_page)
        if page >= 100:
            raise ValueError("The generated text would exceed 100 pages.")
        if position == 0:
            if page:
                canvas.showPage()
            canvas.setFont(font, size)
        canvas.drawString(margin, height - margin - size - position * leading, line)
    canvas.save()
    doc = Document(output.getvalue())
    doc.saved = b""
    return doc


def wrapped_lines(text, font, size, available):
    for logical in text.split("\n"):
        line = ""
        for word in re.findall(r"\S+| +", logical):
            if stringWidth(line + word, font, size) <= available:
                line += word
                continue
            if line.strip():
                yield line.rstrip()
            line = ""
            for character in word.lstrip(" "):
                if line and stringWidth(line + character, font, size) > available:
                    yield line
                    line = ""
                line += character
        yield line.rstrip()


def text_file_document(path: Path, font_path: Path | None = None) -> Document:
    path = path.resolve()
    with path.open("rb") as source:
        raw = source.read(TEXT_LIMIT * 4 + 4)
        stat = os.fstat(source.fileno())
    if len(raw) > TEXT_LIMIT * 4 + 3:
        raise ValueError("The text file exceeds the import limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Choose a plain text file saved as UTF-8.") from exc
    doc = text_document(text, font_path)
    doc.sources.add(path)
    doc.source_identities.add((stat.st_dev, stat.st_ino))
    return doc


def worksheet(pattern: str, count: int, paper: str, landscape: bool) -> Document:
    if pattern not in WORKSHEETS or not 1 <= count <= 100 or paper not in PAGE_SIZES:
        raise ValueError("Choose a pattern, paper size, and 1 to 100 pages.")
    width, height = PAGE_SIZES[paper][::-1] if landscape else PAGE_SIZES[paper]
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    x_end, y_end = int(width - 36), int(height - 36)
    for _ in range(count):
        canvas.setStrokeColorRGB(0.68, 0.74, 0.81)
        canvas.setFillColorRGB(0.55, 0.61, 0.69)
        canvas.setLineWidth(0.45)
        if pattern == "Dots":
            for y in range(36, y_end + 1, 18):
                for x in range(36, x_end + 1, 18):
                    canvas.circle(x, y, 0.7, stroke=0, fill=1)
        else:
            for y in range(36, y_end + 1, 18):
                canvas.line(36, y, x_end, y)
            if pattern == "Grid":
                for x in range(36, x_end + 1, 18):
                    canvas.line(x, 36, x, y_end)
        canvas.showPage()
    canvas.save()
    doc = Document(output.getvalue())
    doc.saved = b""
    return doc


def split_groups(count: int, *, every: int = 0, starts: tuple[int, ...] = ()) -> list[list[int]]:
    """Return contiguous groups. Explicit boundaries are one-based start pages."""
    if every:
        if type(every) is not int or not 1 <= every <= count or starts:
            raise ValueError("Choose a valid number of pages per file.")
        cuts = list(range(0, count, every))
    else:
        if (
            not starts
            or list(starts) != sorted(set(starts))
            or any(not 2 <= n <= count for n in starts)
        ):
            raise ValueError("Enter unique, ascending start pages between 2 and the last page.")
        cuts = [0, *(n - 1 for n in starts)]
    if not 2 <= len(cuts) <= 100:
        raise ValueError("A split must produce 2 to 100 PDF files.")
    return [list(range(start, end)) for start, end in zip(cuts, cuts[1:] + [count], strict=True)]


def export_split(document: Document, groups: list[list[int]], path: Path, overwrite=False) -> None:
    for group in groups:
        document.validate_pages(group)
    if not 2 <= len(groups) <= 100 or [i for group in groups for i in group] != list(
        range(document.count)
    ):
        raise ValueError("Split groups must cover the document in its original order.")
    path = document.export_destination(path, ".zip")
    reader = read_pdf(document.data)
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for number, group in enumerate(groups, 1):
            archive.writestr(
                f"{number:03d}-pages-{group[0] + 1}-{group[-1] + 1}.pdf",
                document.subset_pdf(reader, group),
            )
            if output.tell() > ARCHIVE_LIMIT:
                raise ValueError("The split archive would exceed 100 MB.")
    write_copy_bytes(path, output.getvalue(), overwrite)


def export_contact_sheet(
    document: Document, indices: list[int], columns: int, path: Path, overwrite=False
) -> None:
    document.validate_pages(indices)
    if columns not in (2, 3, 4) or len(indices) > 40:
        raise ValueError("Choose 2 to 4 columns and up to 40 pages.")
    path = document.export_destination(path, ".pdf")
    output = io.BytesIO()
    width, height = PAGE_SIZES["Letter"]
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    margin, header, rows = 30, 36, 3
    cell_width = (width - 2 * margin) / columns
    cell_height = (height - 2 * margin - header) / rows
    for i, index in enumerate(indices):
        slot = i % (columns * rows)
        if slot == 0:
            if i:
                canvas.showPage()
            canvas.setFont("Helvetica-Bold", 15)
            canvas.drawString(margin, height - margin - 14, "Page contact sheet")
        row, column = divmod(slot, columns)
        x = margin + column * cell_width
        y = height - margin - header - (row + 1) * cell_height
        page_width, page_height = document.size(index)
        scale = min(1, 540 / max(page_width, page_height))
        with document.render(index, scale) as image:
            iw, ih = fit_stamp_size(image.size, cell_width - 12, cell_height - 26)
            canvas.drawImage(
                ImageReader(image),
                x + (cell_width - iw) / 2,
                y + 22 + (cell_height - 26 - ih) / 2,
                iw,
                ih,
            )
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(x + cell_width / 2, y + 8, f"Page {index + 1}")
    canvas.save()
    data = output.getvalue()
    read_pdf(data)
    write_copy_bytes(path, data, overwrite)


def export_rendered_archive(
    document: Document,
    indices: list[int],
    kind: str,
    dpi: int,
    gray: bool,
    quality: int,
    path: Path,
    overwrite=False,
) -> None:
    document.validate_pages(indices)
    if (
        kind not in ("png", "jpg")
        or not 72 <= dpi <= 216
        or not 40 <= quality <= 100
        or len(indices) > 20
    ):
        raise ValueError("Choose up to 20 pages, 72 to 216 DPI, and JPEG quality from 40 to 100.")
    path = document.export_destination(path, ".zip")
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for number, index in enumerate(indices, 1):
            width, height = document.size(index)
            effective_dpi = min(dpi, 216000 / max(width, height))
            with document.render(index, effective_dpi / 72) as image, io.BytesIO() as encoded:
                rendered = ImageOps.grayscale(image) if gray else image
                rendered.save(
                    encoded,
                    format="PNG" if kind == "png" else "JPEG",
                    dpi=(effective_dpi, effective_dpi),
                    quality=quality,
                )
                archive.writestr(f"{number:03d}-page-{index + 1}.{kind}", encoded.getvalue())
            if output.tell() > ARCHIVE_LIMIT:
                raise ValueError("The image archive would exceed 100 MB.")
    write_copy_bytes(path, output.getvalue(), overwrite)


def report_rows(document: Document, kind: str):
    if kind == "pages":
        yield ("Page", "Label", "Width (pt)", "Height (pt)", "Rotation", "Annotations")
        reader = read_pdf(document.data)
        for index, (page, label) in enumerate(
            zip(reader.pages, reader.page_labels, strict=True), 1
        ):
            width, height, _ = visible_page(page)
            yield (
                index,
                label,
                round(width * page.user_unit, 2),
                round(height * page.user_unit, 2),
                page.rotation % 360,
                len(page.get("/Annots") or ()),
            )
    elif kind == "links":
        yield ("Page", "URI")
        yield from document.external_links()
    elif kind == "notes":
        yield ("Page", "Note", "Text")
        for note in document.all_notes():
            yield (note["page"] + 1, note["index"] + 1, note["text"])
    elif kind == "bookmarks":
        yield ("Page", "Depth", "Title")
        for bookmark in document.bookmarks():
            yield (bookmark["page"] + 1, bookmark["depth"], bookmark["title"])
    else:
        raise ValueError("Unknown document report.")


def csv_cell(value):
    if not isinstance(value, str):
        return value
    value = value[:16_000]
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_report(document: Document, kind: str, path: Path, overwrite=False) -> None:
    path = document.export_destination(path, ".csv")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for row in report_rows(document, kind):
        writer.writerow([csv_cell(value) for value in row])
        if output.tell() > 1_250_000:
            raise ValueError("The report exceeds the export limit.")
    write_copy_bytes(path, output.getvalue().encode("utf-8-sig"), overwrite)
