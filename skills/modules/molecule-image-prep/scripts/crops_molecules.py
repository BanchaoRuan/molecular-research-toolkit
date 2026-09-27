#!/usr/bin/env python3
"""Initialize a molecule-image-prep task, crop a target, or correct an existing crop."""

from __future__ import annotations

import argparse
import io
import shutil
import sys
from dataclasses import replace
from pathlib import Path

sys.dont_write_bytecode = True

import scan_images
import validate_setup
from prepare_images_core import (
    SOURCE_LOCATION_VALUES, CropReviewRecord, TaskConfig, TaskPaths, clean_cell,
    commit_crop, ensure_unique_records, next_image_id, normalized_identifier,
    read_crop_review, read_task_config, validate_output_identifier,
    write_crop_review, write_task_config,
)


def initialize_task(args: argparse.Namespace) -> TaskPaths:
    if not validate_setup.run_validation():
        raise RuntimeError("environment check failed; no task workspace was created")
    paths = TaskPaths.for_new_task(
        task_name=args.task_name, run_date=args.run_date,
        project_root=Path(args.project_root) if args.project_root else Path.cwd())
    paths.assert_new_task_available()
    sources = scan_images.scan_inputs([Path(value) for value in args.inputs])
    config = TaskConfig(
        task_name=paths.task_name, run_date=paths.run_date,
        id_prefix=validate_output_identifier(args.id_prefix, "id_prefix"),
        id_width=args.id_width, start_id=clean_cell(args.start_id),
        has_existing_ids=args.has_existing_ids == "yes",
        reserved_ids=tuple(validate_output_identifier(value) for value in args.reserve_id),
        crop_layout_rules=clean_cell(args.crop_layout_rules),
        source_origins={row.path.name: str(row.path) for row in sources})
    config.validate()
    paths.initialize_workspace()
    for row in sources:
        shutil.copyfile(row.path, paths.source_path(row.path.name))
    write_task_config(paths, config)
    write_crop_review(paths, [])
    print(f"workspace: {paths.workspace_dir}")
    print(f"source snapshots: {paths.source_dir}")
    print(f"crop review: {paths.crop_review_path}")
    print(f"review: {paths.review_dir}")
    print(f"source images: {len(sources)}")
    print(f"reserved IDs: {', '.join(config.reserved_ids) or '(none)'}")
    return paths


def _rgb_image(path: Path):
    from PIL import Image, ImageOps

    with Image.open(path) as opened:
        if getattr(opened, "n_frames", 1) != 1:
            raise ValueError("only single-frame images can be cropped")
        image = ImageOps.exif_transpose(opened)
        image.load()
        if "A" in image.getbands() or "transparency" in image.info:
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", rgba.size, "white")
            white.alpha_composite(rgba)
            return white.convert("RGB")
        return image.convert("RGB")


