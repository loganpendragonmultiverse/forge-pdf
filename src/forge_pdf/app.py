"""Tk desktop shell with a single-page canvas and explicit editing modes."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import ImageTk

from . import __version__
from .document import Document

NAVY = "#16232f"
MINT = "#a9edcc"
PAPER = "#f7f8fa"
INK = "#203340"


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Forge PDF")
        self.geometry("1180x820")
        self.minsize(960, 640)
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
        style.map("TButton", background=[("active", "#e5ecef")])
        style.configure(
            "Accent.TButton", background=MINT, foreground=NAVY, font=("Segoe UI", 10, "bold")
        )
        style.configure("Tool.TRadiobutton", padding=(10, 8), background="white", foreground=INK)
        style.map("Tool.TRadiobutton", background=[("selected", "#d9f5e7")])
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.close)
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
        tk.Label(
            header, text="OFFLINE  /  FREE", bg=NAVY, fg=MINT, font=("Segoe UI", 9, "bold")
        ).pack(side="right", padx=22)

        toolbar = tk.Frame(self, bg="white", pady=10, padx=20)
        toolbar.pack(fill="x")
        for value, label in [
            ("view", "Browse"),
            ("text", "Add text"),
            ("highlight", "Highlight"),
            ("whiteout", "Whiteout"),
        ]:
            ttk.Radiobutton(
                toolbar,
                text=label,
                value=value,
                variable=self.mode,
                style="Tool.TRadiobutton",
                command=self.mode_changed,
            ).pack(side="left", padx=(0, 4))
        self.undo_button = ttk.Button(toolbar, text="Undo", command=lambda: self.history(False))
        self.undo_button.pack(side="left", padx=(20, 4))
        self.redo_button = ttk.Button(toolbar, text="Redo", command=lambda: self.history(True))
        self.redo_button.pack(side="left")
        ttk.Button(toolbar, text="Clear footer…", command=self.clear_footer).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(toolbar, text="Fit page", command=self.fit_page).pack(side="right")
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.zoom_by(1.2)).pack(side="right")
        self.zoom_label = ttk.Button(toolbar, text="100%", width=6, command=self.actual_size)
        self.zoom_label.pack(side="right")
        ttk.Button(toolbar, text="−", width=3, command=lambda: self.zoom_by(1 / 1.2)).pack(
            side="right"
        )

        body = tk.Frame(self, bg=PAPER)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg="white", width=210, padx=16, pady=18)
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
        menu.add_command(
            label="Rotate left",
            command=lambda: self.change(lambda: self.doc.rotate(self.page, -90)),
        )
        menu.add_command(label="Go to page…  Ctrl+G", command=self.go_to_page)
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
        canvasframe = tk.Frame(workspace, bg="#e5eaee")
        canvasframe.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.canvas = tk.Canvas(canvasframe, bg="#e5eaee", highlightthickness=0)
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

    def change(self, fn):
        if not self.doc:
            return
        try:
            fn()
            self.refresh()
        except Exception as exc:
            self.error(exc)

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
        self.render()
        self.canvas.yview_moveto(1 if bottom else 0)

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
        self.canvas.configure(cursor="crosshair" if self.mode.get() != "view" else "")
        self.hint.configure(
            text={
                "view": "Browse your pages. All edits stay here until you save a copy.",
                "text": "Enter your text above, then click on the page to place it. Ctrl+Z to undo.",
                "highlight": "Drag across an area to highlight it. Highlights do not remove or redact text.",
                "whiteout": "Drag to cover an area in white. Visual cover only — underlying content can still be extracted.",
            }[self.mode.get()]
        )

    def refresh(self):
        self.pages.delete(0, "end")
        if self.doc:
            self.page = min(self.page, self.doc.count - 1)
            for n in range(self.doc.count):
                self.pages.insert("end", f"  {n + 1:02d}    Page {n + 1}")
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
        if self.drag_start is not None:
            return
        old_x, old_y = self.canvas.xview()[0], self.canvas.yview()[0]
        self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not self.doc:
            self.canvas.create_text(
                cw / 2,
                ch / 2 - 45,
                text="A little less PDF friction.",
                fill=INK,
                font=("Segoe UI", 25, "bold"),
            )
            self.canvas.create_text(
                cw / 2,
                ch / 2 + 5,
                text="Open a PDF to mark it up and put its pages in order.",
                fill="#516675",
                font=("Segoe UI", 11),
            )
            self.canvas.create_text(
                cw / 2,
                ch / 2 + 42,
                text="OPEN PDF  ·  CTRL+O",
                fill="#32755c",
                font=("Segoe UI", 10, "bold"),
            )
            return
        try:
            w, h = self.doc.size(self.page)
            if self.fit:
                self.zoom = max(0.05, min((cw - 48) / w, (ch - 48) / h, 2))
            image = self.doc.render(self.page, self.zoom)
            self.scale_x, self.scale_y = image.width / w, image.height / h
            self.offset_x = max(24, (cw - image.width) / 2)
            self.offset_y = 24
            self.photo = ImageTk.PhotoImage(image)
            self.canvas.create_rectangle(
                self.offset_x + 4,
                28,
                self.offset_x + image.width + 4,
                image.height + 28,
                fill="#cbd3da",
                outline="",
            )
            self.canvas.create_image(self.offset_x, 24, image=self.photo, anchor="nw")
            self.canvas.configure(
                scrollregion=(0, 0, max(cw, image.width + 48), max(ch, image.height + 48))
            )
            self.canvas.xview_moveto(old_x)
            self.canvas.yview_moveto(old_y)
            self.zoom_label.configure(text=f"{self.scale_x:.0%}")
        except Exception as exc:
            self.error(exc)

    def point(self, event):
        return (
            (self.canvas.canvasx(event.x) - self.offset_x) / self.scale_x,
            (self.canvas.canvasy(event.y) - self.offset_y) / self.scale_y,
        )

    def press(self, event):
        if not self.doc:
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
                )
            )
        elif self.mode.get() in ("highlight", "whiteout"):
            self.drag_start = (x, y)
            self.drag_tool = self.mode.get()
            self.canvas.grab_set()

    def drag(self, event):
        if self.drag_start:
            self.canvas.delete("selection")
            x, y = self.drag_start
            self.canvas.create_rectangle(
                x * self.scale_x + self.offset_x,
                y * self.scale_y + self.offset_y,
                self.canvas.canvasx(event.x),
                self.canvas.canvasy(event.y),
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
        self.change(lambda: self.doc.overlay(self.page, tool, (*start, *end)))

    def close(self):
        if self.discard_ok():
            self.destroy()


def main():
    app = Editor()
    if len(sys.argv) > 1:
        app.after(100, lambda: app.load(Path(sys.argv[1])))
    app.mainloop()
