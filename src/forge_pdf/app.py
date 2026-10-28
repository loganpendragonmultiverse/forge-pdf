"""Tk desktop shell with a single-page canvas and explicit editing modes."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from . import __version__
from .document import Document, parse_page_ranges
from .workers import NativeWorker
from .enhancements import (
    fit_stamp_size,
    is_recovery_snapshot,
    open_session,
    save_session,
    stamp_image,
    text_font,
    RESOURCE_BYTES,
)

NAVY = "#16232f"
MINT = "#a9edcc"
PAPER = "#f7f8fa"
INK = "#203340"


class Editor(tk.Tk):
    def __init__(self):
        # Python's Windows Tcl discovery can intermittently lose tcl_findLibrary
        # after repeated root creation in one process. Point the development/CI
        # interpreter at its own bundled script trees; PyInstaller supplies its
        # separate frozen paths and must keep managing those itself.
        if sys.platform == "win32" and not getattr(sys, "frozen", False):
            scripts = Path(sys.base_prefix) / "tcl"
            for name, folder in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
                if (scripts / folder / "init.tcl").is_file() or (
                    folder == "tk8.6" and (scripts / folder / "tk.tcl").is_file()
                ):
                    os.environ[name] = str(scripts / folder)
        # Windows Tcl/Tk can intermittently fail while locating its script library
        # after another root has closed. Retry that bootstrap failure once; other
        # Tk errors still surface immediately.
        for attempt in range(2):
            try:
                super().__init__()
                break
            except tk.TclError as exc:
                if attempt or not any(
                    marker in str(exc)
                    for marker in (
                        "tcl_findLibrary",
                        "Can't find a usable init.tcl",
                        "Can't find a usable tk.tcl",
                    )
                ):
                    raise
        self.title("Forge PDF")
        self.geometry("1180x820")
        self.minsize(740, 520)
        self.configure(bg=PAPER)
        self.option_add("*Font", ("Segoe UI", 10))
        self.doc = None
        self.path = None
        self.page = 0
        self.zoom = 1.0
        self.fit = False
        self.mode = tk.StringVar(value="view")
        self.font_size = tk.StringVar(value="16")
        self.drag_start = None
        self.drag_tool = None
        self.wheel_delta = 0
        self.pending_resize = None
        self.photo = None
        self.local_font = None
        self.stamp_data = None
        self.stamp_thumbnail = None
        self.stamp_preview_image = None
        self.preview_executor = NativeWorker("preview")
        self.search_executor = NativeWorker("search")
        self.ocr_executor = NativeWorker("ocr")
        self.preview_future = None
        self.preview_request = None
        self.preview_generation = 0
        self.preview_pending = False
        self.preview_poll = None
        self.recovery_path = None
        self.recovery_after = None
        self.view_target = None
        self.closing = False
        self.search_window = None
        self.search_listbox = None
        self.search_future = None
        self.ocr_future = None
        self.search_results = []
        self.search_snapshot = None
        self.search_position = -1
        self.search_info = tk.StringVar(value="")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TButton",
            padding=(12, 8),
            background="white",
            foreground=INK,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure("Compact.TButton", padding=(6, 4), font=("Segoe UI", 9))
        style.configure("Compact.TMenubutton", padding=(6, 4), font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#e5ecef")])
        style.configure(
            "Accent.TButton", background=MINT, foreground=NAVY, font=("Segoe UI", 10, "bold")
        )
        style.configure(
            "Tool.TRadiobutton",
            padding=(6, 6),
            background="white",
            foreground=INK,
            font=("Segoe UI", 9),
        )
        style.map("Tool.TRadiobutton", background=[("selected", "#d9f5e7")])
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Configure>", self.window_resize, add="+")
        self.bind("<Control-o>", lambda e: self.open_dialog())
        self.bind("<Control-s>", lambda e: self.save())
        self.bind(
            "<Control-z>",
            lambda e: (
                self.history(False)
                if not isinstance(self.focus_get(), (tk.Text, tk.Entry, ttk.Spinbox))
                else None
            ),
        )
        self.bind(
            "<Control-y>",
            lambda e: (
                self.history(True)
                if not isinstance(self.focus_get(), (tk.Text, tk.Entry, ttk.Spinbox))
                else None
            ),
        )
        self.bind("<Escape>", lambda e: self.set_mode("view"))
        self.bind("<Control-f>", lambda e: self.find_dialog())
        self.bind("<F3>", lambda e: self.next_match(1))
        self.bind("<Shift-F3>", lambda e: self.next_match(-1))
        self.bind("<Control-Shift-S>", lambda e: self.save_session_dialog())
        self.bind("<Control-Shift-O>", lambda e: self.open_session_dialog())
        self.bind("<Control-g>", lambda e: self.go_to_page())
        self.bind("<Prior>", lambda e: self.navigate(-1))
        self.bind("<Next>", lambda e: self.navigate(1))
        self.refresh()

    def build(self):
        header = tk.Frame(self, bg=NAVY, height=78)
        header.pack(fill="x")
        tk.Label(header, text="F /", bg=NAVY, fg=MINT, font=("Segoe UI", 26, "bold")).pack(
            side="left", padx=(24, 14), pady=16
        )
        names = tk.Frame(header, bg=NAVY)
        names.pack(side="left")
        tk.Label(names, text="Forge PDF", bg=NAVY, fg="white", font=("Segoe UI", 18, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            names, text="Your documents. Your desktop.", bg=NAVY, fg="#abbac4", font=("Segoe UI", 9)
        ).pack(anchor="w")
        ttk.Button(header, text="Save a copy", style="Accent.TButton", command=self.save).pack(
            side="right", padx=(8, 24)
        )
        ttk.Button(header, text="Open PDF", command=self.open_dialog).pack(side="right")
        session = ttk.Menubutton(header, text="Session")
        session_menu = tk.Menu(session, tearoff=False)
        session_menu.add_command(
            label="Save editing session…  Ctrl+Shift+S", command=self.save_session_dialog
        )
        session_menu.add_command(
            label="Open editing session…  Ctrl+Shift+O", command=self.open_session_dialog
        )
        session_menu.add_separator()
        session_menu.add_command(label="Enable local recovery…", command=self.enable_recovery)
        session_menu.add_command(label="Stop local recovery", command=self.stop_recovery)
        session_menu.add_command(
            label="Delete a local recovery snapshot…", command=self.delete_recovery
        )
        session.configure(menu=session_menu)
        session.pack(side="right", padx=8)

        toolbar = tk.Frame(self, bg="white", pady=10, padx=20)
        toolbar.pack(fill="x")
        tools = tk.Frame(toolbar, bg="white")
        tools.pack(fill="x")
        actions = tk.Frame(toolbar, bg="white")
        actions.pack(fill="x", pady=(4, 0))
        ttk.Button(
            tools, style="Compact.TButton", width=0, text="Find…", command=self.find_dialog
        ).pack(side="right")
        ttk.Button(
            tools, style="Compact.TButton", width=0, text="Pages", command=self.toggle_sidebar
        ).pack(side="right")

        for value, label in [
            ("view", "Browse"),
            ("text", "Add text"),
            ("highlight", "Highlight"),
            ("whiteout", "Whiteout"),
            ("note", "Add note"),
            ("image", "Image stamp"),
        ]:
            ttk.Radiobutton(
                tools,
                text=label,
                value=value,
                variable=self.mode,
                style="Tool.TRadiobutton",
                command=self.mode_changed,
            ).pack(side="left", padx=(0, 4))
        self.undo_button = ttk.Button(
            actions,
            style="Compact.TButton",
            text="Undo",
            width=0,
            command=lambda: self.history(False),
        )
        self.undo_button.pack(side="left", padx=(0, 4))
        self.redo_button = ttk.Button(
            actions,
            style="Compact.TButton",
            text="Redo",
            width=0,
            command=lambda: self.history(True),
        )
        self.redo_button.pack(side="left")
        ttk.Button(
            actions,
            style="Compact.TButton",
            text="Clear footer…",
            width=0,
            command=self.clear_footer,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            actions, style="Compact.TButton", text="Fit page", width=0, command=self.fit_page
        ).pack(side="right")
        ttk.Button(
            actions, style="Compact.TButton", text="+", width=3, command=lambda: self.zoom_by(1.2)
        ).pack(side="right")
        self.zoom_label = ttk.Button(
            actions, style="Compact.TButton", text="100%", width=6, command=self.actual_size
        )
        self.zoom_label.pack(side="right")
        ttk.Button(
            actions,
            style="Compact.TButton",
            text="−",
            width=3,
            command=lambda: self.zoom_by(1 / 1.2),
        ).pack(side="right")

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg="white", width=185, padx=12, pady=12)
        self.sidebar = sidebar
        sidebar.pack(side="left", fill="y", padx=(0, 1))
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar, text="DOCUMENT", bg="white", fg="#697c88", font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")
        self.file_label = tk.Label(
            sidebar,
            text="No PDF open",
            bg="white",
            fg=INK,
            wraplength=174,
            justify="left",
            font=("Segoe UI", 11, "bold"),
        )
        self.file_label.pack(anchor="w", pady=(8, 14))
        listframe = tk.Frame(sidebar, bg="white")
        listframe.pack(fill="both", expand=True)
        self.pages = tk.Listbox(
            listframe,
            bg="#f1f5f7",
            fg=INK,
            selectbackground="#caefdd",
            selectforeground=INK,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            exportselection=False,
            font=("Segoe UI", 11),
        )
        self.pages.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listframe, command=self.pages.yview)
        scroll.pack(side="right", fill="y")
        self.pages.configure(yscrollcommand=scroll.set)
        self.pages.bind("<<ListboxSelect>>", self.select_page)
        self.pages.bind("<Button-3>", self.page_context)
        self.pages.bind("<Delete>", lambda e: self.quick_delete())
        for label, fn in [
            ("Rotate 90°", self.rotate),
            ("Move page up", lambda: self.move(-1)),
            ("Move page down", lambda: self.move(1)),
            ("Delete page", self.delete),
            ("Merge another PDF", self.merge),
        ]:
            ttk.Button(sidebar, text=label, command=fn).pack(fill="x", pady=(8, 0))
        more = ttk.Menubutton(sidebar, text="More page actions")
        menu = tk.Menu(more, tearoff=False)
        menu.add_command(
            label="Duplicate page",
            command=lambda: self.change(lambda: self.doc.duplicate(self.page)),
        )
        menu.add_command(
            label="Insert blank page after",
            command=lambda: self.change(lambda: self.doc.insert_blank(self.page)),
        )
        menu.add_command(label="Export this page…", command=self.export_page)
        menu.add_command(label="Export page ranges…", command=self.export_ranges)
        menu.add_command(label="Rotate page ranges right…", command=self.rotate_ranges)
        menu.add_command(label="Set page labels…", command=self.page_labels_dialog)
        menu.add_command(
            label="Rotate left",
            command=lambda: self.change(lambda: self.doc.rotate(self.page, -90)),
        )
        menu.add_command(label="Go to page…  Ctrl+G", command=self.go_to_page)
        menu.add_separator()
        menu.add_command(label="Rotate right", command=self.rotate)
        menu.add_command(label="Move page up", command=lambda: self.move(-1))
        menu.add_command(label="Move page down", command=lambda: self.move(1))
        menu.add_command(label="Delete page", command=self.delete)
        menu.add_command(label="Merge another PDF…", command=self.merge)
        menu.add_command(label="Export checks…", command=self.preflight_dialog)
        menu.add_separator()
        menu.add_command(label="Fill text form field…", command=self.fill_text_field_dialog)
        menu.add_command(label="Edit form fields…", command=self.edit_form_fields_dialog)
        menu.add_command(label="Fill choice form field…", command=self.fill_choice_field_dialog)
        menu.add_command(label="Select radio option…", command=self.select_radio_dialog)
        menu.add_command(label="Toggle checkbox field…", command=self.toggle_checkbox_dialog)
        menu.add_command(label="Edit document metadata…", command=self.metadata_dialog)
        menu.add_command(label="Add bookmark for this page…", command=self.bookmark_dialog)
        menu.add_command(label="Browse bookmarks…", command=self.browse_bookmarks)
        menu.add_command(label="Review notes on this page…", command=self.review_notes)
        menu.add_command(label="Browse all notes…", command=self.browse_notes)
        menu.add_command(
            label="Add native PDF highlight…", command=lambda: self.set_mode("native_highlight")
        )
        menu.add_command(label="Review native highlights…", command=self.review_native_highlights)
        menu.add_command(label="Save encrypted copy…", command=self.save_encrypted)
        menu.add_command(label="OCR searchable image copy…", command=self.export_ocr)
        menu.add_command(
            label="OCR text layer on scanned pages…",
            command=lambda: self.export_ocr(preserve_pages=True),
        )
        menu.add_command(
            label="Rasterized redacted export…", command=lambda: self.set_mode("raster_redact")
        )
        actions_menu = ttk.Menubutton(
            actions, text="Page actions", menu=menu, style="Compact.TMenubutton", width=0
        )
        actions_menu.pack(side="left", padx=(8, 0))
        more.configure(menu=menu)
        more.pack(fill="x", pady=(8, 0))
        tk.Label(
            sidebar,
            text=f"VERSION  {__version__}",
            bg="white",
            fg="#697c88",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(18, 0))

        workspace = tk.Frame(body, bg=PAPER)
        self.workspace = workspace
        workspace.pack(side="left", fill="both", expand=True)
        self.hint = tk.Label(
            workspace, text="", bg=PAPER, fg="#516675", anchor="w", padx=22, pady=12
        )
        self.hint.pack(fill="x")
        self.textbar = tk.Frame(workspace, bg=PAPER, padx=22, pady=6)
        tk.Label(self.textbar, text="Text", bg=PAPER, fg=INK).pack(side="left", padx=(0, 8))
        self.text_entry = tk.Entry(self.textbar, relief="solid", borderwidth=1)
        self.text_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.text_entry.insert(0, "Your text here")
        tk.Label(self.textbar, text="Size", bg=PAPER, fg=INK).pack(side="left", padx=10)
        ttk.Spinbox(self.textbar, from_=8, to=72, textvariable=self.font_size, width=5).pack(
            side="left"
        )
        ttk.Button(self.textbar, text="Local font…", command=self.choose_font).pack(
            side="left", padx=6
        )
        ttk.Button(self.textbar, text="Check glyphs", command=self.check_glyphs).pack(side="left")
        self.imagebar = tk.Frame(workspace, bg=PAPER, padx=22, pady=6)
        ttk.Button(self.imagebar, text="Choose PNG/JPEG…", command=self.choose_stamp).pack(
            side="left"
        )
        self.stamp_label = ttk.Label(
            self.imagebar, text="Choose an image, then drag its placement rectangle."
        )
        self.stamp_label.pack(side="left", padx=8)
        canvasframe = tk.Frame(workspace, bg="#e5eaee")
        canvasframe.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.canvas = tk.Canvas(canvasframe, bg="#e5eaee", highlightthickness=1, takefocus=True)
        yscroll = ttk.Scrollbar(canvasframe, command=self.canvas.yview)
        xscroll = ttk.Scrollbar(canvasframe, orient="horizontal", command=self.canvas.xview)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.canvas.bind("<Configure>", self.resize)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Control-MouseWheel>", self.wheel_zoom)
        self.canvas.configure(yscrollincrement=24)
        self.status = tk.Label(self, text="", bg="white", fg="#516675", anchor="w", padx=22, pady=8)
        self.status.pack(fill="x")

    def error(self, exc):
        messagebox.showerror("Forge PDF", str(exc), parent=self)

    def discard_ok(self):
        if not self.doc or not self.doc.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", "Save a copy before continuing?", parent=self
        )
        if answer is None:
            return False
        return self.save() if answer else True

    def open_dialog(self):
        path = filedialog.askopenfilename(
            parent=self, title="Open PDF", filetypes=[("PDF documents", "*.pdf")]
        )
        if path:
            self.load(Path(path))

    def load(self, path):
        if not self.discard_ok():
            return
        try:
            try:
                candidate = Document.open(path)
            except ValueError as exc:
                if "Password" not in str(exc):
                    raise
                password = simpledialog.askstring(
                    "Open protected PDF",
                    "PDF password (saved edited copies will be unencrypted):",
                    show="*",
                    parent=self,
                )
                if password is None:
                    return
                candidate = Document.open(path, password)
            candidate.render(0, 0.2)  # Validate rendering before replacing the current document.
            self.stop_recovery()
            self.doc, self.path, self.page, self.fit = candidate, path, 0, False
            self.zoom = 1.0
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.refresh()
        except Exception as exc:
            self.error(exc)

    def save(self):
        if not self.doc:
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save an edited copy",
            initialfile=f"{self.path.stem}-edited.pdf",
            initialdir=self.path.parent,
            defaultextension=".pdf",
            filetypes=[("PDF documents", "*.pdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            self.doc.save_copy(Path(path), overwrite=Path(path).exists())
            self.refresh()
            self.status.configure(text=f"Saved copy: {path}")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def save_encrypted(self):
        if not self.doc:
            return False
        password = simpledialog.askstring(
            "Save encrypted copy", "Password for the new PDF:", show="*", parent=self
        )
        if password is None:
            return False
        confirm = simpledialog.askstring(
            "Save encrypted copy", "Confirm password:", show="*", parent=self
        )
        if confirm is None:
            return False
        if not password or password != confirm:
            self.error(ValueError("Passwords must match and cannot be empty."))
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save an AES-256 encrypted copy",
            initialfile=f"{self.path.stem}-encrypted.pdf",
            initialdir=self.path.parent,
            defaultextension=".pdf",
            filetypes=[("PDF documents", "*.pdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            self.doc.save_copy(Path(path), overwrite=Path(path).exists(), password=password)
            self.refresh()
            self.status.configure(text=f"Saved encrypted copy: {path}")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def fill_text_field_dialog(self):
        if not self.doc:
            return
        try:
            fields = self.doc.text_fields()
            if not fields:
                messagebox.showinfo("Forge PDF", "No editable text form fields found.", parent=self)
                return
            name = simpledialog.askstring(
                "Text form fields",
                "Field name (choose from: " + ", ".join(fields) + "):",
                parent=self,
            )
            if name is None:
                return
            if name not in fields:
                raise ValueError("Choose an editable text form field from the list.")
            value = simpledialog.askstring(
                "Fill form field", f"Value for {name}:", initialvalue=fields[name], parent=self
            )
            if value is not None:
                self.change(lambda: self.doc.fill_text_field(name, value))
        except Exception as exc:
            self.error(exc)

    def edit_form_fields_dialog(self):
        if not self.doc:
            return
        fields = {}
        for name, value in self.doc.text_fields().items():
            fields[name] = ("Text", value, [])
        for name, (value, options) in self.doc.choice_fields().items():
            fields[name] = ("Choice", value, options)
        for name, checked in self.doc.checkbox_fields().items():
            fields[name] = ("Checkbox", checked, [])
        for name, (value, options) in self.doc.radio_fields().items():
            fields[name] = ("Radio", value, options)
        if not fields:
            messagebox.showinfo(
                "Forge PDF", "No supported editable form fields found.", parent=self
            )
            return
        names = sorted(fields)
        dialog = tk.Toplevel(self)
        dialog.title("Edit form fields")
        dialog.geometry("580x400")
        dialog.transient(self)
        ttk.Label(dialog, text="Choose a field, edit its value, then apply.").pack(
            anchor="w", padx=12, pady=(12, 6)
        )
        listing = tk.Listbox(dialog, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12)
        for name in names:
            kind, value, _ = fields[name]
            listing.insert("end", f"{name}  ·  {kind}  ·  {value}")
        value_label = ttk.Label(dialog, text="")
        value_label.pack(anchor="w", padx=12, pady=(10, 3))
        text_value = ttk.Entry(dialog)
        choice_value = ttk.Combobox(dialog, state="readonly")
        check_value = tk.BooleanVar(value=False)
        checkbox = ttk.Checkbutton(dialog, text="Checked", variable=check_value)

        def selected_name():
            return names[listing.curselection()[0]] if listing.curselection() else None

        def select_field(event=None):
            text_value.pack_forget()
            choice_value.pack_forget()
            checkbox.pack_forget()
            name = selected_name()
            if name is None:
                return
            kind, value, options = fields[name]
            value_label.configure(text=f"{name} ({kind})")
            if kind == "Text":
                text_value.delete(0, "end")
                text_value.insert(0, value)
                text_value.pack(fill="x", padx=12)
            elif kind in ("Choice", "Radio"):
                choice_value.configure(values=options)
                choice_value.set(value)
                choice_value.pack(fill="x", padx=12)
            else:
                check_value.set(value)
                checkbox.pack(anchor="w", padx=12)

        def apply_value():
            name = selected_name()
            if name is None:
                return
            kind, _, options = fields[name]
            previous = self.doc.data
            if kind == "Text":
                value = text_value.get()
                self.change(lambda: self.doc.fill_text_field(name, value))
            elif kind in ("Choice", "Radio"):
                value = choice_value.get()
                if value in options:
                    if kind == "Radio":
                        self.change(lambda: self.doc.select_radio(name, value))
                    else:
                        self.change(lambda: self.doc.fill_choice_field(name, value))
            else:
                value = check_value.get()
                self.change(lambda: self.doc.set_checkbox(name, value))
            if self.doc.data == previous:
                return
            fields[name] = (kind, value, options)
            index = listing.curselection()[0]
            listing.delete(index)
            listing.insert(index, f"{name}  ·  {kind}  ·  {value}")
            listing.selection_set(index)

        listing.bind("<<ListboxSelect>>", select_field)
        controls = ttk.Frame(dialog)
        controls.pack(fill="x", padx=12, pady=12)
        ttk.Button(controls, text="Apply value", command=apply_value).pack(side="left")
        ttk.Button(controls, text="Close", command=dialog.destroy).pack(side="right")
        listing.selection_set(0)
        select_field()
        listing.focus_set()

    def fill_choice_field_dialog(self):
        if not self.doc:
            return
        try:
            fields = self.doc.choice_fields()
            if not fields:
                messagebox.showinfo(
                    "Forge PDF", "No editable simple choice fields found.", parent=self
                )
                return
            name = simpledialog.askstring(
                "Choice form fields",
                "Field name (choose from: " + ", ".join(fields) + "):",
                parent=self,
            )
            if name is None:
                return
            if name not in fields:
                raise ValueError("Choose an editable choice field from the list.")
            current, options = fields[name]
            value = simpledialog.askstring(
                "Fill choice field",
                f"{name}: choose from {', '.join(options)}",
                initialvalue=current,
                parent=self,
            )
            if value is not None:
                self.change(lambda: self.doc.fill_choice_field(name, value))
        except Exception as exc:
            self.error(exc)

    def select_radio_dialog(self):
        if not self.doc:
            return
        try:
            fields = self.doc.radio_fields()
            if not fields:
                messagebox.showinfo("Forge PDF", "No editable radio groups found.", parent=self)
                return
            name = simpledialog.askstring(
                "Radio groups",
                "Field name (choose from: " + ", ".join(fields) + "):",
                parent=self,
            )
            if name is None:
                return
            if name not in fields:
                raise ValueError("Choose an editable radio group from the list.")
            current, options = fields[name]
            value = simpledialog.askstring(
                "Radio option",
                f"{name}: choose from {', '.join(options)}",
                initialvalue=current,
                parent=self,
            )
            if value is not None:
                self.change(lambda: self.doc.select_radio(name, value))
        except Exception as exc:
            self.error(exc)

    def toggle_checkbox_dialog(self):
        if not self.doc:
            return
        try:
            fields = self.doc.checkbox_fields()
            if not fields:
                messagebox.showinfo(
                    "Forge PDF", "No editable single-state checkboxes found.", parent=self
                )
                return
            name = simpledialog.askstring(
                "Checkbox fields",
                "Field name (choose from: " + ", ".join(fields) + "):",
                parent=self,
            )
            if name is not None:
                if name not in fields:
                    raise ValueError("Choose an editable single-state checkbox from the list.")
                self.change(lambda: self.doc.set_checkbox(name, not fields[name]))
        except Exception as exc:
            self.error(exc)

    def metadata_dialog(self):
        if not self.doc:
            return
        values = self.doc.metadata()
        for key in ("/Title", "/Author", "/Subject", "/Keywords"):
            value = simpledialog.askstring(
                "Document metadata", key[1:] + ":", initialvalue=values[key], parent=self
            )
            if value is None:
                return
            values[key] = value
        self.change(lambda: self.doc.set_metadata(values))

    def bookmark_dialog(self):
        if not self.doc:
            return
        title = simpledialog.askstring(
            "Add bookmark", f"Bookmark title for page {self.page + 1}:", parent=self
        )
        if title is not None:
            self.change(lambda: self.doc.add_bookmark(title, self.page))

    def browse_bookmarks(self):
        if not self.doc:
            return
        try:
            bookmarks = self.doc.bookmarks()
        except Exception as exc:
            self.error(exc)
            return
        if not bookmarks:
            messagebox.showinfo("Forge PDF", "No usable bookmarks in this PDF.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Document bookmarks")
        dialog.geometry("480x360")
        listing = tk.Listbox(dialog, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12, pady=12)
        for item in bookmarks:
            listing.insert(
                "end", f"{'  ' * item['depth']}{item['title']}  ·  page {item['page'] + 1}"
            )

        def navigate(event=None):
            if listing.curselection():
                self.show_page(bookmarks[listing.curselection()[0]]["page"])
                dialog.destroy()

        listing.bind("<Double-Button-1>", navigate)
        ttk.Button(dialog, text="Go to selected", command=navigate).pack(pady=(0, 12))

    def review_notes(self):
        if not self.doc:
            return
        try:
            notes = self.doc.notes(self.page)
        except Exception as exc:
            self.error(exc)
            return
        if not notes:
            messagebox.showinfo("Forge PDF", "No text notes on this page.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Text notes · page {self.page + 1}")
        dialog.geometry("520x340")
        listing = tk.Listbox(dialog, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12, pady=12)

        def populate():
            listing.delete(0, "end")
            for note in self.doc.notes(self.page):
                listing.insert("end", note.replace("\n", " ")[:160])

        def delete_selected():
            if listing.curselection():
                index = listing.curselection()[0]
                self.change(lambda: self.doc.delete_note(self.page, index))
                populate()

        def edit_selected():
            if not listing.curselection():
                return
            index = listing.curselection()[0]
            current = self.doc.notes(self.page)[index]
            revised = simpledialog.askstring(
                "Edit text note", "Note text:", initialvalue=current, parent=dialog
            )
            if revised is None:
                return
            self.change(lambda: self.doc.update_note(self.page, index, revised))
            populate()
            listing.selection_set(index)

        populate()
        ttk.Button(dialog, text="Edit selected note", command=edit_selected).pack(pady=(0, 8))
        ttk.Button(dialog, text="Delete selected note", command=delete_selected).pack(pady=(0, 12))

    def browse_notes(self):
        if not self.doc:
            return
        try:
            notes = self.doc.all_notes()
        except Exception as exc:
            self.error(exc)
            return
        if not notes:
            messagebox.showinfo("Forge PDF", "No text notes in this PDF.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Document text notes")
        dialog.geometry("560x360")
        listing = tk.Listbox(dialog, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12, pady=12)
        for note in notes:
            excerpt = note["text"].replace("\n", " ")[:160]
            listing.insert("end", f"Page {note['page'] + 1}: {excerpt}")

        def navigate(event=None):
            if listing.curselection():
                self.show_page(notes[listing.curselection()[0]]["page"])
                dialog.destroy()

        listing.bind("<Double-Button-1>", navigate)
        ttk.Button(dialog, text="Go to selected page", command=navigate).pack(pady=(0, 12))

    def review_native_highlights(self):
        if not self.doc:
            return
        try:
            count = self.doc.highlight_annotation_count(self.page)
        except Exception as exc:
            self.error(exc)
            return
        if not count:
            messagebox.showinfo("Forge PDF", "No native highlights on this page.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Native highlights · page {self.page + 1}")
        dialog.geometry("400x320")
        listing = tk.Listbox(dialog, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12, pady=12)

        def populate():
            listing.delete(0, "end")
            for number in range(self.doc.highlight_annotation_count(self.page)):
                listing.insert("end", f"Native highlight {number + 1}")

        def delete_selected():
            if listing.curselection():
                index = listing.curselection()[0]
                self.change(lambda: self.doc.delete_native_highlight(self.page, index))
                populate()

        populate()
        ttk.Button(dialog, text="Delete selected highlight", command=delete_selected).pack(
            pady=(0, 12)
        )

    def rotate_ranges(self):
        if not self.doc:
            return
        selection = simpledialog.askstring(
            "Rotate page ranges",
            f"Pages to rotate right (1-{self.doc.count}, e.g. 1,3-5):",
            parent=self,
        )
        if selection is not None:
            try:
                indices = parse_page_ranges(selection, self.doc.count)
                self.change(lambda: self.doc.rotate_pages(indices))
            except Exception as exc:
                self.error(exc)

    def page_labels_dialog(self):
        if not self.doc:
            return
        first = simpledialog.askinteger(
            "Page labels",
            "First page:",
            initialvalue=self.page + 1,
            minvalue=1,
            maxvalue=self.doc.count,
            parent=self,
        )
        if first is None:
            return
        last = simpledialog.askinteger(
            "Page labels",
            "Last page:",
            initialvalue=self.doc.count,
            minvalue=first,
            maxvalue=self.doc.count,
            parent=self,
        )
        if last is None:
            return
        prefix = simpledialog.askstring("Page labels", "Prefix (optional):", parent=self)
        if prefix is None:
            return
        style = simpledialog.askstring(
            "Page labels",
            "Style: decimal, roman or letters:",
            initialvalue="decimal",
            parent=self,
        )
        if style is None:
            return
        start = simpledialog.askinteger(
            "Page labels",
            "Starting number:",
            initialvalue=1,
            minvalue=1,
            maxvalue=100000,
            parent=self,
        )
        if start is not None:
            self.change(
                lambda: self.doc.set_page_labels(
                    first - 1, last - 1, prefix, style.strip().lower(), start
                )
            )

    def export_ocr(self, preserve_pages=False):
        if not self.doc:
            return False
        if self.ocr_future is not None and not self.ocr_future.done():
            self.status.configure(text="An OCR export is already running.")
            return False
        bundle = Path(sys.executable).resolve().parent / "Support" / "ocr"
        languages = sorted(path.stem for path in (bundle / "tessdata").glob("*.traineddata"))
        if not languages:
            self.error(ValueError("Offline OCR languages are unavailable in this build."))
            return False
        language = languages[0]
        if len(languages) > 1:
            choice = simpledialog.askstring(
                "OCR language",
                f"Choose an installed language code: {', '.join(languages)}",
                initialvalue="eng" if "eng" in languages else language,
                parent=self,
            )
            if choice is None:
                return False
            language = choice.strip().lower()
            if language not in languages:
                self.error(ValueError("Choose one of the installed OCR languages."))
                return False
        title = "OCR text layer copy" if preserve_pages else "OCR searchable image copy"
        warning = (
            "This copies the original page objects and adds invisible OCR text. It accepts "
            "only unrotated, uncropped image pages without existing text, forms or signatures. "
            "Graphics, links and bookmarks are retained, but the copy is unencrypted and "
            "limited to 20 pages. Check text placement and recognition before sharing."
            if preserve_pages
            else "The copy loses vector quality, forms, links, bookmarks, annotations, metadata, "
            "accessibility structure and signatures. It is unencrypted and limited to 20 pages. "
            "Check recognized text before sharing."
        )
        if not messagebox.askyesno(
            title,
            f"Create a new PDF with offline {language} OCR? The current file stays open. "
            + warning,
            parent=self,
        ):
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save OCR text-layer PDF" if preserve_pages else "Save searchable image PDF",
            initialfile=f"{self.path.stem}-ocr-layer.pdf"
            if preserve_pages and self.path
            else f"{self.path.stem}-searchable.pdf"
            if self.path
            else "searchable.pdf",
            initialdir=self.path.parent if self.path else None,
            defaultextension=".pdf",
            filetypes=[("PDF documents", "*.pdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            self.ocr_future = self.ocr_executor.submit(
                self.doc.data,
                {
                    "path": path,
                    "overwrite": Path(path).exists(),
                    "language": language,
                    "preserve_pages": preserve_pages,
                },
            )
        except Exception as exc:
            self.error(exc)
            return False
        future = self.ocr_future
        dialog = tk.Toplevel(self)
        dialog.title("Offline OCR progress")
        dialog.transient(self)
        progress_text = tk.StringVar(value="Preparing OCR copy...")
        ttk.Label(dialog, textvariable=progress_text, width=46).pack(padx=18, pady=16)

        def cancel():
            if future.done():
                poll()
                return
            future.cancel()
            self.status.configure(
                text="OCR export cancelled. Check the destination for a completed copy."
            )
            dialog.destroy()

        ttk.Button(dialog, text="Cancel OCR", command=cancel).pack(pady=(0, 16))
        dialog.protocol("WM_DELETE_WINDOW", cancel)

        def poll():
            if self.closing or not dialog.winfo_exists():
                return
            if not future.done():
                done, total = future.progress
                progress_text.set(
                    f"Processed {done} of {total} pages" if total else "Preparing OCR copy..."
                )
                dialog.after(100, poll)
                return
            dialog.destroy()
            try:
                future.result()
                self.status.configure(
                    text=f"OCR copy saved: {path}. Check recognized text before sharing."
                )
            except Exception as exc:
                self.error(exc)

        dialog.after(100, poll)
        return True

    def export_redacted(self, box):
        if not messagebox.askyesno(
            "Rasterized redacted export",
            "This makes a new image-only PDF with the selected area blacked out. "
            "Searchable text, forms, links, notes, bookmarks, accessibility structure, "
            "metadata and signatures are removed from every page. The new PDF is unencrypted. The current document "
            "and any saved editing sessions may still contain the original content. Continue?",
            parent=self,
        ):
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save rasterized redacted PDF",
            initialfile=f"{self.path.stem}-redacted.pdf",
            initialdir=self.path.parent,
            defaultextension=".pdf",
            filetypes=[("PDF documents", "*.pdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            self.doc.export_raster_redacted(
                self.page, box, Path(path), overwrite=Path(path).exists()
            )
            self.status.configure(
                text=f"Rasterized redacted copy saved: {path}. Review it before sharing."
            )
            self.set_mode("view")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def change(self, fn):
        if not self.doc:
            return
        try:
            previous = self.doc.data
            fn()
            self.refresh()
            if self.doc.data != previous:
                self.schedule_recovery()
        except Exception as exc:
            self.error(exc)

    def schedule_recovery(self):
        if self.recovery_after:
            self.after_cancel(self.recovery_after)
            self.recovery_after = None
        if self.recovery_path and self.doc and not self.closing:
            self.recovery_after = self.after(1200, self.write_recovery)

    def write_recovery(self):
        self.recovery_after = None
        if not self.recovery_path or not self.doc or self.closing:
            return
        try:
            if not is_recovery_snapshot(self.recovery_path):
                self.stop_recovery()
                raise ValueError("Recovery file is missing or changed; updates stopped.")
            save_session(
                self.doc,
                self.recovery_path,
                self.page,
                self.zoom,
                overwrite=self.recovery_path.exists(),
                include_history=False,
                recovery=True,
            )
            self.status.configure(text=f"Local recovery snapshot updated: {self.recovery_path}")
        except Exception as exc:
            self.status.configure(text=f"Local recovery failed: {exc}")

    def enable_recovery(self):
        if not self.doc:
            return False
        if self.doc.opened_encrypted:
            self.error(ValueError("Local recovery is unavailable for password-opened PDFs."))
            return False
        if self.recovery_path:
            self.error(ValueError("Stop or delete the current recovery snapshot first."))
            return False
        if not messagebox.askyesno(
            "Enable local recovery",
            "Keep an unencrypted local recovery file after edits? It contains the current PDF "
            "and original filenames, but no Undo history. It remains until you delete it. "
            "Do not use this for sensitive documents.",
            parent=self,
        ):
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Choose a local recovery file",
            initialfile=f"{self.path.stem}-recovery.forgepdf",
            initialdir=self.path.parent,
            defaultextension=".forgepdf",
            filetypes=[("Forge PDF sessions", "*.forgepdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            candidate = Path(path).resolve()
            if candidate.exists() and not is_recovery_snapshot(candidate):
                raise ValueError("Choose a new file or an existing Forge PDF recovery snapshot.")
            save_session(
                self.doc,
                candidate,
                self.page,
                self.zoom,
                overwrite=candidate.exists(),
                include_history=False,
                recovery=True,
            )
            self.stop_recovery()
            self.recovery_path = candidate
            self.status.configure(text=f"Local recovery enabled: {candidate}")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def stop_recovery(self):
        if self.recovery_after:
            self.after_cancel(self.recovery_after)
            self.recovery_after = None
        self.recovery_path = None

    def delete_recovery(self):
        path = self.recovery_path
        if path is None:
            chosen = filedialog.askopenfilename(
                parent=self,
                title="Choose a Forge PDF recovery snapshot to delete",
                filetypes=[("Forge PDF sessions", "*.forgepdf")],
            )
            if not chosen:
                return False
            path = Path(chosen)
        try:
            if not is_recovery_snapshot(path):
                raise ValueError("Choose a recovery snapshot created by Forge PDF.")
            original = path.stat()
            if not messagebox.askyesno(
                "Delete local recovery",
                f"Permanently delete this unencrypted recovery snapshot?\n{path}",
                parent=self,
            ):
                return False
            current = path.stat()

            def identity(stat):
                return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

            if path.is_symlink() or identity(current) != identity(original):
                raise ValueError("Recovery snapshot changed before deletion; choose it again.")
            path.unlink()
            if self.recovery_path == path:
                self.stop_recovery()
            self.status.configure(text="Local recovery snapshot deleted.")
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def rotate(self):
        self.change(lambda: self.doc.rotate(self.page))

    def move(self, delta):
        if self.doc and 0 <= self.page + delta < self.doc.count:
            self.change(lambda: self.doc.move(self.page, self.page + delta))
            self.page += delta
            self.refresh()

    def delete(self):
        if self.doc and messagebox.askyesno(
            "Delete page",
            f"Remove page {self.page + 1} from this copy? You can undo this.",
            parent=self,
        ):
            self.change(lambda: self.doc.delete(self.page))

    def merge(self):
        if not self.doc:
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Append pages from another PDF",
            filetypes=[("PDF documents", "*.pdf")],
        )
        if path:
            self.change(lambda: self.doc.append(Path(path)))

    def export_page(self):
        if not self.doc:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export current page",
            initialdir=self.path.parent,
            initialfile=f"{self.path.stem}-page-{self.page + 1}.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF documents", "*.pdf")],
            confirmoverwrite=True,
        )
        if path:
            try:
                self.doc.export_page(self.page, Path(path), overwrite=Path(path).exists())
                self.status.configure(text=f"Exported page {self.page + 1}: {path}")
            except Exception as exc:
                self.error(exc)

    def review_export_pages(self, indices):
        original_page = self.page
        approved = False
        dialog = tk.Toplevel(self)
        dialog.title("Review page export order")
        dialog.geometry("420x440")
        dialog.transient(self)
        ttk.Label(
            dialog,
            text="Select a row to preview its source page.\n"
            "Export creates one new PDF in this order.\n"
            "Subset export is not secure redaction.",
            wraplength=390,
        ).pack(padx=12, pady=12)
        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=12)
        scroll = ttk.Scrollbar(frame)
        scroll.pack(side="right", fill="y")
        order = tk.Listbox(frame, yscrollcommand=scroll.set, exportselection=False)
        order.pack(side="left", fill="both", expand=True)
        scroll.configure(command=order.yview)
        for output, index in enumerate(indices, 1):
            order.insert("end", f"Output page {output} ← document page {index + 1}")
        order.bind(
            "<<ListboxSelect>>",
            lambda event: (
                self.show_page(indices[order.curselection()[0]]) if order.curselection() else None
            ),
        )

        def accept():
            nonlocal approved
            approved = True
            dialog.destroy()

        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=12, pady=12)
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="left")
        ttk.Button(actions, text="Continue to save", command=accept).pack(side="right")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        order.focus_set()
        dialog.grab_set()
        self.wait_window(dialog)
        self.show_page(original_page)
        return approved

    def export_ranges(self):
        if not self.doc:
            return
        selection = simpledialog.askstring(
            "Export page ranges",
            f"Pages from 1 to {self.doc.count}, for example 1,3-5.\n"
            "Pages follow your entered order; duplicates are rejected.",
            parent=self,
            initialvalue=str(self.page + 1),
        )
        if selection is None:
            return
        try:
            indices = parse_page_ranges(selection, self.doc.count)
            if not self.review_export_pages(indices):
                return
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Export selected pages",
                initialdir=self.path.parent,
                initialfile=f"{self.path.stem}-selected-pages.pdf",
                defaultextension=".pdf",
                filetypes=[("PDF documents", "*.pdf")],
                confirmoverwrite=True,
            )
            if not path:
                return
            self.doc.export_pages(indices, Path(path), overwrite=Path(path).exists())
            self.status.configure(text=f"Exported {len(indices)} selected pages: {path}")
        except Exception as exc:
            self.error(exc)

    def clear_footer(self):
        if not self.doc:
            return
        height = simpledialog.askinteger(
            "Clear footer on every page",
            "Whiteout height in pixels at 100% zoom:\n"
            "Applies to the bottom of every page. One Undo restores it.\n"
            "Visual cover only; this is not secure redaction.",
            initialvalue=5,
            minvalue=1,
            maxvalue=10000,
            parent=self,
        )
        if height is None:
            return
        self.status.configure(text=f"Clearing {height}px from the bottom of every page…")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            self.change(lambda: self.doc.clear_footer(height))
        finally:
            self.configure(cursor="")

    def actual_size(self):
        self.fit = False
        self.zoom = 1.0
        self.render()

    def history(self, redo):
        self.change(lambda: self.doc.redo() if redo else self.doc.undo())

    def select_page(self, event=None):
        selected = self.pages.curselection()
        if selected and selected[0] != self.page:
            self.show_page(selected[0])

    def show_page(self, index, bottom=False):
        if not self.doc or self.drag_start is not None:
            return
        self.page = max(0, min(index, self.doc.count - 1))
        self.pages.selection_clear(0, "end")
        self.pages.selection_set(self.page)
        self.pages.see(self.page)
        self.view_target = (0, 1 if bottom else 0)
        self.render()

    def navigate(self, direction):
        if self.doc:
            self.show_page(self.page + direction, bottom=direction < 0)
        return "break"

    def wheel(self, event):
        if not self.doc or self.drag_start is not None:
            return "break"
        self.wheel_delta += event.delta
        steps = int(self.wheel_delta / 120)
        if not steps:
            return "break"
        self.wheel_delta -= steps * 120
        top, bottom = self.canvas.yview()
        if steps < 0 and bottom >= 0.999 and self.page < self.doc.count - 1:
            self.show_page(self.page + 1)
        elif steps > 0 and top <= 0.001 and self.page > 0:
            self.show_page(self.page - 1, bottom=True)
        else:
            self.canvas.yview_scroll(-steps * 3, "units")
        return "break"

    def wheel_zoom(self, event):
        if self.drag_start is None and event.delta:
            self.zoom_by(1.1 if event.delta > 0 else 1 / 1.1)
        return "break"

    def go_to_page(self):
        if not self.doc:
            return
        page = simpledialog.askinteger(
            "Go to page",
            f"Page number (1–{self.doc.count}):",
            initialvalue=self.page + 1,
            minvalue=1,
            maxvalue=self.doc.count,
            parent=self,
        )
        if page is not None:
            self.show_page(page - 1)

    def quick_delete(self):
        self.change(lambda: self.doc.delete(self.page))

    def page_context(self, event):
        if not self.doc:
            return
        index = self.pages.nearest(event.y)
        bounds = self.pages.bbox(index)
        if bounds is None or not bounds[1] <= event.y < bounds[1] + bounds[3]:
            return
        self.show_page(index)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Delete page",
            command=self.quick_delete,
            state="normal" if self.doc.count > 1 else "disabled",
        )
        menu.add_command(
            label="Duplicate page",
            command=lambda: self.change(lambda: self.doc.duplicate(self.page)),
        )
        menu.add_separator()
        menu.add_command(label="Rotate right", command=self.rotate)
        menu.add_command(
            label="Rotate left",
            command=lambda: self.change(lambda: self.doc.rotate(self.page, -90)),
        )
        menu.add_command(label="Export page…", command=self.export_page)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def cancel_drag(self):
        self.drag_start = None
        self.drag_tool = None
        self.canvas.delete("selection")
        if self.canvas.grab_current() == self.canvas:
            self.canvas.grab_release()

    def set_mode(self, mode):
        self.mode.set(mode)
        self.mode_changed()

    def mode_changed(self):
        self.cancel_drag()
        if self.mode.get() == "text":
            self.textbar.pack(fill="x", after=self.hint)
        else:
            self.textbar.pack_forget()
        if self.mode.get() == "image":
            self.imagebar.pack(fill="x", after=self.hint)
        else:
            self.imagebar.pack_forget()
        self.canvas.configure(cursor="crosshair" if self.mode.get() != "view" else "")
        self.hint.configure(
            text={
                "view": "Browse your pages. All edits stay here until you save a copy.",
                "text": "Enter your text above, then click on the page to place it. Ctrl+Z to undo.",
                "highlight": "Drag across an area to highlight it. Highlights do not remove or redact text.",
                "whiteout": "Drag to cover an area in white. Visual cover only — underlying content can still be extracted.",
                "note": "Click on the page to add a native text note. Review or delete notes through Page actions.",
                "native_highlight": "Drag an area to add a native PDF highlight annotation. Later page-content edits may flatten it.",
                "raster_redact": "Drag an area to black out in a new image-only PDF. Source objects are discarded; current file stays open.",
                "image": "Choose a PNG/JPEG, then drag a rectangle. The image fits inside it; preview before release.",
            }[self.mode.get()]
        )

    def refresh(self):
        self.pages.delete(0, "end")
        if self.doc:
            self.page = min(self.page, self.doc.count - 1)
            labels = self.doc.page_labels()
            for n in range(self.doc.count):
                self.pages.insert("end", f"  {n + 1:02d}    {labels[n]}")
            self.pages.selection_set(self.page)
            self.pages.see(self.page)
            self.file_label.configure(text=self.path.name)
        dirty = self.doc and self.doc.dirty
        self.title(f"{'* ' if dirty else ''}{self.path.name + ' — ' if self.path else ''}Forge PDF")
        self.status.configure(
            text="Unsaved changes  •  Originals are kept untouched"
            if dirty
            else "Ready  •  No uploads. No account. No subscription."
        )
        self.undo_button.configure(
            state="normal" if self.doc and self.doc.undo_stack else "disabled"
        )
        self.redo_button.configure(
            state="normal" if self.doc and self.doc.redo_stack else "disabled"
        )
        self.mode_changed()
        self.render()

    def resize(self, event=None):
        if self.pending_resize:
            self.after_cancel(self.pending_resize)
        self.pending_resize = self.after(120, self.render)

    def fit_page(self):
        self.fit = True
        self.render()

    def zoom_by(self, multiplier):
        self.fit = False
        self.zoom = max(0.2, min(3, self.zoom * multiplier))
        self.render()

    def render(self):
        self.pending_resize = None
        if self.drag_start is not None or self.closing:
            return
        self.preview_generation += 1
        if not self.doc:
            self.preview_request = None
            self.preview_pending = False
            self.canvas.delete("all")
            self.canvas.create_text(
                max(100, self.canvas.winfo_width() / 2),
                max(100, self.canvas.winfo_height() / 2),
                text="Open a PDF to start.  Ctrl+O",
                fill=INK,
                font=("Segoe UI", 18),
            )
            return
        self.preview_pending = True
        self.preview_request = (
            self.preview_generation,
            self.doc.data,
            self.page,
            self.zoom,
            self.fit,
            max(1, self.canvas.winfo_width()),
            max(1, self.canvas.winfo_height()),
            self.view_target or (self.canvas.xview()[0], self.canvas.yview()[0]),
        )
        self.view_target = None
        self._start_preview()

    def _start_preview(self):
        if self.preview_future is not None or self.preview_request is None or self.closing:
            return
        request = self.preview_request
        self.preview_request = None

        generation, data, index, zoom, fit, cw, ch, view = request
        params = dict(
            generation=generation, page=index, zoom=zoom, fit=fit, cw=cw, ch=ch, view=view
        )
        self.preview_future = self.preview_executor.submit(data, params)
        self.preview_poll = self.after(15, self._poll_preview)

    def _poll_preview(self):
        self.preview_poll = None
        if self.closing:
            return
        future = self.preview_future
        if not future.done() or self.drag_start is not None:
            self.preview_poll = self.after(15, self._poll_preview)
            return
        self.preview_future = None
        try:
            generation, image, width, height, zoom, cw, ch, view = future.result()
            if generation == self.preview_generation and self.doc:
                self.canvas.delete("all")
                self.scale_x, self.scale_y = image.width / width, image.height / height
                self.offset_x, self.offset_y = max(24, (cw - image.width) / 2), 24
                self.photo = ImageTk.PhotoImage(image)
                self.canvas.create_image(
                    self.offset_x, self.offset_y, image=self.photo, anchor="nw"
                )
                self.canvas.configure(
                    scrollregion=(0, 0, max(cw, image.width + 48), max(ch, image.height + 48))
                )
                self.canvas.xview_moveto(view[0])
                self.canvas.yview_moveto(view[1])
                self.zoom = zoom
                self.zoom_label.configure(text=f"{self.scale_x:.0%}")
                self.preview_pending = False
        except Exception as exc:
            if self.preview_request is None:
                self.preview_pending = False
                self.error(exc)
        self._start_preview()

    def window_resize(self, event):
        if event.widget is self:
            self.status.configure(wraplength=max(200, self.winfo_width() - 44))
            self.hint.configure(wraplength=max(200, self.workspace.winfo_width() - 44))

    def toggle_sidebar(self):
        if self.sidebar.winfo_manager():
            self.sidebar.pack_forget()
        else:
            self.sidebar.pack(side="left", fill="y", padx=(0, 1), before=self.workspace)

    def choose_font(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a local TrueType font",
            filetypes=[("TrueType fonts", "*.ttf")],
        )
        if not path:
            return
        try:
            text_font(self.text_entry.get(), Path(path))
            self.local_font = Path(path)
            self.status.configure(
                text=f"Font: {Path(path).name}. Use Check glyphs after changing text."
            )
        except Exception as exc:
            self.error(exc)

    def check_glyphs(self):
        try:
            text_font(self.text_entry.get(), self.local_font)
            name = self.local_font.name if self.local_font else "Helvetica"
            self.status.configure(
                text=f"{name}: glyphs found for the entered text. Complex-script shaping is not verified."
            )
        except Exception as exc:
            self.error(exc)

    def choose_stamp(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a local image stamp",
            filetypes=[("PNG/JPEG images", "*.png *.jpg *.jpeg")],
        )
        if not path:
            return
        try:
            source = Path(path)
            if source.stat().st_size > RESOURCE_BYTES:
                raise ValueError("Choose an image no larger than 20 MB.")
            data = source.read_bytes()
            image = stamp_image(data)
            self.stamp_data = data
            self.stamp_original_size = image.size
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            self.stamp_preview_image = image
            self.stamp_label.configure(
                text=f"{source.name} · {image.width}×{image.height} · drag to place"
            )
            self.set_mode("image")
        except Exception as exc:
            self.error(exc)

    def preflight_dialog(self):
        if not self.doc:
            return
        try:
            report = self.doc.export_preflight()
            messagebox.showinfo(
                "Export checks",
                f"{report['pages']} pages · {report['links']} links · "
                f"{report['forms']} form fields · {report['other_annotations']} other annotations\n\n"
                + "\n".join(report["warnings"]),
                parent=self,
            )
        except Exception as exc:
            self.error(exc)

    def save_session_dialog(self):
        if not self.doc:
            return False
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save unencrypted session (PDF, undo history and original filenames)",
            initialdir=self.path.parent,
            initialfile=f"{self.path.stem}.forgepdf",
            defaultextension=".forgepdf",
            filetypes=[("Forge PDF sessions", "*.forgepdf")],
            confirmoverwrite=True,
        )
        if not path:
            return False
        try:
            save_session(self.doc, Path(path), self.page, self.zoom, overwrite=Path(path).exists())
            self.status.configure(
                text="Session saved with bounded Undo history. It is unencrypted; save a PDF copy separately."
            )
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def open_session_dialog(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Open an unencrypted editing session",
            filetypes=[("Forge PDF sessions", "*.forgepdf")],
        )
        if not path:
            return
        try:
            candidate, page, zoom = open_session(Path(path))
            candidate.render(page, 0.2)
            if not self.discard_ok():
                return
            self.stop_recovery()
            self.doc, self.path, self.page, self.zoom = candidate, Path(path), page, zoom
            self.fit = False
            self.local_font = self.stamp_data = None
            self.view_target = (0, 0)
            self.refresh()
            self.status.configure(
                text="Session reopened. Original files were not loaded. Export an unencrypted PDF copy when ready."
            )
        except Exception as exc:
            self.error(exc)

    def next_match(self, direction=1):
        if not self.doc or self.search_snapshot != self.doc.data or not self.search_results:
            self.status.configure(text="Use Find to search the current document first.")
            return "break"
        self.search_position = (self.search_position + direction) % len(self.search_results)
        item = self.search_results[self.search_position]
        self.search_info.set(
            f"{self.search_position + 1} of {len(self.search_results)} · page {item['page'] + 1}\n{item['excerpt']}"
        )
        if self.search_listbox is not None and self.search_listbox.winfo_exists():
            self.search_listbox.selection_clear(0, "end")
            self.search_listbox.selection_set(self.search_position)
            self.search_listbox.see(self.search_position)
        self.show_page(item["page"])
        return "break"

    def find_dialog(self):
        if not self.doc:
            return "break"
        if self.search_window is not None and self.search_window.winfo_exists():
            self.search_window.lift()
            return "break"
        dialog = tk.Toplevel(self)
        self.search_window = dialog
        dialog.title("Find document text")
        dialog.geometry("620x420")
        dialog.transient(self)
        ttk.Label(dialog, text="Document text search · up to 1000 matches · no OCR").pack(
            padx=12, pady=8
        )
        entry = ttk.Entry(dialog)
        entry.pack(fill="x", padx=12)
        case_sensitive = tk.BooleanVar(value=False)
        whole_word = tk.BooleanVar(value=False)
        ttk.Checkbutton(dialog, text="Match case", variable=case_sensitive).pack(
            anchor="w", padx=12, pady=(6, 0)
        )
        ttk.Checkbutton(dialog, text="Whole word", variable=whole_word).pack(anchor="w", padx=12)
        ttk.Label(dialog, textvariable=self.search_info, wraplength=540).pack(
            fill="x", padx=12, pady=10
        )
        results_list = tk.Listbox(dialog, exportselection=False)
        self.search_listbox = results_list
        results_list.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def select_result(event=None):
            if results_list.curselection() and self.search_snapshot == self.doc.data:
                self.search_position = results_list.curselection()[0] - 1
                self.next_match()

        results_list.bind("<Double-Button-1>", select_result)
        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=12)

        def search():
            if self.search_future is not None and not self.search_future.done():
                self.search_info.set("The previous search is still finishing.")
                return
            snapshot = self.doc.data
            query = entry.get()
            self.search_results = []
            results_list.delete(0, "end")
            self.search_snapshot = None
            self.search_position = -1
            self.search_info.set("Searching…")
            start.configure(state="disabled")
            self.search_future = self.search_executor.submit(
                snapshot,
                {
                    "query": query,
                    "case_sensitive": case_sensitive.get(),
                    "whole_word": whole_word.get(),
                },
            )
            future = self.search_future

            def poll():
                if self.closing or not dialog.winfo_exists():
                    return
                if not future.done():
                    dialog.after(25, poll)
                    return
                start.configure(state="normal")
                try:
                    matches = future.result()
                    if not self.doc or self.doc.data != snapshot:
                        self.search_info.set("Document changed. Search again.")
                        return
                    self.search_results, self.search_snapshot = matches, snapshot
                    self.search_position = -1
                    for match in matches:
                        results_list.insert("end", f"Page {match['page'] + 1}: {match['excerpt']}")
                    if matches:
                        self.next_match()
                    else:
                        self.search_info.set(
                            "No matching text. Image-only pages need external OCR."
                        )
                except Exception as exc:
                    self.search_results = []
                    self.search_info.set(str(exc))

            dialog.after(25, poll)

        start = ttk.Button(buttons, text="Find", command=search)
        start.pack(side="left")
        ttk.Button(buttons, text="Previous", command=lambda: self.next_match(-1)).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="Next", command=self.next_match).pack(side="left")

        def close_search(event=None):
            if self.search_future is not None:
                self.search_future.cancel()
                self.search_future = None
            self.search_window = None
            self.search_listbox = None
            dialog.destroy()
            return "break"

        ttk.Button(buttons, text="Close", command=close_search).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close_search)
        entry.bind("<Return>", lambda e: search())
        dialog.bind("<Escape>", close_search)
        entry.focus_set()
        return "break"

    def point(self, event):
        return (
            (self.canvas.canvasx(event.x) - self.offset_x) / self.scale_x,
            (self.canvas.canvasy(event.y) - self.offset_y) / self.scale_y,
        )

    def press(self, event):
        if not self.doc or self.preview_pending:
            return
        self.canvas.focus_set()
        self.cancel_drag()
        if self.pending_resize:
            self.after_cancel(self.pending_resize)
            self.pending_resize = None
        x, y = self.point(event)
        w, h = self.doc.size(self.page)
        if not 0 <= x <= w or not 0 <= y <= h:
            return
        if self.mode.get() == "text":
            self.change(
                lambda: self.doc.overlay(
                    self.page,
                    "text",
                    (x, y, x, y),
                    self.text_entry.get(),
                    int(self.font_size.get()),
                    font_path=self.local_font,
                )
            )
        elif self.mode.get() == "note":
            note = simpledialog.askstring("Add text note", "Note text:", parent=self)
            if note is not None:
                self.change(lambda: self.doc.add_note(self.page, x, y, note))
        elif self.mode.get() in (
            "highlight",
            "native_highlight",
            "whiteout",
            "image",
            "raster_redact",
        ):
            if self.mode.get() == "image" and self.stamp_data is None:
                self.status.configure(text="Choose a PNG or JPEG first.")
                return
            self.drag_start = (x, y)
            self.drag_tool = self.mode.get()
            self.canvas.grab_set()

    def drag(self, event):
        if self.drag_start:
            self.canvas.delete("selection")
            x, y = self.drag_start
            end_x, end_y = self.point(event)
            page_width, page_height = self.doc.size(self.page)
            end_x = max(0, min(page_width, end_x))
            end_y = max(0, min(page_height, end_y))
            left, top = x * self.scale_x + self.offset_x, y * self.scale_y + self.offset_y
            x2 = end_x * self.scale_x + self.offset_x
            y2 = end_y * self.scale_y + self.offset_y
            if self.drag_tool == "image" and self.stamp_data and x2 != left and y2 != top:
                width, height = fit_stamp_size(
                    self.stamp_original_size, abs(x2 - left), abs(y2 - top)
                )
                preview = self.stamp_preview_image.resize(
                    (max(1, round(width)), max(1, round(height))), Image.Resampling.LANCZOS
                )
                self.stamp_thumbnail = ImageTk.PhotoImage(preview)
                self.canvas.create_image(
                    (left + x2) / 2, (top + y2) / 2, image=self.stamp_thumbnail, tags="selection"
                )
            self.canvas.create_rectangle(
                left,
                top,
                x2,
                y2,
                outline="#a97c00",
                width=2,
                tags="selection",
            )

    def release(self, event):
        if self.drag_start is None:
            return
        start, tool = self.drag_start, self.drag_tool
        end = self.point(event)
        w, h = self.doc.size(self.page)
        end = (max(0, min(w, end[0])), max(0, min(h, end[1])))
        self.cancel_drag()
        # A click or tiny accidental movement is not an edit and never opens a dialog.
        # Capture through mouse-up, and commit exactly once for a real rectangle.
        if abs(start[0] - end[0]) * self.scale_x < 2 or abs(start[1] - end[1]) * self.scale_y < 2:
            return
        if tool == "raster_redact":
            self.export_redacted((*start, *end))
        elif tool == "native_highlight":
            self.change(lambda: self.doc.add_native_highlight(self.page, (*start, *end)))
        elif tool == "image":
            x, x2 = sorted((start[0], end[0]))
            y, y2 = sorted((start[1], end[1]))
            self.change(
                lambda: self.doc.overlay(
                    self.page, "image", (x, y, x2, y2), image_path=self.stamp_data
                )
            )
        else:
            self.change(lambda: self.doc.overlay(self.page, tool, (*start, *end)))

    def destroy(self):
        if not self.closing:
            self.closing = True
            for callback in (self.preview_poll, self.pending_resize, self.recovery_after):
                if callback:
                    self.after_cancel(callback)
            self.preview_request = None
            self.preview_executor.shutdown(wait=False, cancel_futures=True)
            self.search_executor.shutdown(wait=False, cancel_futures=True)
            self.ocr_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def close(self):
        if self.discard_ok():
            self.destroy()


def main():
    app = Editor()
    if len(sys.argv) > 1:
        app.after(100, lambda: app.load(Path(sys.argv[1])))
    app.mainloop()
