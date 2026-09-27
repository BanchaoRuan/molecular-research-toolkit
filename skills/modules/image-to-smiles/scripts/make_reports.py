#!/usr/bin/env python3
"""Build the review bundle from the canonical candidate table."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from pathlib import Path


sys.dont_write_bytecode = True

import chemdraw_fallback
from render_smiles import make_placeholder, write_overview
from smiles_core import (
    FINAL_REPORT_FIELDS,
    CandidateRecord,
    TaskPaths,
    candidate_fields,
    configure_runtime,
    natural_sort_key,
    read_candidates,
    read_events,
    safe_component,
)


def _markdown(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def write_xlsx(records: list[CandidateRecord], output_path: Path) -> Path:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "SMILES review"
    sheet.append(FINAL_REPORT_FIELDS)
    for record in records:
        row = record.as_dict()
        sheet.append([row[field] for field in FINAL_REPORT_FIELDS])

    workbook.save(output_path)
    return output_path


def write_readable(records: list[CandidateRecord], output_path: Path, task_name: str) -> Path:
    lines = [
        f"# {task_name} SMILES review",
        "",
        "| " + " | ".join(FINAL_REPORT_FIELDS) + " |",
        "|" + "|".join("---" for _ in FINAL_REPORT_FIELDS) + "|",
    ]
    for record in records:
        row = record.as_dict()
        lines.append(
            "| " + " | ".join(_markdown(row[field]) for field in FINAL_REPORT_FIELDS) + " |"
        )
    lines.extend(["", "## Evidence details", ""])
    detail_fields = candidate_fields()[len(FINAL_REPORT_FIELDS) :]
    task = safe_component(task_name)
    for record in records:
        row = record.as_dict()
        source_suffix = Path(record.source_image_path).suffix.lower() or ".png"
        row["source_image_path"] = (
            f"{task}_single_molecule/{safe_component(record.image_id)}{source_suffix}"
        )
        row["reverse_structure_path"] = (
            f"{task}_re_structure/{safe_component(record.image_id)}.png"
        )
        lines.extend(
            [
                f"### {_markdown(record.image_id)}",
                "",
                *[f"- `{field}`: {_markdown(row[field])}" for field in detail_fields],
                "",
            ]
        )
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def _copy_sources(records: list[CandidateRecord], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for record in records:
        source = Path(record.source_image_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"source image missing for report: {source}")
        output = destination / f"{safe_component(record.image_id)}{source.suffix.lower()}"
        shutil.copyfile(source, output)
        copied.append(output)
    return copied


def _copy_reverse(records: list[CandidateRecord], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for record in records:
        output = destination / f"{safe_component(record.image_id)}.png"
        source = Path(record.reverse_structure_path).expanduser().resolve() if record.reverse_structure_path else None
        if source is not None and source.is_file():
            shutil.copyfile(source, output)
        else:
            make_placeholder(output, record.image_id, record.notes or "reverse structure unavailable")
        copied.append(output)
    return copied


def _copy_mol_folder(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    if source.is_dir():
        for mol_path in sorted(source.glob("*.mol"), key=lambda path: natural_sort_key(path.stem)):
            shutil.copyfile(mol_path, destination / mol_path.name)
            count += 1
    return count


def write_run_log(
    paths: TaskPaths,
    records: list[CandidateRecord],
    output_path: Path,
    *,
    failed_mol_count: int,
    input_mol_count: int,
) -> Path:
    status_counts = Counter(record.status for record in records)
    confidence_counts = Counter(record.confidence for record in records)
    events = read_events(paths)
    lines = [
        "# smiles_auto run log",
        "",
        f"- Task: `{paths.task_name}`",
        f"- Workspace evidence: `workspace/{paths.workspace_dir.name}/`",
        f"- Candidate table: `workspace/{paths.workspace_dir.name}/candidates.tsv`",
        f"- Molecules: {len(records)}",
        f"- Status counts: {dict(sorted(status_counts.items()))}",
        f"- Confidence counts: {dict(sorted(confidence_counts.items()))}",
        f"- ChemDraw failed seeds: {failed_mol_count}",
        f"- Required ChemDraw inputs: {input_mol_count}",
        f"- Structured events: {len(events)}",
        "",
        "The XLSX report contains the first five canonical candidate fields. "
        "Detailed evidence remains in the workspace and in the readable Markdown report.",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def build_review_bundle(paths: TaskPaths, output_dir: Path) -> Path:
    """Create a complete review tree inside the task workspace."""

    records = read_candidates(paths)
    chemdraw_fallback.validate_required_mols(paths, records)
    output = paths.assert_workspace_path(output_dir)
    if output.exists():
        raise FileExistsError(f"review staging already exists: {output}")
    output.mkdir(parents=True)
    task = safe_component(paths.task_name)

    source_dir = output / f"{task}_single_molecule"
    reverse_dir = output / f"{task}_re_structure"
    failed_dir = output / f"{task}_chemdraw"
    input_dir = output / f"{task}_chemdraw_input"
    source_images = _copy_sources(records, source_dir)
    reverse_images = _copy_reverse(records, reverse_dir)
    labels = [record.image_id for record in records]
    write_overview(
        source_images,
        output / f"{task}_single_molecule_overview.png",
        labels=labels,
    )
    write_overview(
        reverse_images,
        output / f"{task}_re_structure_overview.png",
        labels=labels,
    )
    failed_count = _copy_mol_folder(paths.chemdraw_failed_dir, failed_dir)
    input_count = _copy_mol_folder(paths.chemdraw_input_dir, input_dir)
    if input_count != len(records):
        raise RuntimeError(
            f"required ChemDraw MOL count mismatch: expected={len(records)}; actual={input_count}"
        )
    write_xlsx(records, output / f"{task}_smiles_report.xlsx")
    write_readable(records, output / f"{task}_readable.md", paths.task_name)
    write_run_log(
        paths,
        records,
        output / "run_log.md",
        failed_mol_count=failed_count,
        input_mol_count=input_count,
    )
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a review preview inside a task workspace.")
    parser.add_argument("workspace_dir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    configure_runtime(paths)
    output = build_review_bundle(paths, paths.review_staging_dir)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
