"""Bounded local resources and explicit, self-contained editing-session files."""

from __future__ import annotations

import hashlib
import io
import json
import math
import threading
import warnings
import zipfile
from functools import wraps
from pathlib import Path

from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PDFIUM_LOCK = threading.RLock()
RESOURCE_BYTES = 20 * 1024 * 1024
SESSION_BYTES = 100 * 1024 * 1024


def serialized_pdfium(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with PDFIUM_LOCK:
            return function(*args, **kwargs)

    return locked


def text_font(text: str, path: Path | None) -> str:
    if path is None:
        try:
            text.encode("cp1252")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "Default Helvetica supports Western European characters only. Choose a local TrueType font for these characters."
            ) from exc
        return "Helvetica"
    if path.stat().st_size > RESOURCE_BYTES:
        raise ValueError("Choose a TrueType font no larger than 20 MB.")
    with path.open("rb") as source:
        data = source.read(RESOURCE_BYTES + 1)
    if len(data) > RESOURCE_BYTES:
        raise ValueError("Choose a TrueType font no larger than 20 MB.")
    name = "ForgeLocal-" + hashlib.sha256(data).hexdigest()
    if name not in pdfmetrics.getRegisteredFontNames():
        try:
            font = TTFont(name, io.BytesIO(data))
            pdfmetrics.registerFont(font)
        except Exception as exc:
            raise ValueError("This font could not be read as a supported TrueType font.") from exc
    font = pdfmetrics.getFont(name)
    missing = sorted(
        {
            ord(char)
            for char in text
            if not char.isspace() and not font.face.charToGlyph.get(ord(char))
        }
    )
    if missing:
        codes = ", ".join(f"U+{value:04X}" for value in missing[:12])
        raise ValueError("The selected font has no glyph for: " + codes)
    return name


