#!/usr/bin/env python3
"""Per-image state machine for the smiles_auto v2 workflow."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


sys.dont_write_bytecode = True

import chemdraw_fallback
import render_smiles
import structure_predict
import text_lookup
from smiles_core import (
    CandidateRecord,
    TaskPaths,
    add_note,
    append_event,
    configure_runtime,
    read_candidates,
    safe_component,
    update_candidate,
)


@dataclass(frozen=True)
class EngineConfig:
    lookup_names: bool = True
    allow_fragments: bool = False
    max_smiles_length: int = 450
    pubchem_timeout: float = 20.0
    model_policy: str = "strict"
    molscribe_checkpoint: Path | None = None


def normalize_source_image(paths: TaskPaths, record: CandidateRecord) -> Path:
    from PIL import Image, ImageOps

    source = Path(record.source_image_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source image not found: {source}")
    output = paths.assert_workspace_path(
        paths.normalized_dir / f"{safe_component(record.image_id)}.png"
    )
    temporary = paths.assert_workspace_path(output.with_name(f".{output.name}.tmp.png"))
    with Image.open(source) as opened:
        ImageOps.exif_transpose(opened).convert("RGB").save(temporary, format="PNG")
    temporary.replace(output)
    return output


def _accept_text(record: CandidateRecord, result: text_lookup.LookupResult) -> None:
    record.smiles = result.chosen_smiles
    record.inchikey = result.chosen_inchikey
    record.recognition_method = result.recognition_method
    add_note(record, result.reason)


def _accept_model(record: CandidateRecord, result: structure_predict.ModelResult) -> None:
    record.smiles = result.chosen_smiles
    record.inchikey = result.chosen_inchikey
    record.recognition_method = f"model:{result.engine}"
    add_note(record, f"{result.reason}; {result.route_reason}")


def _mark_candidate_pending(record: CandidateRecord) -> None:
    record.status = "pending"
    record.confidence = "pending"
    record.source_match = "pending"
    record.rdkit_valid = "true"


def _mark_failure(record: CandidateRecord, reason: str) -> None:
    record.smiles = ""
    record.inchikey = ""
    record.status = "failure"
    record.confidence = "low"
    record.source_match = "no"
    record.recognition_method = "unresolved"
    record.rdkit_valid = "false"
    add_note(record, reason)


def process_record(
    paths: TaskPaths,
    record: CandidateRecord,
    config: EngineConfig,
) -> CandidateRecord:
    normalized = normalize_source_image(paths, record)
    text_result = text_lookup.lookup_image(
        record.image_id,
        normalized,
        paths,
        lookup_names=config.lookup_names,
        allow_fragments=config.allow_fragments,
        max_length=config.max_smiles_length,
        timeout=config.pubchem_timeout,
    )
    if text_result.chosen_smiles:
        _accept_text(record, text_result)
        _mark_candidate_pending(record)
    else:
        model_result = structure_predict.predict_image(
            record.image_id,
            normalized,
            paths,
            original_path=Path(record.source_image_path),
            config=structure_predict.ModelConfig(
                policy=config.model_policy,
                allow_fragments=config.allow_fragments,
                max_smiles_length=config.max_smiles_length,
                molscribe_checkpoint=config.molscribe_checkpoint,
            ),
        )
        if model_result.chosen_smiles:
            _accept_model(record, model_result)
            _mark_candidate_pending(record)
        else:
            _mark_failure(record, f"no accepted candidate: {text_result.reason}; {model_result.reason}")

    record = render_smiles.render_record(paths, record)
    update_candidate(paths, record)

    if record.status == "failure":
        chemdraw_fallback.prepare_seed(paths, record.image_id)
        record = next(
            item for item in read_candidates(paths) if item.image_id == record.image_id
        )
    append_event(
        paths,
        stage="candidate_state",
        status=record.status,
        image_id=record.image_id,
        message=(
            "source comparison required"
            if record.status == "pending"
            else "candidate generation finished without an accepted structure"
        ),
    )
    return record


def process_records(
    paths: TaskPaths,
    records: list[CandidateRecord],
    config: EngineConfig,
) -> list[CandidateRecord]:
    processed: list[CandidateRecord] = []
    for record in records:
        try:
            processed.append(process_record(paths, record, config))
        except Exception as exc:
            append_event(
                paths,
                stage="processing_error",
                status="error",
                image_id=record.image_id,
                message=f"{type(exc).__name__}: {exc}",
            )
            raise RuntimeError(f"processing stopped at {record.image_id}: {exc}") from exc
    return processed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate candidates inside an existing workspace.")
    parser.add_argument("workspace_dir")
    parser.add_argument("--image-id")
    parser.add_argument("--no-name-lookup", action="store_true")
    parser.add_argument("--allow-fragments", action="store_true")
    parser.add_argument("--max-smiles-length", type=int, default=450)
    parser.add_argument("--pubchem-timeout", type=float, default=20.0)
    parser.add_argument("--policy", choices=["strict", "best-effort"], default="strict")
    parser.add_argument("--molscribe-checkpoint")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    configure_runtime(paths)
    records = read_candidates(paths)
    if args.image_id:
        records = [record for record in records if record.image_id == args.image_id]
        if len(records) != 1:
            raise KeyError(f"candidate not found: {args.image_id}")
    try:
        processed = process_records(
            paths,
            records,
            EngineConfig(
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
            ),
        )
    except Exception as exc:
        print(f"runtime error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    pending = sum(record.status == "pending" for record in processed)
    failed = sum(record.status == "failure" for record in processed)
    print(f"processed={len(processed)} pending_review={pending} failure={failed}")
    return 0 if pending == 0 and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
