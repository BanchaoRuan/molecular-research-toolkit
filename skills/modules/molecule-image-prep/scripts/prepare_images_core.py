#!/usr/bin/env python3
"""Shared data, paths, and file operations for molecule-image-prep."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

sys.dont_write_bytecode = True

SKILL_NAME = "molecule-image-prep"
SKILL_DIR = Path(__file__).resolve().parent.parent
SUPPORTED_IMAGE_EXTENSIONS = frozenset((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"))
CROP_REVIEW_FIELDS = (
    "image_id", "source_image_id", "source_position_id", "source_location",
    "source_image_path", "single_molecule_path", "notes",
)
SOURCE_LOCATION_VALUES = (
    "top-left", "top-center", "top-right", "middle-left", "center", "middle-right",
    "bottom-left", "bottom-center", "bottom-right",
    "far-left", "left-center", "right-center", "far-right",
)


def assert_outside_skill_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == SKILL_DIR or SKILL_DIR in resolved.parents:
        raise ValueError(f"{label} must be outside the {SKILL_NAME} package: {resolved}")
    return resolved


def assert_within(path: Path, parent: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    root = parent.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes {label}: {resolved}")
    return resolved


def clean_cell(value: str) -> str:
    return str(value).strip()


def normalized_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def natural_sort_key(value: str) -> tuple:
    value = unicodedata.normalize("NFKC", value)
    parts = [(0, int(p)) if p.isdigit() else (1, p.casefold())
             for p in re.split(r"(\d+)", value) if p]
    return (*parts, (2, value))


def clean_task_name(value: str) -> str:
    name = str(value).strip()
    if (not name or name in (".", "..") or name.endswith(".")
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)):
        raise ValueError("task_name must be a non-empty, portable folder name")
    return name


def validate_output_identifier(value: str, label: str = "image_id") -> str:
    value = clean_cell(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError(f"{label} must contain only ASCII letters, digits, '_' or '-': {value!r}")
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value, flags=re.I):
        raise ValueError(f"{label} is a reserved filename: {value!r}")
    return value


def validate_source_location(value: str) -> str:
    value = clean_cell(value)
    if value not in SOURCE_LOCATION_VALUES:
        raise ValueError("source_location must be one of: " + ", ".join(SOURCE_LOCATION_VALUES))
    return value


def parse_start_id(prefix: str, width: int, start_id: str) -> int:
    prefix = validate_output_identifier(prefix, "id_prefix")
    if not 1 <= width <= 12:
        raise ValueError("id_width must be between 1 and 12")
    match = re.fullmatch(re.escape(prefix) + rf"([0-9]{{{width}}})", clean_cell(start_id))
    if not match:
        raise ValueError(f"start_id must be {prefix} followed by exactly {width} digits")
    return int(match.group(1))


def portable_source_name(value: str) -> str:
    name = PurePosixPath(value)
    if (not value or name.name != value or value in (".", "..")
            or "\\" in value or any(c in value for c in "\t\r\n\0")):
        raise ValueError(f"source_image_path must be a source filename: {value!r}")
    return value


@dataclass(frozen=True)
class TaskConfig:
    task_name: str
    run_date: str
    id_prefix: str
    id_width: int
    start_id: str
    has_existing_ids: bool
    reserved_ids: tuple[str, ...]
    crop_layout_rules: str
    source_origins: dict[str, str]

    @property
    def start_number(self) -> int:
        return parse_start_id(self.id_prefix, self.id_width, self.start_id)

    def validate(self) -> None:
        if clean_task_name(self.task_name) != self.task_name:
            raise ValueError("task_name contains leading or trailing whitespace")
        if not re.fullmatch(r"[0-9]{8}", self.run_date):
            raise ValueError("run_date must use YYYYMMDD")
        datetime.strptime(self.run_date, "%Y%m%d")
        self.start_number
        if not isinstance(self.has_existing_ids, bool):
            raise ValueError("has_existing_ids must be a boolean")
        known = set()
        for value in self.reserved_ids:
            if validate_output_identifier(value) != value:
                raise ValueError("reserved IDs must not contain surrounding whitespace")
            key = normalized_identifier(value)
            if key in known:
                raise ValueError(f"duplicate reserved ID: {value}")
            known.add(key)
        if self.has_existing_ids and not self.reserved_ids:
            raise ValueError("list the retained IDs with --reserve-id before initialization")
        if not clean_cell(self.crop_layout_rules):
            raise ValueError("crop and layout requirements must be established before initialization")
        if not self.source_origins:
            raise ValueError("at least one source image is required")
        for name, origin in self.source_origins.items():
            portable_source_name(name)
            if not isinstance(origin, str) or not Path(origin).is_absolute():
                raise ValueError(f"source origin must be an absolute path: {name}")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskConfig":
        if not isinstance(payload, dict) or set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("task_config.json does not match this release's task format")
        if not isinstance(payload["reserved_ids"], list) or not all(
                isinstance(x, str) for x in payload["reserved_ids"]):
            raise ValueError("reserved_ids must be a list of strings")
        if not isinstance(payload["source_origins"], dict):
            raise ValueError("source_origins must be an object")
        if not isinstance(payload["id_width"], int) or isinstance(payload["id_width"], bool):
            raise ValueError("id_width must be an integer")
        for key in ("task_name", "run_date", "id_prefix", "start_id", "crop_layout_rules"):
            if not isinstance(payload[key], str):
                raise ValueError(f"{key} must be a string")
        config = cls(**{**payload, "reserved_ids": tuple(payload["reserved_ids"])})
        config.validate()
        return config


@dataclass(frozen=True)
class CropReviewRecord:
    image_id: str
    source_image_id: str
    source_position_id: str
    source_location: str
    source_image_path: str
    single_molecule_path: str
    notes: str = ""

    def validate(self) -> None:
        if validate_output_identifier(self.image_id) != self.image_id:
            raise ValueError("image_id must not contain surrounding whitespace")
        for field in ("source_image_id", "source_position_id"):
            value = getattr(self, field)
            if not value.strip() or any(c in value for c in "\t\r\n\0"):
                raise ValueError(f"{field} must be non-empty text without control characters")
        validate_source_location(self.source_location)
        source = portable_source_name(self.source_image_path)
        if Path(source).stem.strip() != self.source_image_id:
            raise ValueError(f"source_image_id disagrees with source filename for {self.image_id}")
        relative = PurePosixPath(self.single_molecule_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ValueError("single_molecule_path must be a safe task-relative path")
        if relative.name != f"{self.image_id}.png":
            raise ValueError(f"single_molecule_path must end with {self.image_id}.png")

    def as_dict(self) -> dict[str, str]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "CropReviewRecord":
        if set(row) != set(CROP_REVIEW_FIELDS) or any(v is None for v in row.values()):
            raise ValueError("crop_review.tsv must have exactly seven fields on every row")
        record = cls(**row)
        record.validate()
        return record


@dataclass(frozen=True)
class TaskPaths:
    project_root: Path
    run_date: str
    task_name: str
    workspace_dir: Path
    review_dir: Path

    def __post_init__(self) -> None:
        assert_within(self.workspace_dir, self.project_root, "working project")
        assert_within(self.review_dir, self.project_root, "working project")
        assert_within(self.workspace_dir, self.project_root / "workspace", "project workspace")
        assert_within(self.review_dir, self.project_root / "review", "project review")
        assert_outside_skill_dir(self.workspace_dir, "workspace")
        assert_outside_skill_dir(self.review_dir, "review")

    @classmethod
    def for_new_task(cls, *, task_name: str, project_root: Path | None = None,
                     run_date: str | None = None) -> "TaskPaths":
        root = (project_root or Path.cwd()).expanduser().resolve()
        date = run_date or datetime.now().strftime("%Y%m%d")
        if not re.fullmatch(r"[0-9]{8}", date):
            raise ValueError("run_date must use YYYYMMDD")
        datetime.strptime(date, "%Y%m%d")
        name = clean_task_name(task_name)
        stem = f"{date}_{name}_images"
        return cls(root, date, name, root / "workspace" / stem, root / "review" / stem)

    @classmethod
    def from_workspace(cls, workspace_dir: Path) -> "TaskPaths":
        workspace = workspace_dir.expanduser().resolve()
        match = re.fullmatch(r"([0-9]{8})_(.+)_images", workspace.name)
        if workspace.parent.name != "workspace" or not match:
            raise ValueError(f"not an image-preparation task workspace: {workspace}")
        paths = cls.for_new_task(project_root=workspace.parent.parent,
                                 run_date=match[1], task_name=match[2])
        if paths.workspace_dir != workspace or not workspace.is_dir():
            raise ValueError(f"task workspace not found: {workspace}")
        return paths

    @property
    def crop_review_path(self) -> Path:
        return self.workspace_dir / "crop_review.tsv"

    @property
    def task_config_path(self) -> Path:
        return self.workspace_dir / "task_config.json"

    @property
    def source_dir(self) -> Path:
        return self.workspace_dir / "source_images"

    @property
    def single_molecule_dir(self) -> Path:
        return self.workspace_dir / f"{self.task_name}_prepare_single_molecule"

    @property
    def temp_dir(self) -> Path:
        return self.workspace_dir / "tmp"

    def assert_workspace_path(self, path: Path) -> Path:
        return assert_outside_skill_dir(
            assert_within(path, self.workspace_dir, "task workspace"), "runtime file")

    def assert_new_task_available(self) -> None:
        for path in (self.workspace_dir, self.review_dir):
            if path.exists():
                raise FileExistsError(
                    f"task already exists: {path}; resume the existing task instead of initializing")

    def initialize_workspace(self) -> None:
        self.assert_new_task_available()
        self.assert_workspace_path(self.workspace_dir).mkdir(parents=True, exist_ok=False)
        self.assert_workspace_path(self.source_dir).mkdir()
        self.assert_workspace_path(self.single_molecule_dir).mkdir()

    def relative_single_molecule_path(self, image_id: str) -> str:
        validate_output_identifier(image_id)
        return PurePosixPath(self.single_molecule_dir.name, f"{image_id}.png").as_posix()

    def resolve_workspace_relative(self, value: str) -> Path:
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts or "\\" in value:
            raise ValueError(f"unsafe workspace-relative path: {value}")
        return self.assert_workspace_path(self.workspace_dir.joinpath(*relative.parts))

    def source_path(self, source_name: str) -> Path:
        return self.assert_workspace_path(
            assert_within(self.source_dir / portable_source_name(source_name),
                          self.source_dir, "source snapshots"))


def configure_runtime(paths: TaskPaths) -> Path:
    directory = paths.assert_workspace_path(paths.temp_dir)
    directory.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(directory)
    tempfile.tempdir = str(directory)
    return directory


def atomic_write(paths: TaskPaths, destination: Path, data: bytes) -> None:
    destination = paths.assert_workspace_path(destination)
    directory = configure_runtime(paths)
    fd, name = tempfile.mkstemp(prefix="write-", dir=directory)
    staged = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        staged.replace(destination)
    finally:
        if staged.exists():
            staged.unlink()


def ensure_unique_records(records: Iterable[CropReviewRecord], paths: TaskPaths) -> None:
    ids, positions = set(), set()
    for row in records:
        row.validate()
        if row.single_molecule_path != paths.relative_single_molecule_path(row.image_id):
            raise ValueError(f"unexpected result path for {row.image_id}")
        key = normalized_identifier(row.image_id)
        position = (normalized_identifier(row.source_image_id),
                    normalized_identifier(row.source_position_id))
        if key in ids:
            raise ValueError(f"duplicate image_id: {row.image_id}")
        if position in positions:
            raise ValueError(f"duplicate source position: {row.source_image_id}/{row.source_position_id}")
        ids.add(key)
        positions.add(position)


def crop_review_bytes(paths: TaskPaths, records: Iterable[CropReviewRecord]) -> bytes:
    rows = sorted(records, key=lambda row: natural_sort_key(row.image_id))
    ensure_unique_records(rows, paths)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CROP_REVIEW_FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(row.as_dict() for row in rows)
    return buffer.getvalue().encode("utf-8")


def read_crop_review(paths: TaskPaths) -> list[CropReviewRecord]:
    path = paths.assert_workspace_path(paths.crop_review_path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != CROP_REVIEW_FIELDS:
            raise ValueError("crop_review.tsv has an unexpected header")
        records = [CropReviewRecord.from_dict(row) for row in reader]
    ensure_unique_records(records, paths)
    return sorted(records, key=lambda row: natural_sort_key(row.image_id))


def write_crop_review(paths: TaskPaths, records: Iterable[CropReviewRecord]) -> None:
    atomic_write(paths, paths.crop_review_path, crop_review_bytes(paths, records))


def write_task_config(paths: TaskPaths, config: TaskConfig) -> None:
    if config.task_name != paths.task_name or config.run_date != paths.run_date:
        raise ValueError("task config disagrees with its workspace")
    data = json.dumps(config.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(paths, paths.task_config_path, data.encode("utf-8"))


def read_task_config(paths: TaskPaths) -> TaskConfig:
    path = paths.assert_workspace_path(paths.task_config_path)
    config = TaskConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    if config.task_name != paths.task_name or config.run_date != paths.run_date:
        raise ValueError("task config disagrees with its workspace")
    return config


def next_image_id(config: TaskConfig, records: Iterable[CropReviewRecord]) -> str:
    used = {normalized_identifier(value) for value in config.reserved_ids}
    used.update(normalized_identifier(row.image_id) for row in records)
    for number in range(config.start_number, 10 ** config.id_width):
        candidate = f"{config.id_prefix}{number:0{config.id_width}d}"
        if normalized_identifier(candidate) not in used:
            return candidate
    raise ValueError("no unused ID remains within the confirmed numbering width")


def archive_review(paths: TaskPaths) -> Path | None:
    if not paths.review_dir.exists():
        return None
    review = assert_outside_skill_dir(
        assert_within(paths.review_dir, paths.project_root / "review", "project review"), "review")
    if not review.is_dir():
        raise ValueError(f"review path is not a directory: {review}")
    history = paths.assert_workspace_path(paths.workspace_dir / "review_history")
    history.mkdir(exist_ok=True)
    destination = history / datetime.now().strftime("%Y%m%dT%H%M%S%f")
    review.rename(destination)
    return destination


def commit_crop(paths: TaskPaths, record: CropReviewRecord, records: list[CropReviewRecord],
                png_data: bytes) -> None:
    """Replace the PNG and canonical mapping; restore the PNG on a caught write failure."""
    table_data = crop_review_bytes(paths, records)
    output = paths.resolve_workspace_relative(record.single_molecule_path)
    old_image = output.read_bytes() if output.exists() else None
    old_table = paths.crop_review_path.read_bytes()
    archived = archive_review(paths)
    try:
        atomic_write(paths, output, png_data)
        atomic_write(paths, paths.crop_review_path, table_data)
    except BaseException:
        if old_image is None:
            if output.exists():
                output.unlink()
        else:
            atomic_write(paths, output, old_image)
        atomic_write(paths, paths.crop_review_path, old_table)
        if archived is not None:
            archived.rename(paths.review_dir)
        raise
    if archived is not None:
        print(f"previous review retained in workspace: {archived}")
        print("Inspect the updated crop, then rebuild the review package.")
