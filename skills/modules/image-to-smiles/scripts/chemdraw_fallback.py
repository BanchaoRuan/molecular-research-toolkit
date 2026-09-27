#!/usr/bin/env python3
"""Generate, validate, and apply required ChemDraw MOL inputs."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable


sys.dont_write_bytecode = True

from render_smiles import render_record
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
)


def _evidence_smiles(paths: TaskPaths, image_id: str) -> Iterable[str]:
    file_id = safe_component(image_id)
    ocr_path = paths.ocr_dir / f"{file_id}.json"
    model_path = paths.model_dir / f"{file_id}.json"
    for path, key in ((ocr_path, "candidates"), (model_path, "predictions")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get(key, []):
            if isinstance(row, dict):
                value = str(row.get("canonical_smiles") or row.get("raw_smiles") or "")
                if value:
                    yield value


def _first_valid_seed(paths: TaskPaths, record: CandidateRecord, explicit: str = "") -> str:
    seen: set[str] = set()
    for raw in (explicit, record.smiles, *_evidence_smiles(paths, record.image_id)):
        if not raw or raw in seen:
            continue
        seen.add(raw)
        result = canonicalize_smiles(raw, allow_fragments=True)
        if result.rdkit_valid:
            return result.canonical
    return ""


def _write_mol(paths: TaskPaths, smiles: str, output_path: Path) -> Path:
    from rdkit import Chem

    validation = canonicalize_smiles(smiles, allow_fragments=True)
    if not validation.rdkit_valid or validation.mol is None:
        raise ValueError(f"cannot create MOL from invalid SMILES: {validation.reason}")
    output = paths.assert_workspace_path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.assert_workspace_path(output.with_name(f".{output.name}.tmp"))
    temporary.write_text(Chem.MolToMolBlock(validation.mol), encoding="utf-8")
    temporary.replace(output)
    return output


def _canonical_smiles_from_mol(mol_path: Path) -> str:
    from rdkit import Chem

    molecule = Chem.MolFromMolFile(str(mol_path), sanitize=True, removeHs=True)
    if molecule is None:
        raise ValueError(f"MOL is not RDKit-readable: {mol_path}")
    mol_smiles = Chem.MolToSmiles(molecule, isomericSmiles=True)
    validation = canonicalize_smiles(mol_smiles, allow_fragments=True)
    if not validation.rdkit_valid:
        raise ValueError(f"MOL cannot be canonicalized: {mol_path}: {validation.reason}")
    return validation.canonical


def _validate_mol_matches(mol_path: Path, canonical_smiles: str) -> None:
    mol_smiles = _canonical_smiles_from_mol(mol_path)
    if mol_smiles != canonical_smiles:
        raise ValueError(
            "MOL and candidate SMILES do not describe the same structure: "
            f"mol={mol_smiles}; smiles={canonical_smiles}"
        )


def prepare_required_mols(
    paths: TaskPaths,
    records: Iterable[CandidateRecord] | None = None,
) -> tuple[list[Path], list[Path], list[str]]:
    """Create one required ChemDraw input MOL per candidate when a valid seed exists."""

    active = list(records) if records is not None else read_candidates(paths)
    created: list[Path] = []
    preserved: list[Path] = []
    missing: list[str] = []
    for record in active:
        output = paths.assert_workspace_path(
            paths.chemdraw_input_dir / f"{safe_component(record.image_id)}.mol"
        )
        if output.is_file():
            preserved.append(output)
            append_event(
                paths,
                stage="chemdraw_required",
                status="preserved",
                image_id=record.image_id,
                message="existing required MOL preserved",
                data={"path": str(output)},
            )
            continue
        seed = _first_valid_seed(paths, record)
        if not seed:
            missing.append(record.image_id)
            append_event(
                paths,
                stage="chemdraw_required",
                status="human_required",
                image_id=record.image_id,
                message="required MOL missing because no RDKit-valid seed exists",
            )
            continue
        created.append(_write_mol(paths, seed, output))
        append_event(
            paths,
            stage="chemdraw_required",
            status="complete",
            image_id=record.image_id,
            message="required ChemDraw input MOL written",
            data={"path": str(output), "seed_smiles": seed},
        )
    return created, preserved, missing


def validate_required_mols(
    paths: TaskPaths,
    records: Iterable[CandidateRecord] | None = None,
) -> list[Path]:
    """Require exactly one readable input MOL per ImageID and match valid candidates."""

    active = list(records) if records is not None else read_candidates(paths)
    expected = {
        f"{safe_component(record.image_id)}.mol": record for record in active
    }
    actual = {
        path.name: path
        for path in paths.chemdraw_input_dir.glob("*.mol")
        if path.is_file()
    }
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    invalid: list[str] = []
    mismatched: list[str] = []
    for name, record in expected.items():
        mol_path = actual.get(name)
        if mol_path is None:
            continue
        try:
            mol_smiles = _canonical_smiles_from_mol(mol_path)
        except ValueError:
            invalid.append(name)
            continue
        if record.smiles and record.rdkit_valid == "true":
            validation = canonicalize_smiles(record.smiles, allow_fragments=True)
            if not validation.rdkit_valid or mol_smiles != validation.canonical:
                mismatched.append(name)
    if missing or unexpected or invalid or mismatched:
        raise RuntimeError(
            "required ChemDraw MOL validation failed: "
            f"missing={missing}; unexpected={unexpected}; "
            f"invalid={invalid}; mismatched={mismatched}"
        )
    return [actual[name] for name in expected]


def prepare_seed(paths: TaskPaths, image_id: str, *, smiles: str = "") -> Path | None:
    """Write one failed-candidate MOL only when a valid seed exists."""

    record = get_candidate(paths, image_id)
    if record.status != "failure":
        raise ValueError(f"ChemDraw fallback is only valid for failure rows: {image_id}")
    seed = _first_valid_seed(paths, record, smiles)
    if not seed:
        add_note(record, "ChemDraw seed not created: no RDKit-valid seed")
        update_candidate(paths, record)
        append_event(
            paths,
            stage="chemdraw_prepare",
            status="skipped",
            image_id=image_id,
            message="no RDKit-valid seed",
        )
        return None
    output = paths.chemdraw_failed_dir / f"{safe_component(image_id)}.mol"
    _write_mol(paths, seed, output)
    add_note(record, f"ChemDraw seed prepared: {output.name}")
    update_candidate(paths, record)
    append_event(
        paths,
        stage="chemdraw_prepare",
        status="complete",
        image_id=image_id,
        message="fallback MOL written",
        data={"path": str(output), "seed_smiles": seed},
    )
    return output


def apply_correction(
    paths: TaskPaths,
    image_id: str,
    *,
    smiles: str,
    mol_path: Path | None = None,
    notes: str = "",
) -> CandidateRecord:
    """Apply a corrected candidate, then return it to source-image review."""

    validation = canonicalize_smiles(smiles, allow_fragments=True)
    if not validation.rdkit_valid:
        raise ValueError(f"invalid corrected SMILES: {validation.reason}")
    record = get_candidate(paths, image_id)
    record.smiles = validation.canonical
    record.inchikey = validation.inchikey
    record.status = "pending"
    record.confidence = "pending"
    record.source_match = "pending"
    record.recognition_method = "chemdraw"
    record.rdkit_valid = "true"
    add_note(record, notes or "ChemDraw/manual correction applied; source comparison required")

    destination = paths.assert_workspace_path(
        paths.chemdraw_input_dir / f"{safe_component(image_id)}.mol"
    )
    if mol_path is not None:
        source = mol_path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"corrected MOL not found: {source}")
        _validate_mol_matches(source, validation.canonical)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source != destination.resolve():
            shutil.copy2(source, destination)
    else:
        _write_mol(paths, validation.canonical, destination)

    record = render_record(paths, record)
    update_candidate(paths, record)
    append_event(
        paths,
        stage="chemdraw_apply",
        status="pending_review",
        image_id=image_id,
        message="corrected candidate rendered; source comparison required",
        data={"mol_path": str(destination)},
    )
    return record


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage required ChemDraw MOL inputs and corrections.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_all_parser = subparsers.add_parser("prepare-all")
    prepare_all_parser.add_argument("workspace_dir")

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("workspace_dir")
    prepare_parser.add_argument("image_id")
    prepare_parser.add_argument("--smiles", default="")

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("workspace_dir")
    apply_parser.add_argument("image_id")
    apply_parser.add_argument("--smiles", required=True)
    apply_parser.add_argument("--mol")
    apply_parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = TaskPaths.from_workspace(Path(args.workspace_dir))
    configure_runtime(paths)
    if args.command == "prepare-all":
        created, preserved, missing = prepare_required_mols(paths)
        print(
            f"required MOL created={len(created)} preserved={len(preserved)} "
            f"missing={len(missing)}"
        )
        if missing:
            print("human-required ImageIDs: " + ", ".join(missing))
            return 1
        return 0
    if args.command == "prepare":
        output = prepare_seed(paths, args.image_id, smiles=args.smiles)
        if output is None:
            print(f"no valid seed for {args.image_id}")
            return 1
        print(output)
        return 0

    record = apply_correction(
        paths,
        args.image_id,
        smiles=args.smiles,
        mol_path=Path(args.mol) if args.mol else None,
        notes=args.notes,
    )
    print(f"updated {record.image_id}; source review remains pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
