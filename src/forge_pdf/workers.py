"""One-shot, memory-only workers; the GUI process creates no background Python threads."""

from __future__ import annotations

import json
import multiprocessing as mp
from multiprocessing import shared_memory

from PIL import Image

from .document import Document, MAX_BYTES


def _work(connection, memory_name, length, role, params, cancel_event):
    try:
        memory = shared_memory.SharedMemory(name=memory_name)
        try:
            data = bytes(memory.buf[:length])
        finally:
            memory.close()
        document = Document(data)
        if role == "preview":
            width, height = document.size(params["page"])
            zoom = params["zoom"]
            if params["fit"]:
                zoom = max(0.05, min((params["cw"] - 48) / width, (params["ch"] - 48) / height, 2))
            image = document.render(params["page"], zoom)
            result = dict(
                params,
                width=width,
                height=height,
                zoom=zoom,
                image_width=image.width,
                image_height=image.height,
                status="image",
            )
            connection.send_bytes(json.dumps(result).encode())
            connection.send_bytes(image.tobytes())
        elif role == "search":
            connection.send_bytes(
                json.dumps(
                    {
                        "status": "search",
                        "matches": document.search(
                            params["query"],
                            case_sensitive=params.get("case_sensitive", False),
                            whole_word=params.get("whole_word", False),
                        ),
                    }
                ).encode()
            )
        elif role == "ocr":
            from pathlib import Path

            def progress(done, total):
                connection.send_bytes(
                    json.dumps({"status": "progress", "done": done, "total": total}).encode()
                )

            export = (
                document.export_searchable_layer_copy
                if params.get("preserve_pages")
                else document.export_searchable_image_copy
            )
            export(
                Path(params["path"]),
                overwrite=params["overwrite"],
                ocr_dir=Path(params["ocr_dir"]) if params.get("ocr_dir") else None,
                language=params["language"],
                progress=progress,
                cancelled=cancel_event.is_set,
            )
            connection.send_bytes(json.dumps({"status": "ocr"}).encode())
        else:
            raise ValueError("Unknown worker operation.")
    except Exception as exc:
        connection.send_bytes(json.dumps({"status": "error", "message": str(exc)}).encode())
    finally:
        connection.close()


class WorkerFuture:
    def __init__(self, data, role, params):
        if not 0 < len(data) <= MAX_BYTES:
            raise ValueError("Worker PDF exceeds its file limit.")
        self.memory = shared_memory.SharedMemory(create=True, size=len(data))
        self.memory.buf[: len(data)] = data
        context = mp.get_context("spawn")
        self.role = role
        self.cancel_event = context.Event()
        self.connection, child = context.Pipe(duplex=False)
        self.process = context.Process(
            target=_work, args=(child, self.memory.name, len(data), role, params, self.cancel_event)
        )
        self.header = None
        self.value = None
        self.error = None
        self.complete = False
        self.progress = (0, 0)
        try:
            self.process.start()
        except BaseException:
            child.close()
            self.connection.close()
            self.memory.close()
            self.memory.unlink()
            raise
        child.close()

    def _release(self):
        self.connection.close()
        if self.memory is not None:
            self.memory.close()
            self.memory.unlink()
            self.memory = None
        self.process.join(timeout=0.05)

    def done(self):
        if self.complete:
            return True
        try:
            if self.header is None and self.connection.poll():
                self.header = json.loads(self.connection.recv_bytes(8 * 1024 * 1024))
            if self.header is not None:
                if self.header["status"] == "error":
                    self.error = ValueError(self.header["message"])
                elif self.header["status"] == "search":
                    self.value = self.header["matches"]
                elif self.header["status"] == "progress":
                    self.progress = (self.header["done"], self.header["total"])
                    self.header = None
                    return False
                elif self.header["status"] == "ocr":
                    self.value = True
                elif self.header["status"] == "image":
                    if not self.connection.poll():
                        return False
                    header = self.header
                    width, height = header["image_width"], header["image_height"]
                    if not 0 < width <= 3000 or not 0 < height <= 3000:
                        raise ValueError("Preview exceeded its pixel limit.")
                    pixels = self.connection.recv_bytes(3000 * 3000 * 3)
                    if len(pixels) != width * height * 3:
                        raise ValueError("Incomplete preview pixels.")
                    image = Image.frombytes("RGB", (width, height), pixels)
                    self.value = (
                        header["generation"],
                        image,
                        header["width"],
                        header["height"],
                        header["zoom"],
                        header["cw"],
                        header["ch"],
                        header["view"],
                    )
                else:
                    raise ValueError("Invalid worker result.")
                self.complete = True
                self._release()
                return True
            if self.process.exitcode is not None:
                raise ValueError("PDF worker exited without a complete result.")
        except (EOFError, OSError, ValueError, KeyError, TypeError) as exc:
            self.error = ValueError(str(exc) or "PDF worker failed.")
            self.complete = True
            self.cancel()
            return True
        return False

    def result(self):
        if not self.done():
            raise RuntimeError("Worker is still running.")
        if self.error:
            raise self.error
        return self.value

    def cancel(self):
        if self.role == "ocr":
            self.cancel_event.set()
            self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        if self.memory is not None:
            self._release()
        self.complete = True


class NativeWorker:
    def __init__(self, role):
        self.role = role
        self.active = None
        self.closed = False

    def submit(self, data, params):
        if self.closed:
            raise RuntimeError("Worker is closed.")
        if self.active is not None and not self.active.done():
            raise RuntimeError("A worker job is already running.")
        self.active = WorkerFuture(data, self.role, params)
        return self.active

    def shutdown(self, wait=False, cancel_futures=True):
        self.closed = True
        if self.active is not None:
            self.active.cancel()
