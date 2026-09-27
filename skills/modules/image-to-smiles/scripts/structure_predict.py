#!/usr/bin/env python3
"""Generate OCSR candidates with MolScribe or DECIMER."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

from smiles_core import (
    TaskPaths,
    add_note,
    append_event,
    canonicalize_smiles,
    configure_runtime,
    read_candidates,
    safe_component,
    update_candidate,
    write_workspace_json,
)


@dataclass(frozen=True)
class ModelConfig:
    policy: str = "strict"
    allow_fragments: bool = False
    max_smiles_length: int = 450
    molscribe_checkpoint: Path | None = None
    forced_route: str = "auto"

    def validate(self) -> None:
        if self.policy not in {"strict", "best-effort"}:
            raise ValueError(f"invalid model policy: {self.policy}")
        if self.forced_route not in {"auto", "printed", "handdrawn"}:
            raise ValueError(f"invalid model route: {self.forced_route}")


@dataclass
class PredictionRecord:
    variant: str
    engine: str
    raw_smiles: str
    canonical_smiles: str
    inchikey: str
    rdkit_valid: bool
    reason: str


@dataclass
class ModelResult:
    image_id: str
    route: str
    route_reason: str
    engine: str
    chosen_smiles: str
    chosen_inchikey: str
    reason: str
    model_error: str
    predictions: list[PredictionRecord]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prediction_count"] = len(self.predictions)
        return payload


def _imports() -> tuple[Any, Any, Any, Any]:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    return cv2, np, Image, ImageOps


def _is_camera_photo(path: Path) -> bool:
    _cv2, _np, Image, _ImageOps = _imports()
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            return bool(exif.get(271) or exif.get(272))
    except Exception:
        return False


def _detect_lined_paper(gray: Any) -> tuple[bool, int, float]:
    cv2, _np, _Image, _ImageOps = _imports()
    height, width = gray.shape
    inverted = 255 - gray
    _, binary = cv2.threshold(inverted, 25, 255, cv2.THRESH_BINARY)
    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(80, width // 5), 1)),
        iterations=1,
    )
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        horizontal,
        connectivity=8,
    )
    long_lines = 0
    line_pixels = 0
    for label in range(1, count):
        _x, _y, line_width, line_height, area = stats[label]
        if line_width > width * 0.35 and line_height <= max(8, height * 0.01) and area > width * 0.03:
            long_lines += 1
            line_pixels += int(area)
    density = line_pixels / float(max(1, height * width))
    return long_lines >= 3 and density > 0.0008, long_lines, density


def classify_image(image_path: Path, original_path: Path | None = None) -> tuple[str, str]:
    _cv2, np, Image, ImageOps = _imports()
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("L")
        gray = np.array(image)
    bright_fraction = float((gray > 235).mean())
    dark_fraction = float((gray < 80).mean())
    gray_std = float(gray.std())
    lined, line_count, line_density = _detect_lined_paper(gray)
    camera_photo = _is_camera_photo(original_path or image_path)

    if lined:
        return "reject", f"lined_background lines={line_count} density={line_density:.5f}"
    if camera_photo:
        if bright_fraction < 0.35 or dark_fraction > 0.35:
            return "reject", "camera_background_not_white_enough"
        return "handdrawn", "camera_photo_plain_background"
    if bright_fraction > 0.55 and gray_std > 18:
        return "printed", "clean_light_background"
    return "printed", "non_camera_default"


def _normalize_background(gray: Any) -> Any:
    cv2, _np, _Image, _ImageOps = _imports()
    background = cv2.GaussianBlur(gray, (0, 0), 65)
    flattened = cv2.divide(gray, background, scale=255)
    return cv2.normalize(flattened, None, 0, 255, cv2.NORM_MINMAX)


def make_variants(image_path: Path, output_dir: Path, paths: TaskPaths) -> list[Path]:
    cv2, np, Image, ImageOps = _imports()
    paths.assert_workspace_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")

    raw_path = paths.assert_workspace_path(output_dir / "raw.png")
    enhanced_path = paths.assert_workspace_path(output_dir / "enhanced.png")
    morph_path = paths.assert_workspace_path(output_dir / "morph.png")
    image.save(raw_path)

    array = np.array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    flattened = _normalize_background(gray)
    enhanced = 255 - cv2.convertScaleAbs(255 - flattened, alpha=3.0, beta=0)
    enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
    enhanced = cv2.convertScaleAbs(enhanced, alpha=1.35, beta=-35)
    enhanced = np.clip(enhanced, 0, 255).astype("uint8")
    Image.fromarray(enhanced).convert("RGB").save(enhanced_path)

    inverted = 255 - enhanced
    _, binary = cv2.threshold(inverted, 35, 255, cv2.THRESH_BINARY)
    closed = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )
    dilated = cv2.dilate(
        closed,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    Image.fromarray(255 - dilated).convert("RGB").save(morph_path)
    return [raw_path, enhanced_path, morph_path]


class MolScribeRunner:
    def __init__(self, checkpoint: Path | None):
        import torch
        from huggingface_hub import hf_hub_download
        from molscribe import MolScribe

        if checkpoint is not None:
            resolved = checkpoint.expanduser().resolve()
            if not resolved.is_file():
                raise FileNotFoundError(f"MolScribe checkpoint not found: {resolved}")
        else:
            resolved = Path(hf_hub_download("yujieq/MolScribe", "swin_base_char_aux_1m.pth"))
        self.model = MolScribe(str(resolved), device=torch.device("cpu"))

    def predict(self, image_path: Path) -> str:
        prediction = self.model.predict_image_file(
            str(image_path),
            return_atoms_bonds=False,
            return_confidence=False,
        )
        return str(prediction.get("smiles", "")) if isinstance(prediction, dict) else ""


_MOLSCRIBE_RUNNERS: dict[str, MolScribeRunner] = {}
_DECIMER_PREDICTOR: Any | None = None


def _run_molscribe(variants: list[Path], checkpoint: Path | None) -> tuple[list[str], str]:
    key = str(checkpoint.expanduser().resolve()) if checkpoint else "default"
    try:
        runner = _MOLSCRIBE_RUNNERS.get(key)
        if runner is None:
            runner = MolScribeRunner(checkpoint)
            _MOLSCRIBE_RUNNERS[key] = runner
    except Exception as exc:
        return [""] * len(variants), f"MolScribe:{type(exc).__name__}:{exc}"

    predictions: list[str] = []
    errors: list[str] = []
    for path in variants:
        try:
            predictions.append(runner.predict(path))
        except Exception as exc:
            predictions.append("")
            errors.append(f"{path.name}:{type(exc).__name__}:{exc}")
    return predictions, "; ".join(errors)


def _run_decimer(variants: list[Path]) -> tuple[list[str], str]:
    global _DECIMER_PREDICTOR
    try:
        if _DECIMER_PREDICTOR is None:
            from DECIMER import predict_SMILES

            _DECIMER_PREDICTOR = predict_SMILES
    except Exception as exc:
        return [""] * len(variants), f"DECIMER:{type(exc).__name__}:{exc}"

    predictions: list[str] = []
    errors: list[str] = []
    for path in variants:
        try:
            predictions.append(str(_DECIMER_PREDICTOR(str(path), hand_drawn=True) or ""))
        except Exception as exc:
            predictions.append("")
            errors.append(f"{path.name}:{type(exc).__name__}:{exc}")
    return predictions, "; ".join(errors)


def _evaluate_predictions(
    raw_values: list[str],
    variants: list[Path],
    engine: str,
    config: ModelConfig,
) -> tuple[str, str, list[PredictionRecord], str]:
    records: list[PredictionRecord] = []
    canonical_values: list[str] = []
    inchikeys: dict[str, str] = {}
    for variant, raw in zip(variants, raw_values):
        result = canonicalize_smiles(
            raw,
            allow_fragments=config.allow_fragments,
            max_length=config.max_smiles_length,
        )
        records.append(
            PredictionRecord(
                variant=variant.name,
                engine=engine,
                raw_smiles=raw,
                canonical_smiles=result.canonical,
                inchikey=result.inchikey,
                rdkit_valid=result.rdkit_valid,
                reason=result.reason,
            )
        )
        if result.rdkit_valid:
            canonical_values.append(result.canonical)
            inchikeys[result.canonical] = result.inchikey

    if not canonical_values:
        return "", "", records, "no_valid_model_candidate"
    counts = Counter(canonical_values)
    chosen, count = sorted(counts.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0]
    if count >= 2:
        return chosen, inchikeys.get(chosen, ""), records, "variant_consensus"
    if config.policy == "best-effort":
        return chosen, inchikeys.get(chosen, ""), records, "best_effort_single_variant"
    return "", "", records, "no_variant_consensus"


def predict_image(
    image_id: str,
    image_path: Path,
    paths: TaskPaths,
    *,
    original_path: Path | None = None,
    config: ModelConfig | None = None,
) -> ModelResult:
    active = config or ModelConfig()
    active.validate()
    route, route_reason = classify_image(image_path, original_path)
    if active.forced_route != "auto":
        route, route_reason = active.forced_route, f"forced_{active.forced_route}"

    output_dir = paths.model_dir / safe_component(image_id)
    if route == "reject":
        result = ModelResult(
            image_id=image_id,
            route=route,
            route_reason=route_reason,
            engine="none",
            chosen_smiles="",
            chosen_inchikey="",
            reason="image_rejected",
            model_error="",
            predictions=[],
        )
    else:
        variants = make_variants(image_path, output_dir, paths)
        if route == "printed":
            engine = "molscribe"
            raw_values, model_error = _run_molscribe(variants, active.molscribe_checkpoint)
        else:
            engine = "decimer"
            raw_values, model_error = _run_decimer(variants)
        chosen, inchikey, predictions, reason = _evaluate_predictions(
            raw_values,
            variants,
            engine,
            active,
        )
        if model_error and not chosen:
            reason = "model_unavailable"
        result = ModelResult(
            image_id=image_id,
            route=route,
            route_reason=route_reason,
            engine=engine,
            chosen_smiles=chosen,
            chosen_inchikey=inchikey,
            reason=reason,
            model_error=model_error,
            predictions=predictions,
        )

    evidence_path = paths.model_dir / f"{safe_component(image_id)}.json"
    write_workspace_json(paths, evidence_path, result.as_dict())
    append_event(
        paths,
        stage="structure_predict",
        status=(
            "error" if result.model_error and not result.chosen_smiles
            else "candidate" if result.chosen_smiles else "no_candidate"
        ),
        image_id=image_id,
        message=result.reason,
        data={"route": result.route, "engine": result.engine, "evidence": str(evidence_path)},
    )
    if result.model_error and not result.chosen_smiles:
        raise RuntimeError(f"{result.engine} failed for {image_id}: {result.model_error}")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OCSR inside an existing task workspace.")
    parser.add_argument("workspace_dir")
    parser.add_argument("--image-id")
    parser.add_argument("--route", choices=["auto", "printed", "handdrawn"], default="auto")
    parser.add_argument("--policy", choices=["strict", "best-effort"], default="strict")
    parser.add_argument("--allow-fragments", action="store_true")
    parser.add_argument("--max-smiles-length", type=int, default=450)
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

    config = ModelConfig(
        policy=args.policy,
        allow_fragments=args.allow_fragments,
        max_smiles_length=args.max_smiles_length,
        molscribe_checkpoint=Path(args.molscribe_checkpoint) if args.molscribe_checkpoint else None,
        forced_route=args.route,
    )
    found = 0
    for record in records:
        result = predict_image(
            record.image_id,
            Path(record.source_image_path),
            paths,
            original_path=Path(record.source_image_path),
            config=config,
        )
        if result.chosen_smiles:
            record.smiles = result.chosen_smiles
            record.inchikey = result.chosen_inchikey
            record.rdkit_valid = "true"
            record.recognition_method = f"model:{result.engine}"
            record.status = "pending"
            record.confidence = "pending"
            record.source_match = "pending"
            add_note(record, result.reason)
            update_candidate(paths, record)
            found += 1
    print(f"model candidates found: {found}/{len(records)}")
    return 0 if found == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
