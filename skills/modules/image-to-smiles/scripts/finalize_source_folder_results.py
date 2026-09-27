#!/usr/bin/env python3
"""Publish a terminal candidate batch from workspace to review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.dont_write_bytecode = True

import make_reports
from smiles_core import (
    TaskPaths,
    append_event,
    configure_runtime,
    read_candidates,
    read_events,
    safe_component,
)


def finalize(paths: TaskPaths) -> Path:
    records = read_candidates(paths)
    pending = [record.image_id for record in records if not record.is_terminal]
    if pending:
        raise RuntimeError(
            "cannot finalize while candidate rows remain pending: " + ", ".join(pending)
        )
    candidate_attempts: dict[str, int] = {}
    for event in read_events(paths):
        if event.get("stage") != "candidate_state" or not event.get("image_id"):
            continue
        image_id = str(event["image_id"])
        candidate_attempts[image_id] = candidate_attempts.get(image_id, 0) + 1
    first_pass_failures = [
        record.image_id
        for record in records
        if record.status == "failure"
        and record.recognition_method == "unresolved"
        and candidate_attempts.get(record.image_id, 0) < 2
    ]
    if first_pass_failures:
        raise RuntimeError(
            "cannot finalize first-pass candidate-generation failures before one bounded retry: "
            + ", ".join(first_pass_failures)
        )
    missing_success_reverse = [
        record.image_id
        for record in records
        if record.status == "success"
        and not Path(record.reverse_structure_path).expanduser().resolve().is_file()
    ]
    if missing_success_reverse:
        raise RuntimeError(
            "successful rows have missing reverse structures: "
            + ", ".join(missing_success_reverse)
        )
    if paths.review_dir.exists():
        raise FileExistsError(f"review task already exists: {paths.review_dir}")
    if paths.review_staging_dir.exists():
        raise FileExistsError(
            "review staging already exists; inspect it before deciding whether to remove it: "
            f"{paths.review_staging_dir}"
        )

    append_event(
        paths,
        stage="finalize",
        status="start",
        message="all candidate rows are terminal",
        data={"review_dir": str(paths.review_dir)},
    )
    staging = make_reports.build_review_bundle(paths, paths.review_staging_dir)
    task = safe_component(paths.task_name)
    expected = [
        staging / f"{task}_smiles_report.xlsx",
        staging / f"{task}_single_molecule_overview.png",
        staging / f"{task}_re_structure_overview.png",
        staging / f"{task}_readable.md",
        staging / "run_log.md",
    ]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"review staging is incomplete: {missing}")

    paths.review_dir.parent.mkdir(parents=True, exist_ok=True)
    staging.replace(paths.review_dir)
    append_event(
        paths,
        stage="finalize",
        status="complete",
        message="review bundle published",
        data={"review_dir": str(paths.review_dir)},
    )
    return paths.review_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one terminal smiles_auto task.")
    parser.add_argument("workspace_dir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    configure_runtime(paths)
    try:
        review_dir = finalize(paths)
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(review_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