def stamp_image(path: Path | bytes):
    if isinstance(path, bytes):
        data = path
    else:
        with path.open("rb") as source:
            data = source.read(RESOURCE_BYTES + 1)
    if len(data) > RESOURCE_BYTES:
        raise ValueError("Choose a PNG or JPEG no larger than 20 MB.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("Image stamps support PNG and JPEG only.")
            if image.width * image.height > 16_000_000:
                raise ValueError("Image stamps support up to 16 million pixels.")
            image.load()
            return image.convert("RGBA").copy()


def session_payload(
    document, page: int, zoom: float, include_history: bool = True, recovery: bool = False
) -> bytes:
    if not 0 <= page < document.count or not math.isfinite(zoom) or not 0.05 <= zoom <= 3:
        raise ValueError("Invalid session view state.")
    if recovery and include_history:
        raise ValueError("Recovery snapshots cannot include Undo history.")
    snapshots = []
    total = len(document.data)
    for item in reversed(document.undo_stack[-30:] if include_history else []):
        if total + len(item) > SESSION_BYTES:
            break
        snapshots.insert(0, item)
        total += len(item)
    manifest = {
        "session_version": 1,
        "page": page,
        "zoom": zoom,
        "history": len(snapshots),
        "sources": sorted(str(path) for path in document.sources),
        "source_identities": sorted([list(item) for item in document.source_identities]),
    }
    if recovery:
        manifest["recovery"] = True
    encoded_manifest = json.dumps(manifest, ensure_ascii=False)
    if len(encoded_manifest.encode("utf-8")) > 65536:
        raise ValueError("Original-file protection metadata exceeds the session limit.")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("session.json", encoded_manifest)
        archive.writestr("current.pdf", document.data)
        for index, item in enumerate(snapshots):
            archive.writestr(f"history/{index}.pdf", item)
    return stream.getvalue()


def open_session(path: Path):
    from .document import Document, MAX_BYTES, read_pdf

    if path.stat().st_size > SESSION_BYTES + 1024 * 1024:
        raise ValueError("Editing session exceeds the 100 MB payload limit.")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) > 32 or len(set(names)) != len(names):
                raise ValueError("Invalid session member count or duplicate names.")
            if any(item.flag_bits & 1 for item in infos):
                raise ValueError("Encrypted session archives are unsupported.")
            if sum(item.file_size for item in infos) > SESSION_BYTES + 65536:
                raise ValueError("Editing session payload is too large.")
            if archive.getinfo("session.json").file_size > 65536:
                raise ValueError("Session metadata is too large.")
            metadata = json.loads(archive.read("session.json"))
            fields = {"session_version", "page", "zoom", "history", "sources", "source_identities"}
            if not isinstance(metadata, dict) or set(metadata) not in (
                fields,
                fields | {"recovery"},
            ):
                raise ValueError("Invalid editing-session metadata.")
            if "recovery" in metadata and metadata["recovery"] is not True:
                raise ValueError("Invalid recovery marker.")
            if type(metadata["session_version"]) is not int or metadata["session_version"] != 1:
                raise ValueError("Unsupported editing-session version.")
            count = metadata["history"]
            if type(count) is not int or not 0 <= count <= 30:
                raise ValueError("Invalid session history length.")
            if metadata.get("recovery") and count:
                raise ValueError("Recovery snapshots cannot include Undo history.")
            expected = {"session.json", "current.pdf"} | {f"history/{i}.pdf" for i in range(count)}
            if set(names) != expected:
                raise ValueError("Unexpected editing-session members.")
            blobs = {}
            for name in expected - {"session.json"}:
                if archive.getinfo(name).file_size > MAX_BYTES:
                    raise ValueError("A session PDF exceeds 50 MB.")
                blobs[name] = archive.read(name)
                read_pdf(blobs[name])
            if sum(map(len, blobs.values())) > SESSION_BYTES:
                raise ValueError("Editing session exceeds 100 MB.")
            document = Document(blobs["current.pdf"])
            document.undo_stack = [blobs[f"history/{i}.pdf"] for i in range(count)]
            document.saved = b""  # Reopening a session never means an edited PDF was exported.
            sources, identities = metadata["sources"], metadata["source_identities"]
            if (
                not isinstance(sources, list)
                or len(sources) > 500
                or any(
                    not isinstance(item, str)
                    or len(item) > 32768
                    or "\x00" in item
                    or not Path(item).is_absolute()
                    for item in sources
                )
            ):
                raise ValueError("Invalid original-file protection metadata.")
            if (
                not isinstance(identities, list)
                or len(identities) > 500
                or any(
                    not isinstance(item, list)
                    or len(item) != 2
                    or any(type(value) is not int or value < 0 for value in item)
                    for item in identities
                )
            ):
                raise ValueError("Invalid original-file identity metadata.")
            # Metadata is retained for destination protection, never opened or auto-loaded.
            document.sources = {Path(item) for item in sources}
            document.source_identities = {tuple(item) for item in identities}
            page, zoom = metadata["page"], metadata["zoom"]
            if type(page) is not int or not 0 <= page < document.count:
                raise ValueError("Invalid session page.")
            if type(zoom) not in (int, float) or not math.isfinite(zoom) or not 0.05 <= zoom <= 3:
                raise ValueError("Invalid session zoom.")
            return document, page, float(zoom)
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("This is not a valid Forge PDF editing session.") from exc


def save_session(
    document,
    path: Path,
    page: int,
    zoom: float,
    overwrite: bool = False,
    include_history: bool = True,
    recovery: bool = False,
):
    if path.suffix.lower() != ".forgepdf":
        raise ValueError("Save editing sessions with a .forgepdf extension.")
    document.check_destination(path)
    data = session_payload(document, page, zoom, include_history=include_history, recovery=recovery)
    if len(data) > SESSION_BYTES + 1024 * 1024:
        raise ValueError("Editing session exceeds its bounded file limit.")
    # Both new files and overwrites publish completed bytes atomically.
    from .document import write_copy_bytes

    write_copy_bytes(path, data, overwrite)


def is_recovery_snapshot(path: Path) -> bool:
    """Identify only snapshots made by the opt-in recovery workflow."""
    if path.suffix.lower() != ".forgepdf" or path.is_symlink():
        return False
    try:
        if path.stat().st_size > SESSION_BYTES + 1024 * 1024:
            return False
        with zipfile.ZipFile(path) as archive:
            if set(archive.namelist()) != {"session.json", "current.pdf"}:
                return False
            if archive.getinfo("session.json").file_size > 65536:
                return False
            manifest = json.loads(archive.read("session.json"))
            return (
                isinstance(manifest, dict)
                and manifest.get("session_version") == 1
                and manifest.get("history") == 0
                and manifest.get("recovery") is True
            )
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeError):
        return False


def fit_stamp_size(image_size, width, height):
    if width <= 0 or height <= 0:
        raise ValueError("Draw a non-empty image rectangle.")
    factor = min(width / image_size[0], height / image_size[1])
    return image_size[0] * factor, image_size[1] * factor
