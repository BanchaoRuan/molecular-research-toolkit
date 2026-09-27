#!/usr/bin/env python3
"""Shared contracts for the smiles_auto workflow.

This module is intentionally not a CLI.  It is the single source of truth for
task paths, ImageID handling, candidate-table I/O, statuses, SMILES
normalization, and structured event logging.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}

STATUS_VALUES = {"pending", "success", "failure"}
CONFIDENCE_VALUES = {"pending", "high", "medium", "low"}
SOURCE_MATCH_VALUES = {"pending", "yes", "no"}
RDKIT_VALID_VALUES = {"pending", "true", "false"}
TERMINAL_STATUSES = {"success", "failure"}
SKILL_DIR = Path(__file__).resolve().parent.parent


def assert_outside_skill_dir(path: Path, label: str) -> Path:
    """Reject every runtime write target located inside the deployed skill."""

    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(SKILL_DIR)
    except ValueError:
        return resolved
    raise ValueError(
        f"refusing {label} inside deployed skill directory: {resolved}; "
        f"run from the target project root instead of {SKILL_DIR}"
    )


@dataclass
class CandidateRecord:
    """Canonical eleven-column record defined by the v2 workflow."""

    image_id: str
    smiles: str = ""
    inchikey: str = ""
    status: str = "pending"
    confidence: str = "pending"
    source_match: str = "pending"
    recognition_method: str = "pending"
    rdkit_valid: str = "pending"
    source_image_path: str = ""
    reverse_structure_path: str = ""
    notes: str = ""

    def validate(self) -> None:
        if not self.image_id.strip():
            raise ValueError("image_id must not be empty")
        if self.status not in STATUS_VALUES:
            raise ValueError(f"invalid status for {self.image_id}: {self.status}")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError(f"invalid confidence for {self.image_id}: {self.confidence}")
        if self.source_match not in SOURCE_MATCH_VALUES:
            raise ValueError(f"invalid source_match for {self.image_id}: {self.source_match}")
        if self.rdkit_valid not in RDKIT_VALID_VALUES:
            raise ValueError(f"invalid rdkit_valid for {self.image_id}: {self.rdkit_valid}")
        if self.status == "success":
            if not self.smiles:
                raise ValueError(f"success row has no SMILES: {self.image_id}")
            if self.rdkit_valid != "true":
                raise ValueError(f"success row is not RDKit-valid: {self.image_id}")
            if self.source_match != "yes":
                raise ValueError(f"success row has not matched its source image: {self.image_id}")
            if not self.reverse_structure_path:
                raise ValueError(f"success row has no reverse structure: {self.image_id}")

    def as_dict(self) -> dict[str, str]:
        self.validate()
        return {item.name: str(getattr(self, item.name)) for item in fields(self)}

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "CandidateRecord":
        expected = candidate_fields()
        missing = [name for name in expected if name not in row]
        extra = [name for name in row if name not in expected]
        if missing or extra:
            raise ValueError(f"candidate schema mismatch: missing={missing}; extra={extra}")
        record = cls(**{name: str(row.get(name, "") or "") for name in expected})
        record.validate()
        return record

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


def candidate_fields() -> list[str]:
    return [item.name for item in fields(CandidateRecord)]


FINAL_REPORT_FIELDS = candidate_fields()[:5]


@dataclass(frozen=True)
class TaskPaths:
    """All paths for one YYYYMMDD_taskname_smiles run."""

    project_root: Path
    run_date: str
    task_name: str
    workspace_dir: Path
    review_dir: Path

    def __post_init__(self) -> None:
        assert_outside_skill_dir(self.workspace_dir, "workspace path")
        assert_outside_skill_dir(self.review_dir, "review path")

    @classmethod
    def for_new_task(
        cls,
        input_dir: Path,
        *,
        project_root: Path | None = None,
        run_date: str | None = None,
        task_name: str | None = None,
    ) -> "TaskPaths":
        root = (project_root or Path.cwd()).expanduser().resolve()
        date = run_date or datetime.now().strftime("%Y%m%d")
        if not re.fullmatch(r"\d{8}", date):
            raise ValueError("run_date must use YYYYMMDD")

        input_path = input_dir.expanduser().resolve()
        inferred = input_path.name
        if task_name is None:
            suffix = "_single_molecule"
            if not inferred.endswith(suffix):
                raise ValueError(
                    "input directory must end with '_single_molecule', "
                    "or pass --task-name explicitly"
                )
            inferred = inferred[: -len(suffix)]
        name = clean_task_name(task_name or inferred)
        stem = f"{date}_{name}_smiles"
        return cls(
            project_root=root,
            run_date=date,
            task_name=name,
            workspace_dir=(root / "workspace" / stem).resolve(),
            review_dir=(root / "review" / stem).resolve(),
        )

    @classmethod
    def from_workspace(cls, workspace_dir: Path) -> "TaskPaths":
        workspace = workspace_dir.expanduser().resolve()
        if workspace.parent.name != "workspace":
            raise ValueError(f"not a project workspace task directory: {workspace}")
        match = re.fullmatch(r"(\d{8})_(.+)_smiles", workspace.name)
        if not match:
            raise ValueError(f"invalid workspace task name: {workspace.name}")
        root = workspace.parent.parent.resolve()
        return cls(
            project_root=root,
            run_date=match.group(1),
            task_name=match.group(2),
            workspace_dir=workspace,
            review_dir=(root / "review" / workspace.name).resolve(),
        )

    @property
    def candidates_path(self) -> Path:
        return self.workspace_dir / "candidates.tsv"

    @property
    def events_path(self) -> Path:
        return self.workspace_dir / "events.jsonl"

    @property
    def materials_dir(self) -> Path:
        return self.workspace_dir / "candidate_materials"

    @property
    def normalized_dir(self) -> Path:
        return self.materials_dir / "normalized_images"

    @property
    def ocr_dir(self) -> Path:
        return self.materials_dir / "ocr"

    @property
    def model_dir(self) -> Path:
        return self.materials_dir / "model_predictions"

    @property
    def reverse_dir(self) -> Path:
        return self.materials_dir / "reverse_structures"

    @property
    def comparisons_dir(self) -> Path:
        return self.materials_dir / "comparisons"

    @property
    def chemdraw_failed_dir(self) -> Path:
        return self.materials_dir / "chemdraw" / "failed"

    @property
    def chemdraw_input_dir(self) -> Path:
        return self.materials_dir / "chemdraw" / "input"

    @property
    def cache_dir(self) -> Path:
        return self.workspace_dir / "cache"

    @property
    def tmp_dir(self) -> Path:
        return self.workspace_dir / "tmp"

    @property
    def review_staging_dir(self) -> Path:
        return self.workspace_dir / "review_staging"

    def assert_new_task_available(self) -> None:
        collisions = [path for path in (self.workspace_dir, self.review_dir) if path.exists()]
        if collisions:
            joined = ", ".join(str(path) for path in collisions)
            raise FileExistsError(f"same-day task already exists: {joined}")

    def initialize_workspace(self) -> None:
        self.assert_new_task_available()
        for path in (
            self.workspace_dir,
            self.normalized_dir,
            self.ocr_dir,
            self.model_dir,
            self.reverse_dir,
            self.comparisons_dir,
            self.chemdraw_failed_dir,
            self.chemdraw_input_dir,
            self.cache_dir,
            self.tmp_dir,
        ):
            self.assert_workspace_path(path)
            path.mkdir(parents=True, exist_ok=False if path == self.workspace_dir else True)

    def assert_workspace_path(self, path: Path) -> Path:
        resolved = assert_within(path, self.workspace_dir, "workspace")
        return assert_outside_skill_dir(resolved, "workspace write")

    def assert_review_path(self, path: Path) -> Path:
        resolved = assert_within(path, self.review_dir, "review")
        return assert_outside_skill_dir(resolved, "review write")


def assert_within(path: Path, parent: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    root = parent.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes {label}: {resolved}") from exc
    return resolved


def clean_task_name(value: str) -> str:
    cleaned = re.sub(r"[/:\\\0]+", "_", value).strip().strip(".")
    if not cleaned:
        raise ValueError("task_name must not be empty")
    return cleaned


def safe_component(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[/:\\\0]+", "_", value).strip().strip(".")
    return cleaned or fallback


def normalized_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def natural_sort_key(value: str) -> tuple[tuple[int, Any], ...]:
    normalized = unicodedata.normalize("NFKC", value)
    parts = re.split(r"(\d+)", normalized)
    key: list[tuple[int, Any]] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    key.append((2, normalized))
    return tuple(key)


def image_id_from_path(path: Path) -> str:
    image_id = path.stem.strip()
    if not image_id:
        raise ValueError(f"image filename has an empty stem: {path}")
    return image_id


def collect_images(input_dir: Path) -> list[Path]:
    directory = input_dir.expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"input directory not found: {directory}")

    images = [
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    images.sort(key=lambda path: (natural_sort_key(path.stem), path.suffix.casefold()))
    if not images:
        raise ValueError(f"no supported molecule images found: {directory}")

    seen: dict[str, Path] = {}
    safe_seen: dict[str, Path] = {}
    for path in images:
        image_id = image_id_from_path(path)
        key = normalized_identifier(image_id)
        if key in seen:
            raise ValueError(
                "duplicate image_id after filename normalization: "
                f"{seen[key].name!r} and {path.name!r}"
            )
        seen[key] = path
        safe_key = normalized_identifier(safe_component(image_id))
        if safe_key in safe_seen:
            raise ValueError(
                "duplicate output filename after ImageID sanitization: "
                f"{safe_seen[safe_key].name!r} and {path.name!r}"
            )
        safe_seen[safe_key] = path
    return images


def initial_candidates(images: Iterable[Path]) -> list[CandidateRecord]:
    records = [
        CandidateRecord(
            image_id=image_id_from_path(path),
            source_image_path=str(path.resolve()),
        )
        for path in images
    ]
    return sorted(records, key=lambda item: natural_sort_key(item.image_id))


def read_candidates(paths: TaskPaths) -> list[CandidateRecord]:
    path = paths.assert_workspace_path(paths.candidates_path)
    if not path.exists():
        raise FileNotFoundError(f"candidate table not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != candidate_fields():
            raise ValueError(
                f"candidate header mismatch: expected={candidate_fields()}; actual={reader.fieldnames}"
            )
        records = [CandidateRecord.from_dict(dict(row)) for row in reader]
    ensure_unique_records(records)
    return sorted(records, key=lambda item: natural_sort_key(item.image_id))


def write_candidates(paths: TaskPaths, records: Iterable[CandidateRecord]) -> Path:
    rows = list(records)
    ensure_unique_records(rows)
    rows.sort(key=lambda item: natural_sort_key(item.image_id))
    path = paths.assert_workspace_path(paths.candidates_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = paths.assert_workspace_path(path.with_name(f".{path.name}.tmp"))
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=candidate_fields(),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for record in rows:
            writer.writerow(record.as_dict())
    temp_path.replace(path)
    return path


def update_candidate(paths: TaskPaths, updated: CandidateRecord) -> CandidateRecord:
    updated.validate()
    records = read_candidates(paths)
    matches = [index for index, item in enumerate(records) if item.image_id == updated.image_id]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one candidate row for {updated.image_id}")
    records[matches[0]] = updated
    write_candidates(paths, records)
    return updated


def get_candidate(paths: TaskPaths, image_id: str) -> CandidateRecord:
    matches = [item for item in read_candidates(paths) if item.image_id == image_id]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one candidate row for {image_id}")
    return matches[0]


def ensure_unique_records(records: Iterable[CandidateRecord]) -> None:
    seen: dict[str, str] = {}
    safe_seen: dict[str, str] = {}
    for record in records:
        record.validate()
        key = normalized_identifier(record.image_id)
        if key in seen:
            raise ValueError(f"duplicate candidate image_id: {seen[key]!r} and {record.image_id!r}")
        seen[key] = record.image_id
        safe_key = normalized_identifier(safe_component(record.image_id))
        if safe_key in safe_seen:
            raise ValueError(
                "duplicate candidate output filename: "
                f"{safe_seen[safe_key]!r} and {record.image_id!r}"
            )
        safe_seen[safe_key] = record.image_id


def add_note(record: CandidateRecord, note: str) -> None:
    cleaned = " ".join(str(note).split())
    if not cleaned:
        return
    record.notes = f"{record.notes}; {cleaned}" if record.notes else cleaned


@dataclass
class SmilesResult:
    raw: str
    canonical: str = ""
    inchikey: str = ""
    rdkit_valid: bool = False
    reason: str = ""
    mol: Any | None = None


def canonicalize_smiles(
    smiles: str,
    *,
    allow_fragments: bool = False,
    max_length: int = 450,
) -> SmilesResult:
    raw = (smiles or "").strip()
    if not raw:
        return SmilesResult(raw=raw, reason="empty")
    if len(raw) > max_length:
        return SmilesResult(raw=raw, reason="too_long")
    if "*" in raw:
        return SmilesResult(raw=raw, reason="wildcard_atom")
    if "." in raw and not allow_fragments:
        return SmilesResult(raw=raw, reason="fragment_not_allowed")

    try:
        from rdkit import Chem
        from rdkit.Chem import inchi
    except Exception as exc:
        return SmilesResult(raw=raw, reason=f"rdkit_import_failed:{exc}")

    mol = Chem.MolFromSmiles(raw)
    if mol is None:
        return SmilesResult(raw=raw, reason="rdkit_parse_failed")
    try:
        Chem.SanitizeMol(mol)
        canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
    except Exception as exc:
        return SmilesResult(raw=raw, reason=f"rdkit_sanitize_failed:{exc}")
    try:
        inchikey = inchi.MolToInchiKey(mol)
    except Exception:
        inchikey = ""
    return SmilesResult(
        raw=raw,
        canonical=canonical,
        inchikey=inchikey,
        rdkit_valid=True,
        reason="ok",
        mol=mol,
    )


def configure_runtime(paths: TaskPaths) -> None:
    """Force writable runtime state into the task workspace."""

    for path in (paths.cache_dir, paths.tmp_dir):
        paths.assert_workspace_path(path)
        path.mkdir(parents=True, exist_ok=True)
    cache = str(paths.cache_dir.resolve())
    tmp = str(paths.tmp_dir.resolve())
    environment = {
        "HF_HOME": str((paths.cache_dir / "huggingface").resolve()),
        "HF_HUB_CACHE": str((paths.cache_dir / "huggingface" / "hub").resolve()),
        "TRANSFORMERS_CACHE": str((paths.cache_dir / "transformers").resolve()),
        "TORCH_HOME": str((paths.cache_dir / "torch").resolve()),
        "KERAS_HOME": str((paths.cache_dir / "keras").resolve()),
        "XDG_CACHE_HOME": cache,
        "MPLCONFIGDIR": str((paths.cache_dir / "matplotlib").resolve()),
        "TMPDIR": tmp,
        "TEMP": tmp,
        "TMP": tmp,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key, value in environment.items():
        os.environ[key] = value
    tempfile.tempdir = tmp
    sys.dont_write_bytecode = True


def append_event(
    paths: TaskPaths,
    *,
    stage: str,
    status: str,
    message: str,
    image_id: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    event_path = paths.assert_workspace_path(paths.events_path)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        "image_id": image_id,
        "message": message,
        "data": data or {},
    }
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_events(paths: TaskPaths) -> list[dict[str, Any]]:
    path = paths.assert_workspace_path(paths.events_path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def write_workspace_json(paths: TaskPaths, path: Path, payload: Any) -> Path:
    output = paths.assert_workspace_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = paths.assert_workspace_path(output.with_name(f".{output.name}.tmp"))
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(output)
    return output
