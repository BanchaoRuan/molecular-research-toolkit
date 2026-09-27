#!/usr/bin/env python3
"""Render candidate SMILES, build comparison images, and record source review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True

from smiles_core import (
    CandidateRecord,
    TaskPaths,
    add_note,
    append_event,
    canonicalize_smiles,
    configure_runtime,
    get_candidate,
    read_candidates,
    safe_component,
    update_candidate,
    write_candidates,
)


def _images() -> tuple[Any, Any, Any]:
    from PIL import Image, ImageDraw, ImageOps

    return Image, ImageDraw, ImageOps


def make_placeholder(output_path: Path, title: str, message: str) -> Path:
    Image, ImageDraw, _ImageOps = _images()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (620, 500), "white")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((16, 16, 604, 484), outline=(180, 180, 180), width=2)
    draw.text((32, 32), title, fill=(0, 0, 0))
    draw.text((32, 74), message[:240], fill=(150, 0, 0))
    canvas.save(output_path)
    return output_path


def render_smiles(smiles: str, output_path: Path, title: str) -> Path:
    from rdkit.Chem import Draw

    Image, ImageDraw, _ImageOps = _images()
    validation = canonicalize_smiles(smiles, allow_fragments=True)
    if not validation.rdkit_valid or validation.mol is None:
        return make_placeholder(output_path, title, validation.reason or "invalid candidate")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    molecule_image = Draw.MolToImage(validation.mol, size=(620, 420))
    canvas = Image.new("RGB", (620, 500), "white")
    canvas.paste(molecule_image, (0, 48))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 14), title, fill=(0, 0, 0))
    canvas.save(output_path)
    return output_path


def make_comparison(
    source_path: Path,
    rendered_path: Path,
    output_path: Path,
    *,
    title: str,
    note: str,
) -> Path:
    Image, ImageDraw, ImageOps = _images()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    left = ImageOps.exif_transpose(Image.open(source_path)).convert("RGB")
    right = Image.open(rendered_path).convert("RGB")
    left.thumbnail((620, 500))
    right.thumbnail((620, 500))

    header_height = 92
    canvas = Image.new("RGB", (1280, header_height + max(left.height, right.height, 500) + 30), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 16), title, fill=(0, 0, 0))
    draw.text((20, 46), note[:200], fill=(70, 70, 70))
    draw.text((20, header_height), "Source image", fill=(0, 0, 0))
    draw.text((660, header_height), "Reverse structure", fill=(0, 0, 0))
    canvas.paste(left, (20, header_height + 26))
    canvas.paste(right, (660, header_height + 26))
    canvas.save(output_path)
    return output_path


def write_overview(
    image_paths: Iterable[Path],
    output_path: Path,
    *,
    labels: Iterable[str] | None = None,
    columns: int = 5,
) -> Path:
    Image, ImageDraw, ImageOps = _images()
    paths = list(image_paths)
    names = list(labels or [path.stem for path in paths])
    if len(paths) != len(names):
        raise ValueError("overview paths and labels must have the same length")
    if not paths:
        return make_placeholder(output_path, "overview", "no images")

    cell_width, cell_height = 360, 290
    columns = max(1, min(columns, len(paths)))
    row_count = (len(paths) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, row_count * cell_height), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (path, label) in enumerate(zip(paths, names)):
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        image.thumbnail((cell_width - 20, cell_height - 50))
        origin_x = (index % columns) * cell_width
        origin_y = (index // columns) * cell_height
        x = origin_x + (cell_width - image.width) // 2
        y = origin_y + 34 + (cell_height - 44 - image.height) // 2
        draw.text((origin_x + 10, origin_y + 8), str(label)[:48], fill=(0, 0, 0))
        canvas.paste(image, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def render_record(paths: TaskPaths, record: CandidateRecord) -> CandidateRecord:
    source_path = Path(record.source_image_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"source image not found for {record.image_id}: {source_path}")

    file_id = safe_component(record.image_id)
    reverse_path = paths.assert_workspace_path(paths.reverse_dir / f"{file_id}.png")
    comparison_path = paths.assert_workspace_path(paths.comparisons_dir / f"{file_id}.png")
    title = record.image_id
    if record.smiles:
        render_smiles(record.smiles, reverse_path, title)
    else:
        make_placeholder(reverse_path, title, record.notes or "no accepted candidate")
    make_comparison(
        source_path,
        reverse_path,
        comparison_path,
        title=title,
        note=f"{record.recognition_method}: {record.notes}",
    )
    record.reverse_structure_path = str(reverse_path)
    return record


def apply_source_review(
    paths: TaskPaths,
    image_id: str,
    *,
    source_match: str,
    confidence: str,
    notes: str = "",
) -> CandidateRecord:
    record = get_candidate(paths, image_id)
    record.source_match = source_match
    record.confidence = confidence
    if source_match == "yes":
        if not record.smiles or record.rdkit_valid != "true" or not record.reverse_structure_path:
            raise ValueError(
                "cannot mark success before SMILES validation and reverse rendering are complete"
            )
        if not Path(record.reverse_structure_path).expanduser().resolve().is_file():
            raise ValueError(f"cannot mark success: reverse structure is missing for {image_id}")
        record.status = "success"
    else:
        record.status = "failure"
        if confidence != "low":
            record.confidence = "low"
    add_note(record, notes or f"Source comparison: {source_match}")
    update_candidate(paths, record)
    append_event(
        paths,
        stage="source_review",
        status=record.status,
        image_id=record.image_id,
        message=f"source_match={source_match}; confidence={record.confidence}",
    )
    if record.status == "failure":
        from chemdraw_fallback import prepare_seed

        prepare_seed(paths, record.image_id)
        record = get_candidate(paths, record.image_id)
    return record


def _select_records(records: list[CandidateRecord], image_id: str | None) -> list[CandidateRecord]:
    if image_id is None:
        return records
    selected = [record for record in records if record.image_id == image_id]
    if len(selected) != 1:
        raise KeyError(f"candidate not found: {image_id}")
    return selected


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or review smiles_auto candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Render reverse structures and comparisons.")
    render_parser.add_argument("workspace_dir")
    render_parser.add_argument("--image-id", default=None)

    review_parser = subparsers.add_parser("review", help="Record source-image comparison.")
    review_parser.add_argument("workspace_dir")
    review_parser.add_argument("image_id")
    review_parser.add_argument("--source-match", choices=["yes", "no"], required=True)
    review_parser.add_argument("--confidence", choices=["high", "medium", "low"], required=True)
    review_parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    configure_runtime(paths)
    if args.command == "review":
        record = apply_source_review(
            paths,
            args.image_id,
            source_match=args.source_match,
            confidence=args.confidence,
            notes=args.notes,
        )
        print(f"reviewed {record.image_id}: {record.status}")
        return 0

    records = read_candidates(paths)
    selected = _select_records(records, args.image_id)
    selected_ids = {record.image_id for record in selected}
    updated_by_id = {record.image_id: render_record(paths, record) for record in selected}
    merged = [updated_by_id.get(record.image_id, record) for record in records]
    write_candidates(paths, merged)
    for image_id in selected_ids:
        append_event(
            paths,
            stage="render",
            status="complete",
            image_id=image_id,
            message="reverse structure and comparison written",
        )
    print(f"rendered {len(selected)} candidate(s) in {paths.workspace_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
