"""The window end users see: choose the two Esunny exports, press Generate."""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.config import load_config
from src.pipeline import RunResult, run

APP_TITLE = "Closeout Instruction Generator"
CSV_FILES = [("CSV files", "*.csv"), ("All files", "*.*")]
FILLED_TITLE = "Step 1 of 2: select the FILLED file"
CLOSEOUT_TITLE = "Step 2 of 2: select the CLOSE OUT file"


def default_output_path(closeout_path: Path, now: datetime | None = None) -> Path:
    # A fresh name every run: an earlier result is never overwritten, and the write can never
    # hit a workbook the user still has open in Excel (which Windows locks).
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return closeout_path.parent / f"closeout_output_{stamp}.xlsx"


def summarise(result: RunResult) -> str:
    lines = [
        f"Phillip Nova instructions: {result.pn_rows}",
        f"OCBC instructions: {result.ocbc_rows}",
        f"Exceptions: {result.exceptions}",
    ]
    if result.exceptions:
        lines.append("Review the 'exceptions' sheet before sending anything.")
    lines += ["", f"Saved as {result.output_path.name}", f"in {result.output_path.parent}"]
    return "\n".join(lines)


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open", str(path)], check=False)


class App:
    def __init__(self, root: tk.Tk, config: dict) -> None:
        self.root = root
        self.config = config
        self.filled = tk.StringVar()
        self.closeout = tk.StringVar()
        self.status = tk.StringVar(value="Choose the two files exported from Esunny.")

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        self._file_row(frame, 0, "1. Filled file", self.filled, FILLED_TITLE)
        self._file_row(frame, 1, "2. Close out file", self.closeout, CLOSEOUT_TITLE)
        ttk.Button(frame, text="Generate instructions", command=self.generate).grid(
            row=2, column=1, columnspan=2, sticky="e", pady=(12, 0)
        )
        ttk.Label(frame, textvariable=self.status).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(frame, text=f"Rules version {config['rules_version']}", foreground="gray").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

    def _file_row(self, frame: ttk.Frame, row: int, label: str, target: tk.StringVar, title: str) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=target, width=60, state="readonly").grid(row=row, column=1, padx=8, pady=4)
        ttk.Button(frame, text="Browse...", command=lambda: self.browse(target, title)).grid(row=row, column=2, pady=4)

    def ask_file(self, title: str, initialdir: str | None = None) -> str:
        options = {}
        if sys.platform == "darwin":
            options["message"] = title  # macOS file dialogs hide the title; Windows Tk rejects this option
        return filedialog.askopenfilename(
            parent=self.root, title=title, filetypes=CSV_FILES, initialdir=initialdir, **options
        )

    def browse(self, target: tk.StringVar, title: str) -> None:
        already_chosen = self.filled.get() or self.closeout.get()
        chosen = self.ask_file(title, str(Path(already_chosen).parent) if already_chosen else None)
        if chosen:
            target.set(chosen)

    def prompt_for_files(self) -> None:
        filled = self.ask_file(FILLED_TITLE)
        if not filled:
            self.status.set("No file chosen. Use Browse... for both files, then Generate instructions.")
            return
        self.filled.set(filled)
        closeout = self.ask_file(CLOSEOUT_TITLE, str(Path(filled).parent))
        if not closeout:
            self.status.set("No close out file chosen. Use Browse... for it, then Generate instructions.")
            return
        self.closeout.set(closeout)
        self.generate()

    def generate(self) -> None:
        if not self.filled.get() or not self.closeout.get():
            messagebox.showwarning(APP_TITLE, "Choose both files first.")
            return

        output_path = default_output_path(Path(self.closeout.get()))
        self.status.set("Working...")
        self.root.update()

        try:
            result = run(self.filled.get(), self.closeout.get(), output_path, self.config)
        except Exception as exc:
            self.status.set("No output was created.")
            hint = ""
            if isinstance(exc, ValueError):
                hint = "\n\nCheck that file 1 is the filled export and file 2 is the close out export."
            messagebox.showerror(APP_TITLE, f"No output was created.\n\n{exc}{hint}")
            return

        self.status.set(f"Saved {result.output_path.name}")
        if messagebox.askyesno(APP_TITLE, summarise(result) + "\n\nOpen it now?"):
            open_file(result.output_path)


def launch(config_path: str | Path | None = None) -> None:
    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)

    try:
        config = load_config(config_path)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror(APP_TITLE, f"The rules could not be loaded. Please contact IT.\n\n{exc}")
        return

    app = App(root, config)
    # Tk started from a terminal often opens behind it on macOS.
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.after(300, app.prompt_for_files)
    root.mainloop()
