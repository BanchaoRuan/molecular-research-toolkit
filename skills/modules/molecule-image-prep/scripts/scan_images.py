#!/usr/bin/env python3
"""Inspect source images without changing files or creating task directories."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True

from prepare_images_core import (
    SUPPORTED_IMAGE_EXTENSIONS, natural_sort_key, normalized_identifier, portable_source_name,
)


@dataclass(frozen=True)
class SourceImage:
    source_image_id: str
    path: Path
    width: int
    height: int
    mode: str


def _inspect_image(path: Path) -> SourceImage:
    from PIL import Image, ImageOps

    portable_source_name(path.name)
    image_id = path.stem.strip()
    if not image_id:
        raise ValueError(f"source filename has an empty stem: {path}")
    with Image.open(path) as opened:
        if getattr(opened, "n_frames", 1) != 1:
            raise ValueError(f"only single-frame source images are supported: {path.name}")
        oriented = ImageOps.exif_transpose(opened)
        oriented.load()
        width, height = oriented.size
        mode = oriented.mode
    return SourceImage(image_id, path, width, height, mode)


def scan_inputs(inputs: list[Path]) -> list[SourceImage]:
    paths = [path.expanduser().absolute() for path in inputs]
    if len(paths) == 1 and paths[0].is_dir():
        directory = paths[0]
        paths = sorted(
            (path for path in directory.iterdir()
             if not path.name.startswith(".") and path.name not in ("Thumbs.db", "Desktop.ini")),
            key=lambda path: natural_sort_key(path.name),
        )
    if not paths:
        raise ValueError("no source images were supplied")
    invalid = [str(path) for path in paths
               if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS]
    if invalid:
        raise ValueError(
            "supply supported image files, or one flat image folder; unsupported entries: "
            + ", ".join(invalid))
    records = []
    seen = set()
    for path in paths:
        try:
            record = _inspect_image(path)
        except Exception as exc:
            raise ValueError(f"cannot use source image {path}: {exc}") from exc
        key = normalized_identifier(record.source_image_id)
        if key in seen:
            raise ValueError(
                f"duplicate source_image_id after Unicode/case normalization: {record.source_image_id}")
        seen.add(key)
        records.append(record)
    return sorted(records, key=lambda row: natural_sort_key(row.source_image_id))


def scan_images(input_dir: Path) -> list[SourceImage]:
    return scan_inputs([input_dir])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect an image folder or supplied image files.")
    parser.add_argument("inputs", nargs="+", help="One image folder, or one or more image files.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        records = scan_inputs([Path(value) for value in args.inputs])
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"source images: {len(records)}")
    for row in records:
        print(f"{row.source_image_id}\t{row.width}x{row.height}\t{row.mode}\t{row.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