def _build_crop(source_path: Path, *, box: tuple[int, int, int, int],
                padding: tuple[int, int, int, int], canvas: tuple[int, int] | None,
                paste_offset: tuple[int, int] | None):
    from PIL import Image, ImageOps

    image = _rgb_image(source_path)
    left, top, right, bottom = box
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError(f"crop box {box} must fit the oriented source ({image.width}x{image.height})")
    if any(value < 0 for value in padding):
        raise ValueError("padding must be non-negative")
    cropped = ImageOps.expand(image.crop(box), border=padding, fill="white")
    if canvas is None:
        if paste_offset is not None:
            raise ValueError("--paste-offset requires --canvas")
        return cropped
    width, height = canvas
    if width < cropped.width or height < cropped.height:
        raise ValueError("the padded crop must fit the canvas; implicit resizing is not allowed")
    x, y = paste_offset or ((width - cropped.width) // 2, (height - cropped.height) // 2)
    if x < 0 or y < 0 or x + cropped.width > width or y + cropped.height > height:
        raise ValueError("paste offset places the crop outside the canvas")
    result = Image.new("RGB", (width, height), "white")
    result.paste(cropped, (x, y))
    return result


def _source_records(paths: TaskPaths, config: TaskConfig) -> list[scan_images.SourceImage]:
    records = scan_images.scan_images(paths.source_dir)
    if {row.path.name for row in records} != set(config.source_origins):
        raise ValueError("source snapshots disagree with the initialized task")
    return records


def _check_result_files(paths: TaskPaths, records: list[CropReviewRecord],
                        *, allow_missing: str | None = None) -> None:
    expected = {f"{row.image_id}.png" for row in records}
    actual = {path.name for path in paths.single_molecule_dir.iterdir()
              if not path.name.startswith(".")}
    missing = expected - actual - ({allow_missing} if allow_missing else set())
    if missing or actual - expected:
        raise ValueError(
            f"result files disagree with crop_review.tsv: missing={sorted(missing)}, "
            f"unmapped={sorted(actual - expected)}; inspect the interrupted task before continuing")


def crop_molecule(args: argparse.Namespace) -> Path:
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    config = read_task_config(paths)
    records = read_crop_review(paths)
    sources = _source_records(paths, config)
    if args.command == "recrop":
        requested = normalized_identifier(validate_output_identifier(args.image_id))
        matches = [row for row in records if normalized_identifier(row.image_id) == requested]
        if len(matches) != 1:
            raise ValueError(f"no existing crop with image_id {args.image_id!r}")
        previous = matches[0]
        _check_result_files(paths, records, allow_missing=f"{previous.image_id}.png")
        record = replace(
            previous,
            source_location=args.source_location or previous.source_location,
            notes=previous.notes if args.notes is None else clean_cell(args.notes))
        records = [record if row.image_id == previous.image_id else row for row in records]
    else:
        _check_result_files(paths, records)
        source_matches = [row for row in sources if row.source_image_id == args.source_image_id]
        if len(source_matches) != 1:
            raise ValueError(f"source_image_id must exactly match a scanned filename stem: {args.source_image_id}")
        source = source_matches[0]
        if args.image_id:
            requested = normalized_identifier(validate_output_identifier(args.image_id))
            reserved = {normalized_identifier(value): value for value in config.reserved_ids}
            if not config.has_existing_ids or requested not in reserved:
                raise ValueError("an explicit retained ID must be reserved during initialization")
            image_id = reserved[requested]
        else:
            image_id = next_image_id(config, records)
        record = CropReviewRecord(
            image_id=image_id, source_image_id=source.source_image_id,
            source_position_id=clean_cell(args.source_position_id),
            source_location=args.source_location, source_image_path=source.path.name,
            single_molecule_path=paths.relative_single_molecule_path(image_id),
            notes=clean_cell(args.notes or ""))
        records = [*records, record]
    ensure_unique_records(records, paths)
    image = _build_crop(
        paths.source_path(record.source_image_path), box=tuple(args.box),
        padding=tuple(args.padding), canvas=tuple(args.canvas) if args.canvas else None,
        paste_offset=tuple(args.paste_offset) if args.paste_offset else None)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    from PIL import Image
    buffer.seek(0)
    with Image.open(buffer) as reopened:
        reopened.verify()
    commit_crop(paths, record, records, buffer.getvalue())
    output = paths.resolve_workspace_relative(record.single_molecule_path)
    print(f"image_id: {record.image_id}")
    print(f"output: {output}")
    print(f"output size: {image.width}x{image.height}")
    print(f"crop review: {paths.crop_review_path}")
    return output


def _geometry_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--box", required=True, type=int, nargs=4,
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="Pixels in the EXIF-oriented source; right/bottom are exclusive.")
    parser.add_argument("--padding", type=int, nargs=4, default=(0, 0, 0, 0),
                        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--canvas", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--paste-offset", type=int, nargs=2, metavar=("X", "Y"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize, crop, or correct a molecule-image-prep task.")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Validate inputs and initialize one task.")
    init.add_argument("inputs", nargs="+", help="One image folder, or supplied image files.")
    init.add_argument("--project-root", help="Working project; defaults to the current directory.")
    init.add_argument("--task-name", required=True)
    init.add_argument("--id-prefix", required=True)
    init.add_argument("--id-width", required=True, type=int)
    init.add_argument("--start-id", required=True)
    init.add_argument("--has-existing-ids", required=True, choices=("yes", "no"))
    init.add_argument("--reserve-id", action="append", default=[],
                      help="Known occupied ID; repeat for each ID to protect from new numbering.")
    init.add_argument("--crop-layout-rules", required=True)
    init.add_argument("--run-date", help="YYYYMMDD; defaults to today.")

    crop = commands.add_parser("crop", help="Add one new target and its source mapping.")
    crop.add_argument("workspace_dir")
    crop.add_argument("--source-image-id", required=True)
    crop.add_argument("--source-position-id", required=True)
    crop.add_argument("--source-location", required=True, choices=SOURCE_LOCATION_VALUES)
    crop.add_argument("--image-id", help="A previously reserved ID for this same molecule.")
    crop.add_argument("--notes", default="")
    _geometry_arguments(crop)

    recrop = commands.add_parser("recrop", help="Correct an existing crop while preserving its ID and source target.")
    recrop.add_argument("workspace_dir")
    recrop.add_argument("--image-id", required=True)
    recrop.add_argument("--source-location", choices=SOURCE_LOCATION_VALUES)
    recrop.add_argument("--notes", default=None, help="Replace notes; omission preserves existing notes.")
    _geometry_arguments(recrop)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "init":
            initialize_task(args)
        else:
            crop_molecule(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
