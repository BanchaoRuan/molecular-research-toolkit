#!/usr/bin/env python3
"""Build a checked molecule-image-prep review bundle in the parent project's review directory."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path

sys.dont_write_bytecode = True

import validate_setup
from prepare_images_core import (
    CROP_REVIEW_FIELDS, CropReviewRecord, TaskPaths, archive_review,
    assert_outside_skill_dir, assert_within, configure_runtime,
    read_crop_review, read_task_config,
)


def validate_review_inputs(paths: TaskPaths, records: list[CropReviewRecord]) -> list[Path]:
    from PIL import Image

    config = read_task_config(paths)
    if not records:
        raise ValueError("crop_review.tsv has no targets")
    expected = {f"{row.image_id}.png" for row in records}
    actual = {path.name for path in paths.single_molecule_dir.iterdir()
              if not path.name.startswith(".")}
    if actual != expected:
        raise ValueError(
            f"result files disagree with crop_review.tsv: missing={sorted(expected - actual)}, "
            f"unmapped={sorted(actual - expected)}")
    outputs = []
    for row in records:
        if (row.source_image_path not in config.source_origins
                or not paths.source_path(row.source_image_path).is_file()):
            raise ValueError(f"source snapshot is missing or unrecognized: {row.image_id}")
        output = paths.resolve_workspace_relative(row.single_molecule_path)
        with Image.open(output) as image:
            if image.format != "PNG":
                raise ValueError(f"result is not a PNG image: {row.image_id}")
            image.verify()
        outputs.append(output)
    return outputs


def _fit_report_cells(sheet) -> None:
    """Size the plain report at export without requiring an Excel installation."""
    from openpyxl.styles import Alignment
    from PIL import ImageFont

    # Bundled font metrics avoid machine-specific font paths. A small margin
    # accounts for differences from the workbook's default 11 pt Excel font.
    font = ImageFont.load_default(size=15)
    digit_width = font.getlength("0")

    @lru_cache(maxsize=4096)
    def char_width(char):
        if unicodedata.combining(char):
            return 0
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            return 2
        return font.getlength(char) / digit_width * 1.08

    def text_width(text):
        return sum(char_width(char) for char in text)

    def display_lines(value):
        text = "" if value is None else str(value)
        return text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4).split("\n")

    def wrapped_lines(line, available):
        count, used = 1, 0
        for token in re.findall(r"\S+|\s+", line):
            if token.isspace():
                used += text_width(token)
                continue
            if used and used + text_width(token) > available:
                count, used = count + 1, 0
            for char in token:
                width = char_width(char)
                if used and used + width > available:
                    count, used = count + 1, 0
                used += width
        return count

    for column in sheet.columns:
        longest = max(text_width(line) for cell in column for line in display_lines(cell.value))
        sheet.column_dimensions[column[0].column_letter].width = min(60, max(10, math.ceil(longest) + 2))

    alignment = Alignment(vertical="top", wrap_text=True)
    for row in sheet:
        line_count = 1
        for cell in row:
            cell.alignment = alignment
            available = sheet.column_dimensions[cell.column_letter].width - 2
            lines = sum(wrapped_lines(line, available) for line in display_lines(cell.value))
            line_count = max(line_count, lines)
        # Excel limits a row to 409.5 points; cell values are never shortened.
        sheet.row_dimensions[row[0].row].height = min(409.5, 15 * line_count + 3)


def write_xlsx(records: list[CropReviewRecord], output_path: Path) -> None:
    from openpyxl import Workbook, load_workbook

    expected = [list(CROP_REVIEW_FIELDS)] + [
        [row.as_dict()[field] for field in CROP_REVIEW_FIELDS] for row in records]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "crop_review"
    for values in expected:
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
    _fit_report_cells(sheet)
    workbook.save(output_path)
    workbook.close()
    reopened = load_workbook(output_path, read_only=True, data_only=False)
    try:
        actual = [[value if value is not None else "" for value in row]
                  for row in reopened["crop_review"].iter_rows(values_only=True)]
        if reopened.sheetnames != ["crop_review"] or actual != expected:
            raise RuntimeError("XLSX values do not match crop_review.tsv")
    finally:
        reopened.close()


def write_overview(image_paths: list[Path], labels: list[str], output_path: Path,
                   *, columns: int) -> None:
    from PIL import Image, ImageDraw, ImageFont

    if not image_paths or len(image_paths) != len(labels) or columns < 1:
        raise ValueError("overview requires matching images/labels and a positive column count")
    font = ImageFont.load_default(size=16)
    cell_width = max(360, max(font.getbbox(label)[2] for label in labels) + 24)
    cell_height = 290
    columns = min(columns, len(image_paths))
    rows = (len(image_paths) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (path, label) in enumerate(zip(image_paths, labels)):
        with Image.open(path) as opened:
            preview = opened.convert("RGB")
            preview.thumbnail((cell_width - 24, cell_height - 56))
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        draw.text((x + 12, y + 10), label, font=font, fill="black")
        canvas.paste(preview, (x + (cell_width - preview.width) // 2,
                               y + 40 + (cell_height - 52 - preview.height) // 2))
    canvas.save(output_path, format="PNG")


def build_review(paths: TaskPaths, *, overview_columns: int = 5,
                 replace_existing: bool = False) -> Path:
    if overview_columns < 1:
        raise ValueError("overview_columns must be positive")
    records = read_crop_review(paths)
    images = validate_review_inputs(paths, records)
    if paths.review_dir.exists() and not replace_existing:
        raise FileExistsError("review already exists; use --replace only for an intended rebuild")
    temporary = configure_runtime(paths)
    staging = Path(tempfile.mkdtemp(prefix="review-", dir=temporary))
    copies = []
    for row, source in zip(records, images):
        target = paths.assert_workspace_path(staging / row.single_molecule_path)
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        copies.append(target)
    write_xlsx(records, staging / f"{paths.task_name}_images_report.xlsx")
    write_overview(copies, [row.image_id for row in records],
                   staging / "single_molecule_overview.png", columns=overview_columns)

    parent = assert_outside_skill_dir(
        assert_within(paths.review_dir.parent, paths.project_root, "working project"), "review root")
    parent.mkdir(parents=True, exist_ok=True)
    archived = archive_review(paths)
    try:
        staging.rename(paths.review_dir)
    except BaseException:
        if archived is not None:
            archived.rename(paths.review_dir)
        raise
    if archived is not None:
        print(f"previous review retained in workspace: {archived}")
    print(f"review: {paths.review_dir}")
    print(f"report: {paths.review_dir / (paths.task_name + '_images_report.xlsx')}")
    print(f"overview: {paths.review_dir / 'single_molecule_overview.png'}")
    print(f"single-molecule images: {len(records)}")
    return paths.review_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the molecule-image-prep review package.")
    parser.add_argument("workspace_dir")
    parser.add_argument("--overview-columns", type=int, default=5)
    parser.add_argument("--replace", action="store_true",
                        help="Rebuild intentionally; retain the previous package in workspace history.")
    args = parser.parse_args(argv)
    try:
        if not validate_setup.run_validation():
            raise RuntimeError("environment check failed")
        build_review(TaskPaths.from_workspace(Path(args.workspace_dir)),
                     overview_columns=args.overview_columns, replace_existing=args.replace)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
