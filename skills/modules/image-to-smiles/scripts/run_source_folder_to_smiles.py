#!/usr/bin/env python3
"""Create one collision-safe workspace and run candidate generation."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path


sys.dont_write_bytecode = True

import chemdraw_fallback
import smiles_auto
import validate_setup
from smiles_core import (
    TaskPaths,
    append_event,
    collect_images,
    configure_runtime,
    initial_candidates,
    read_candidates,
    write_candidates,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate SMILES candidates from a *_single_molecule folder. "
            "Run this command from the target project root."
        )
    )
    parser.add_argument("input_dir", help="Explicit single-molecule image directory.")
    parser.add_argument("--run-date", help="Task date in YYYYMMDD; defaults to today.")
    parser.add_argument(
        "--task-name",
        help="Visible task name; otherwise inferred by removing _single_molecule.",
    )
    parser.add_argument("--no-name-lookup", action="store_true")
    parser.add_argument("--allow-fragments", action="store_true")
    parser.add_argument("--max-smiles-length", type=int, default=450)
    parser.add_argument("--pubchem-timeout", type=float, default=20.0)
    parser.add_argument("--policy", choices=["strict", "best-effort"], default="strict")
    parser.add_argument("--molscribe-checkpoint")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validation = validate_setup.run_validation(check_models=True)
    if not validation.ok:
        print(
            "error: required environment validation failed; no task workspace was created",
            file=sys.stderr,
        )
        return 2
    project_root = Path.cwd().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    try:
        images = collect_images(input_dir)
        paths = TaskPaths.for_new_task(
            input_dir,
            project_root=project_root,
            run_date=args.run_date,
            task_name=args.task_name,
        )
        paths.assert_new_task_available()
        paths.initialize_workspace()
        configure_runtime(paths)
        records = initial_candidates(images)
        write_candidates(paths, records)
        append_event(
            paths,
            stage="task_start",
            status="complete",
            message="workspace initialized",
            data={
                "input_dir": str(input_dir),
                "image_count": len(images),
                "review_dir": str(paths.review_dir),
            },
        )
        engine_config = smiles_auto.EngineConfig(
            lookup_names=not args.no_name_lookup,
            allow_fragments=args.allow_fragments,
            max_smiles_length=args.max_smiles_length,
            pubchem_timeout=args.pubchem_timeout,
            model_policy=args.policy,
            molscribe_checkpoint=(
                Path(args.molscribe_checkpoint).expanduser().resolve()
                if args.molscribe_checkpoint
                else None
            ),
        )
        processed = smiles_auto.process_records(paths, records, engine_config)

        first_pass_failures = [
            record for record in processed if record.status == "failure"
        ]
        recovered_ids: list[str] = []
        if first_pass_failures:
            retry_config = replace(engine_config, model_policy="best-effort")
            append_event(
                paths,
                stage="bounded_recovery",
                status="start",
                message="retry first-pass candidate-generation failures once",
                data={
                    "image_ids": [record.image_id for record in first_pass_failures],
                    "retry_policy": retry_config.model_policy,
                },
            )
            retry_results = smiles_auto.process_records(
                paths,
                first_pass_failures,
                retry_config,
            )
            for record in retry_results:
                recovered = record.status != "failure"
                if recovered:
                    recovered_ids.append(record.image_id)
                append_event(
                    paths,
                    stage="bounded_recovery",
                    status="candidate_found" if recovered else "human_required",
                    image_id=record.image_id,
                    message=(
                        "bounded retry produced a candidate; source comparison required"
                        if recovered
                        else "two candidate-generation attempts produced no accepted structure"
                    ),
                    data={
                        "total_candidate_attempts": 2,
                        "retry_policy": retry_config.model_policy,
                    },
                )
            processed = read_candidates(paths)
        created_mols, preserved_mols, missing_mol_ids = (
            chemdraw_fallback.prepare_required_mols(paths, processed)
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"runtime error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    pending = [record.image_id for record in processed if record.status == "pending"]
    failures = [record.image_id for record in processed if record.status == "failure"]
    append_event(
        paths,
        stage="candidate_batch",
        status="review_required" if pending or failures else "complete",
        message=f"pending={len(pending)}; failure={len(failures)}",
        data={"pending_ids": pending, "failure_ids": failures},
    )
    print(f"workspace: {paths.workspace_dir}")
    print(f"candidates: {paths.candidates_path}")
    print(f"planned review: {paths.review_dir}")
    print(f"bounded recovery attempted: {len(first_pass_failures)}")
    print(f"candidates recovered on retry: {len(recovered_ids)}")
    print(f"required ChemDraw MOL created: {len(created_mols)}")
    print(f"required ChemDraw MOL preserved: {len(preserved_mols)}")
    print(f"required ChemDraw MOL missing: {len(missing_mol_ids)}")
    if missing_mol_ids:
        print("human-required MOL ImageIDs: " + ", ".join(missing_mol_ids))
    print(f"pending source comparison: {len(pending)}")
    print(f"human-required unresolved failures: {len(failures)}")
    print("Next: inspect candidate_materials/comparisons, record each source review, then finalize.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
