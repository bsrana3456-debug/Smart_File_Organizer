#!/usr/bin/env python3
"""Smart File Organizer: sort files in a folder by extension (stdlib only)."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Extension (lowercase) -> destination folder name.
CATEGORIES: dict[str, str] = {
    ".pdf": "PDF",
    ".xls": "Excel",
    ".xlsx": "Excel",
    ".csv": "Excel",
    ".doc": "Word",
    ".docx": "Word",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".png": "Images",
    ".gif": "Images",
    ".bmp": "Images",
    ".webp": "Images",
    ".mp4": "Videos",
    ".avi": "Videos",
    ".mkv": "Videos",
    ".mov": "Videos",
    ".txt": "Text",
    ".zip": "Archives",
    ".rar": "Archives",
    ".7z": "Archives",
}

OTHERS = "Others"
LOG_COLUMNS = ["original_path", "destination_path", "status", "error"]


def category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return CATEGORIES.get(suffix, OTHERS)


def _path_key(path: Path) -> str:
    resolved = str(path.resolve())
    return resolved.lower() if os.name == "nt" else resolved


def unique_destination(dest_dir: Path, filename: str, claimed: set[str]) -> Path:
    """Return dest_dir/filename, or filename_1, filename_2, ... if taken.

    Never overwrites an existing file. If the path exists as a directory,
    the next numeric suffix is used. ``claimed`` holds keys from this run.
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    n = 0
    while True:
        name = filename if n == 0 else f"{stem}_{n}{suffix}"
        candidate = dest_dir / name
        key = _path_key(candidate)
        taken_on_disk = candidate.exists()
        if not taken_on_disk and key not in claimed:
            return candidate
        n += 1


def _is_own_log(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("organize_log_") and name.endswith(".csv")


def scan_files(source: Path) -> list[Path]:
    """Files sitting directly in source. Directories and prior logs are ignored."""
    files: list[Path] = []
    for entry in sorted(source.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file() and not _is_own_log(entry):
            files.append(entry)
    return files


def plan_moves(source: Path) -> list[tuple[Path, Path, str]]:
    claimed: set[str] = set()
    plan: list[tuple[Path, Path, str]] = []
    for src in scan_files(source):
        category = category_for(src)
        dest_dir = source / category
        dest = unique_destination(dest_dir, src.name, claimed)
        claimed.add(_path_key(dest))
        plan.append((src, dest, category))
    return plan


def print_preview(plan: list[tuple[Path, Path, str]]) -> None:
    if not plan:
        print("No files to organize.")
        return

    counts: dict[str, int] = {}
    renamed = 0
    print("DRY RUN - no files will be moved.\n")
    print(f"{'Original':<50}  {'Destination':<50}  Category")
    print("-" * 120)
    for src, dest, category in plan:
        if dest.name != src.name:
            renamed += 1
        print(f"{str(src):<50}  {str(dest):<50}  {category}")
        counts[category] = counts.get(category, 0) + 1

    print()
    print(f"Total files: {len(plan)}")
    for name in sorted(counts):
        print(f"  {name}: {counts[name]}")
    if renamed:
        print(f"Unique names (collision avoided): {renamed}")


def _write_log(log_path: Path, rows: list[dict[str, str]]) -> None:
    with log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def execute_moves(
    plan: list[tuple[Path, Path, str]],
    log_path: Path,
) -> list[dict[str, str]]:
    claimed: set[str] = set()
    rows: list[dict[str, str]] = []

    for src, planned_dest, _category in plan:
        dest: Path | None = None
        try:
            dest_dir = planned_dest.parent
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = unique_destination(dest_dir, planned_dest.name, claimed)
            if dest.exists():
                raise FileExistsError(f"Refusing to overwrite: {dest}")
            claimed.add(_path_key(dest))
            shutil.move(str(src), str(dest))
            rows.append(
                {
                    "original_path": str(src),
                    "destination_path": str(dest),
                    "status": "moved",
                    "error": "",
                }
            )
        except (PermissionError, OSError, FileNotFoundError) as exc:
            rows.append(
                {
                    "original_path": str(src),
                    "destination_path": str(dest) if dest is not None else str(planned_dest),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        except Exception as exc:  # noqa: BLE001 — do not abort the batch
            rows.append(
                {
                    "original_path": str(src),
                    "destination_path": str(dest) if dest is not None else str(planned_dest),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    try:
        _write_log(log_path, rows)
    except OSError as exc:
        print(f"Could not write log {log_path}: {exc}", file=sys.stderr)
    return rows


def prompt_source() -> Path:
    raw = input("Source folder path: ").strip().strip('"')
    return Path(raw)


def confirm() -> bool:
    answer = input("Proceed with moving files? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize files in a folder into subfolders by type."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Folder that contains the files to organize",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = Path(args.source) if args.source else prompt_source()

    try:
        source = source.expanduser().resolve()
    except OSError as exc:
        print(f"Invalid path: {exc}", file=sys.stderr)
        return 1

    if not source.exists():
        print(f"Path does not exist: {source}", file=sys.stderr)
        return 1
    if not source.is_dir():
        print(f"Not a directory: {source}", file=sys.stderr)
        return 1

    try:
        plan = plan_moves(source)
    except PermissionError as exc:
        print(f"Cannot read folder: {exc}", file=sys.stderr)
        return 1

    print_preview(plan)
    if not plan:
        return 0

    if not confirm():
        print("Cancelled. No files were moved.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = source / f"organize_log_{stamp}.csv"
    rows = execute_moves(plan, log_path)

    moved = sum(1 for row in rows if row["status"] == "moved")
    failed = sum(1 for row in rows if row["status"] == "error")
    print()
    print(f"Moved: {moved}")
    print(f"Failed: {failed}")
    print(f"Log: {log_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
