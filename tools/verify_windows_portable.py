"""Exercise the exact portable ZIP in a Windows desktop session using synthetic files."""

import ctypes
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab
from pypdf import PdfReader

if sys.platform != "win32":
    raise SystemExit("Portable acceptance requires a Windows interactive desktop.")

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "portable-acceptance"
OUTPUT.mkdir(exist_ok=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [CALLBACK, wintypes.LPARAM]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]


class Keyboard(ctypes.Structure):
    _fields_ = [
        ("vk", wintypes.WORD),
        ("scan", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class Mouse(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
        ("data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("keyboard", Keyboard), ("mouse", Mouse)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", InputUnion)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def key(code, up=False, unicode=False):
    event = Input(
        type=1,
        value=InputUnion(
            keyboard=Keyboard(
                vk=0 if unicode else code,
                scan=code if unicode else 0,
                flags=(4 if unicode else 0) | (2 if up else 0),
            )
        ),
    )
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise RuntimeError("Windows rejected acceptance keyboard input.")


def hotkey(*codes):
    for code in codes:
        key(code)
    for code in reversed(codes):
        key(code, up=True)


def type_text(text):
    data = text.encode("utf-16-le")
    for index in range(0, len(data), 2):
        value = int.from_bytes(data[index : index + 2], "little")
        key(value, unicode=True)
        key(value, up=True, unicode=True)


def wait_window(fragment, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = []

        @CALLBACK
        def visit(handle, unused, found=found):
            if user32.IsWindowVisible(handle):
                text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(handle) + 1)
                user32.GetWindowTextW(handle, text, len(text))
                if fragment in text.value:
                    found.append(handle)
            return True

        user32.EnumWindows(visit, 0)
        if found:
            user32.ShowWindow(found[0], 9)
            user32.SetForegroundWindow(found[0])
            time.sleep(0.1)
            if user32.GetForegroundWindow() != found[0]:
                raise RuntimeError("Could not focus the isolated acceptance window.")
            return found[0]
        time.sleep(0.05)
    raise RuntimeError("Expected portable-app window did not appear: " + fragment)


def screenshot(handle, name):
    rectangle = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rectangle)):
        raise RuntimeError("Could not inspect portable window bounds.")
    ImageGrab.grab(bbox=(rectangle.left, rectangle.top, rectangle.right, rectangle.bottom)).save(
        OUTPUT / name
    )


def choose_destination(title, path):
    dialog = wait_window(title)
    hotkey(0x12, 0x4E)  # Alt+N focuses File name in the standard Windows dialog.
    hotkey(0x11, 0x41)
    type_text(str(path))
    hotkey(0x0D)
    deadline = time.monotonic() + 30
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not path.exists():
        screenshot(dialog, "portable-save-failure.png")
        raise RuntimeError(f"Portable app did not write the selected destination: {path.name}")


archive = next((ROOT / "dist").glob("Forge-PDF-*-Windows.zip"))
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix="forge-pdf-portable-") as temporary:
    folder = Path(temporary)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(folder / "portable")
    executable = folder / "portable" / "Forge PDF" / "Forge PDF.exe"
    source = folder / ("portable-" + uuid.uuid4().hex + ".pdf")
    original = (ROOT / "examples" / "Welcome.pdf").read_bytes()
    source.write_bytes(original)
    process = subprocess.Popen([str(executable), str(source)], cwd=executable.parent)
    main = None
    report = None
    try:
        main = wait_window(source.name, timeout=30)
        time.sleep(0.5)
        screenshot(main, "portable-main.png")
        hotkey(0x11, 0x46)
        search = wait_window("Find document text")
        type_text("Forge")
        hotkey(0x0D)
        time.sleep(0.5)
        screenshot(search, "portable-search.png")
        hotkey(0x1B)
        wait_window(source.name)
        hotkey(0x11, 0x53)
        copied = folder / "portable-copy.pdf"
        choose_destination("Save an edited copy", copied)
        assert len(PdfReader(copied).pages) == len(PdfReader(source).pages)
        assert copied.read_bytes() == original and source.read_bytes() == original
        wait_window(source.name)
        hotkey(0x11, 0x10, 0x53)
        session = folder / "portable-session.forgepdf"
        choose_destination("Save unencrypted session", session)
        with zipfile.ZipFile(session) as saved:
            metadata = json.loads(saved.read("session.json"))
            assert metadata["session_version"] == 1
            assert saved.read("current.pdf") == original
        wait_window(source.name)
        hotkey(0x11, 0x10, 0x4F)
        wait_window("Open an unencrypted editing session")
        hotkey(0x11, 0x41)
        type_text(str(session))
        hotkey(0x0D)
        reopened = wait_window(session.name)
        screenshot(reopened, "portable-session.png")
        assert source.read_bytes() == original
        report = {
            "status": "passed",
            "archive": archive.name,
            "sha256": digest,
            "checks": [
                "native executable launch/load",
                "keyboard find dialog interaction",
                "PDF save, parser validation and original preservation",
                "explicit session save/reopen",
            ],
            "boundary": "Synthetic smoke; model/Tk suite covers edits separately. No arbitrary-PDF, screen-reader or physical-device claim.",
        }
    finally:
        if process.poll() is None:
            if main is not None and user32.IsWindow(main):
                if not user32.PostMessageW(main, 0x0010, 0, 0):  # WM_CLOSE
                    raise RuntimeError("Could not request portable app shutdown.")
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # The editing window can show a save prompt on close. Acceptance uses
                # synthetic files, so stop only this spawned process tree before cleanup.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                process.wait(timeout=15)
    if report is not None:
        (OUTPUT / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
