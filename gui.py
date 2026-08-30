#!/usr/bin/env python3
"""Tkinter front end for Smart File Organizer. Organizing logic stays in organizer.py."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import organizer

APP_TITLE = "Smart File Organizer"


class OrganizerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(820, 560)
        self.root.geometry("960x640")

        self.path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Select a source folder, then Preview / Dry Run.")
        self.summary_var = tk.StringVar(value="No preview yet.")
        self._preview_plan: list[tuple[Path, Path, str]] = []
        self._preview_source: Path | None = None

        self._build()
        self.path_var.trace_add("write", self._on_path_changed)

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 8}
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)

        path_row = ttk.Frame(main)
        path_row.pack(fill=tk.X, **pad)
        ttk.Label(path_row, text="Source folder:").pack(side=tk.LEFT)
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Button(path_row, text="Browse…", command=self.on_browse).pack(side=tk.LEFT)

        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        ttk.Button(btn_row, text="Preview / Dry Run", command=self.on_preview).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.organize_btn = ttk.Button(
            btn_row, text="Organize Files", command=self.on_organize, state=tk.DISABLED
        )
        self.organize_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Clear / Reset", command=self.on_clear).pack(side=tk.LEFT)

        ttk.Label(main, text="Planned moves").pack(anchor=tk.W, padx=12)
        table_frame = ttk.Frame(main)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        columns = ("original", "destination", "category")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        self.tree.heading("original", text="Original")
        self.tree.heading("destination", text="Destination")
        self.tree.heading("category", text="Category")
        self.tree.column("original", width=320, stretch=True)
        self.tree.column("destination", width=360, stretch=True)
        self.tree.column("category", width=100, stretch=False, anchor=tk.CENTER)

        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        ttk.Label(main, text="Summary").pack(anchor=tk.W, padx=12)
        ttk.Label(main, textvariable=self.summary_var, wraplength=900, justify=tk.LEFT).pack(
            anchor=tk.W, padx=12, pady=(0, 8)
        )

        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=12, pady=(0, 8))

        status = ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=6)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _on_path_changed(self, *_args: object) -> None:
        if self._preview_plan or self._preview_source is not None:
            self._clear_table()
            self.summary_var.set("Folder changed. Run Preview / Dry Run again.")
        self._invalidate_preview()

    def _invalidate_preview(self) -> None:
        self._preview_plan = []
        self._preview_source = None
        self.organize_btn.configure(state=tk.DISABLED)

    def _clear_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _validated_source(self) -> Path | None:
        raw = self.path_var.get().strip().strip('"')
        if not raw:
            messagebox.showwarning(APP_TITLE, "Please choose a source folder first.")
            return None
        try:
            source = Path(raw).expanduser().resolve()
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Invalid path:\n{exc}")
            return None
        if not source.exists() or not source.is_dir():
            messagebox.showerror(APP_TITLE, f"Not a valid folder:\n{source}")
            return None
        return source

    def on_browse(self) -> None:
        chosen = filedialog.askdirectory(title="Select source folder")
        if chosen:
            self.path_var.set(chosen)

    def on_preview(self) -> None:
        source = self._validated_source()
        if source is None:
            return
        try:
            self.progress.start(12)
            self.root.update_idletasks()
            plan = organizer.plan_moves(source)
        except PermissionError as exc:
            self.progress.stop()
            messagebox.showerror(APP_TITLE, f"Cannot read folder:\n{exc}")
            self.status_var.set("Preview failed.")
            return
        except Exception as exc:  # noqa: BLE001
            self.progress.stop()
            messagebox.showerror(APP_TITLE, f"Preview failed:\n{type(exc).__name__}: {exc}")
            self.status_var.set("Preview failed.")
            return
        finally:
            self.progress.stop()

        self._show_plan(source, plan)
        self._preview_plan = plan
        self._preview_source = source
        if plan:
            self.organize_btn.configure(state=tk.NORMAL)
            self.status_var.set(f"Dry run complete. {len(plan)} file(s) planned. Nothing was moved.")
        else:
            self.organize_btn.configure(state=tk.DISABLED)
            self.status_var.set("No files to organize in this folder.")

    def _show_plan(self, source: Path, plan: list[tuple[Path, Path, str]]) -> None:
        self._clear_table()
        counts: dict[str, int] = {}
        renamed = 0
        for src, dest, category in plan:
            if dest.name != src.name:
                renamed += 1
            counts[category] = counts.get(category, 0) + 1
            self.tree.insert(
                "",
                tk.END,
                values=(str(src), str(dest), category),
            )
        if not plan:
            self.summary_var.set("No files to organize.")
            return
        parts = [f"Total: {len(plan)}"]
        for name in sorted(counts):
            parts.append(f"{name}: {counts[name]}")
        if renamed:
            parts.append(f"Unique names: {renamed}")
        self.summary_var.set("  |  ".join(parts))

    def on_organize(self) -> None:
        source = self._validated_source()
        if source is None:
            return
        if self._preview_source is None or not self._preview_plan:
            messagebox.showwarning(
                APP_TITLE,
                "Run Preview / Dry Run first so you can review planned moves.",
            )
            return
        if source != self._preview_source:
            messagebox.showwarning(
                APP_TITLE,
                "The folder changed since the last preview. Run Preview / Dry Run again.",
            )
            return

        count = len(self._preview_plan)
        if not messagebox.askyesno(
            APP_TITLE,
            f"Move {count} file(s) in:\n{source}\n\n"
            "This cannot be undone from the app. Continue?",
            icon="warning",
        ):
            self.status_var.set("Organization cancelled. No files were moved.")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = source / f"organize_log_{stamp}.csv"
        try:
            self.progress.start(12)
            self.root.update_idletasks()
            rows = organizer.execute_moves(self._preview_plan, log_path)
        except Exception as exc:  # noqa: BLE001
            self.progress.stop()
            messagebox.showerror(APP_TITLE, f"Organization failed:\n{type(exc).__name__}: {exc}")
            self.status_var.set("Organization failed.")
            return
        finally:
            self.progress.stop()

        moved = sum(1 for row in rows if row["status"] == "moved")
        failed = sum(1 for row in rows if row["status"] == "error")
        self.summary_var.set(f"Moved: {moved}  |  Failed: {failed}  |  Log: {log_path}")
        self.status_var.set(f"Done. Moved {moved}, failed {failed}. Log: {log_path}")
        self._clear_table()
        self._invalidate_preview()
        messagebox.showinfo(
            APP_TITLE,
            f"Moved: {moved}\nFailed: {failed}\n\nCSV log:\n{log_path}",
        )

    def on_clear(self) -> None:
        self.path_var.set("")
        self._clear_table()
        self._invalidate_preview()
        self.summary_var.set("No preview yet.")
        self.status_var.set("Select a source folder, then Preview / Dry Run.")
        self.progress.stop()


def main() -> None:
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except tk.TclError:
        pass
    OrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
