"""Offline print layouts, multipage images and revision review."""

from __future__ import annotations

import difflib
import io
from contextlib import ExitStack
from pathlib import Path

from PIL import ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from .document import PAGE_SIZES, Document, read_pdf, write_copy_bytes
from .enhancements import fit_stamp_size
from .publishing import split_groups


def bookmark_groups(document: Document):
    starts = sorted({b["page"] + 1 for b in document.bookmarks() if b["depth"] == 0 and b["page"]})
    if not starts:
        raise ValueError("Add a top-level bookmark after the first page to split into chapters.")
    return split_groups(document.count, starts=tuple(starts))


def print_layout(
    document: Document, pages: list[int], layout: str, paper: str, path: Path, overwrite=False
):
    document.validate_pages(pages)
    if layout not in {"two-up", "four-up", "booklet"} or paper not in PAGE_SIZES or len(pages) > 40:
        raise ValueError("Choose a supported layout and up to 40 pages.")
    path = document.export_destination(path, ".pdf")
    slots = list(pages)
    if layout == "booklet":
        slots.extend([None] * (-len(slots) % 4))
        slots = [
            slots[pos]
            for sheet in range(len(slots) // 4)
            for pos in (
                len(slots) - 1 - 2 * sheet,
                2 * sheet,
                2 * sheet + 1,
                len(slots) - 2 - 2 * sheet,
            )
        ]
    across, down = 2, 2 if layout == "four-up" else 1
    width, height = PAGE_SIZES[paper]
    if down == 1:
        width, height = height, width
    cell_w, cell_h = width / across, height / down
    output = io.BytesIO()
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    for n, page in enumerate(slots):
        slot = n % (across * down)
        if n and not slot:
            canvas.showPage()
        if page is None:
            continue
        page_w, page_h = document.size(page)
        w, h = fit_stamp_size((page_w, page_h), cell_w - 18, cell_h - 18)
        with document.render(page, min(2, 1100 / max(page_w, page_h))) as image:
            canvas.drawImage(
                ImageReader(image),
                slot % across * cell_w + (cell_w - w) / 2,
                height - (slot // across + 1) * cell_h + (cell_h - h) / 2,
                w,
                h,
            )
    canvas.showPage()
    canvas.save()
    result = output.getvalue()
    read_pdf(result)
    write_copy_bytes(path, result, overwrite)


def export_tiff(document: Document, pages: list[int], gray: bool, path: Path, overwrite=False):
    document.validate_pages(pages)
    if len(pages) > 20:
        raise ValueError("Choose up to 20 pages for TIFF export.")
    path = document.export_destination(path, ".tif")
    with ExitStack() as stack:
        frames = []
        for index in pages:
            w, h = document.size(index)
            image = stack.enter_context(document.render(index, min(1.5, 1200 / max(w, h))))
            if gray:
                image = stack.enter_context(ImageOps.grayscale(image))
            frames.append(image)
        output = io.BytesIO()
        frames[0].save(
            output,
            format="TIFF",
            save_all=True,
            append_images=frames[1:],
            compression="tiff_deflate",
        )
        write_copy_bytes(path, output.getvalue(), overwrite)


def compare_text(original: Document, revision: Document, path: Path, overwrite=False):
    """Compare embedded text by physical page position, with bounded diff cost."""
    path = original.export_destination(path, ".txt")
    revision.check_destination(path)
    if max(original.count, revision.count) > 100:
        raise ValueError("Compare documents of up to 100 pages.")
    left, right = read_pdf(original.data), read_pdf(revision.data)
    chunks = [
        "Embedded text comparison by page position. Images and layout are outside this report.\n"
    ]
    changed = 0
    for n in range(max(len(left.pages), len(right.pages))):
        pair = [
            pdf.pages[n].extract_text() or "" if n < len(pdf.pages) else None
            for pdf in (left, right)
        ]
        if pair[0] == pair[1]:
            continue
        if any(len(text) > 64000 or text.count("\n") > 2000 for text in pair if text is not None):
            raise ValueError("A changed page exceeds the text comparison limit.")
        changed += 1
        kind = "added" if pair[0] is None else "removed" if pair[1] is None else "changed"
        chunks.append(f"\nPage {n + 1} ({kind})\n")
        chunks.extend(
            line + "\n"
            for line in difflib.unified_diff(
                (pair[0] or "").splitlines(),
                (pair[1] or "").splitlines(),
                fromfile="Open document",
                tofile="Comparison document",
                lineterm="",
            )
        )
    chunks.append(f"\n{changed} page positions differ.\n")
    write_copy_bytes(path, "".join(chunks).encode("utf-8"), overwrite)
