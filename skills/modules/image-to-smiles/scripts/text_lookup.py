#!/usr/bin/env python3
"""Extract text evidence from molecule images and query PubChem."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


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


CAS_PATTERN = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
CID_PATTERN = re.compile(r"\bCID\s*[:#=]?\s*(\d+)\b", re.IGNORECASE)
INCHIKEY_PATTERN = re.compile(r"\b[A-Z]{14}-[A-Z]{10}-[A-Z]\b", re.IGNORECASE)
SMILES_PATTERN = re.compile(r"\bSMILES\s*[:=]\s*([^\s;]+)", re.IGNORECASE)
NAME_PATTERN = re.compile(
    r"^(?:name|compound|molecule)\s*[:=]\s*(.+?)\s*$",
    re.IGNORECASE,
)


@dataclass
class TextCandidate:
    kind: str
    query: str
    raw_smiles: str = ""
    canonical_smiles: str = ""
    inchikey: str = ""
    rdkit_valid: bool = False
    reason: str = ""


@dataclass
class LookupResult:
    image_id: str
    ocr_text: str
    tesseract_error: str
    chosen_smiles: str
    chosen_inchikey: str
    recognition_method: str
    reason: str
    candidates: list[TextCandidate]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_count"] = len(self.candidates)
        return payload


def run_tesseract(image_path: Path) -> tuple[str, str]:
    """Return OCR text without creating any sidecar file."""

    try:
        process = subprocess.run(
            ["tesseract", str(image_path), "stdout", "--psm", "6"],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return "", str(exc)
    if process.returncode != 0:
        return process.stdout.strip(), process.stderr.strip() or f"exit={process.returncode}"
    return process.stdout.strip(), ""


def _pubchem_property(namespace: str, value: str, timeout: float) -> dict[str, str]:
    encoded = quote(value.strip(), safe="")
    properties = "CanonicalSMILES,IsomericSMILES,InChIKey"
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
        f"{namespace}/{encoded}/property/{properties}/JSON"
    )
    request = Request(url, headers={"User-Agent": "smiles_auto/2.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return {"error": "no_pubchem_record"}
        raise RuntimeError(f"PubChem lookup failed: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PubChem lookup failed: {type(exc).__name__}: {exc}") from exc

    rows = payload.get("PropertyTable", {}).get("Properties", [])
    if not rows:
        return {"error": "no_pubchem_record"}
    row = rows[0]
    return {
        "smiles": str(
            row.get("SMILES")
            or row.get("IsomericSMILES")
            or row.get("ConnectivitySMILES")
            or row.get("CanonicalSMILES")
            or ""
        ),
        "inchikey": str(row.get("InChIKey") or ""),
    }


def _candidate_from_smiles(
    kind: str,
    query: str,
    raw_smiles: str,
    *,
    inchikey: str = "",
    allow_fragments: bool,
    max_length: int,
) -> TextCandidate:
    validated = canonicalize_smiles(
        raw_smiles,
        allow_fragments=allow_fragments,
        max_length=max_length,
    )
    return TextCandidate(
        kind=kind,
        query=query,
        raw_smiles=raw_smiles,
        canonical_smiles=validated.canonical,
        inchikey=validated.inchikey or inchikey,
        rdkit_valid=validated.rdkit_valid,
        reason=validated.reason,
    )


def _text_queries(text: str, lookup_names: bool) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    queries.extend(("smiles", value) for value in SMILES_PATTERN.findall(text))
    queries.extend(("inchikey", value.upper()) for value in INCHIKEY_PATTERN.findall(text))
    queries.extend(("cid", value) for value in CID_PATTERN.findall(text))
    queries.extend(("cas", value) for value in CAS_PATTERN.findall(text))
    if lookup_names:
        lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        for line in lines:
            match = NAME_PATTERN.match(line)
            if match:
                queries.append(("name", match.group(1).strip()))
        if len(lines) == 1 and 2 <= len(lines[0]) <= 80 and re.search(r"[A-Za-z]", lines[0]):
            if not any(pattern.search(lines[0]) for pattern in (SMILES_PATTERN, CID_PATTERN, CAS_PATTERN, INCHIKEY_PATTERN)):
                queries.append(("name", lines[0]))

    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, value in queries:
        cleaned = value.strip().strip(".,;|")
        key = (kind, cleaned.casefold())
        if cleaned and key not in seen:
            seen.add(key)
            unique.append((kind, cleaned))
    return unique


def collect_text_candidates(
    ocr_text: str,
    *,
    lookup_names: bool,
    allow_fragments: bool,
    max_length: int,
    timeout: float,
) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    for kind, value in _text_queries(ocr_text, lookup_names):
        if kind == "smiles":
            candidates.append(
                _candidate_from_smiles(
                    kind,
                    value,
                    value,
                    allow_fragments=allow_fragments,
                    max_length=max_length,
                )
            )
            continue

        namespace = "cid" if kind == "cid" else "inchikey" if kind == "inchikey" else "name"
        result = _pubchem_property(namespace, value, timeout)
        if "error" in result:
            candidates.append(TextCandidate(kind=kind, query=value, reason=result["error"]))
            continue
        candidates.append(
            _candidate_from_smiles(
                kind,
                value,
                result.get("smiles", ""),
                inchikey=result.get("inchikey", ""),
                allow_fragments=allow_fragments,
                max_length=max_length,
            )
        )
    return candidates


def choose_text_result(candidates: list[TextCandidate]) -> tuple[TextCandidate | None, str]:
    valid = [candidate for candidate in candidates if candidate.rdkit_valid]
    if not valid:
        return None, "no_valid_text_candidate"
    canonical_values = {candidate.canonical_smiles for candidate in valid}
    if len(canonical_values) != 1:
        return None, "conflicting_text_candidates"
    priority = {"smiles": 0, "inchikey": 1, "cid": 2, "cas": 3, "name": 4}
    return min(valid, key=lambda item: priority.get(item.kind, 99)), "text_candidates_agree"


def lookup_image(
    image_id: str,
    image_path: Path,
    paths: TaskPaths,
    *,
    lookup_names: bool = True,
    allow_fragments: bool = False,
    max_length: int = 450,
    timeout: float = 20.0,
) -> LookupResult:
    ocr_text, tesseract_error = run_tesseract(image_path)
    candidates = [] if tesseract_error else collect_text_candidates(
        ocr_text,
        lookup_names=lookup_names,
        allow_fragments=allow_fragments,
        max_length=max_length,
        timeout=timeout,
    )
    chosen, reason = choose_text_result(candidates)
    result = LookupResult(
        image_id=image_id,
        ocr_text=ocr_text,
        tesseract_error=tesseract_error,
        chosen_smiles=chosen.canonical_smiles if chosen else "",
        chosen_inchikey=chosen.inchikey if chosen else "",
        recognition_method=f"text:{chosen.kind}" if chosen else "text:none",
        reason=reason,
        candidates=candidates,
    )
    evidence_path = paths.ocr_dir / f"{safe_component(image_id)}.json"
    write_workspace_json(paths, evidence_path, result.as_dict())
    append_event(
        paths,
        stage="text_lookup",
        status="error" if tesseract_error else "candidate" if chosen else "no_candidate",
        image_id=image_id,
        message=reason,
        data={"evidence": str(evidence_path), "candidate_count": len(candidates)},
    )
    if tesseract_error:
        raise RuntimeError(f"Tesseract failed for {image_id}: {tesseract_error}")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OCR/PubChem lookup inside an existing task workspace.")
    parser.add_argument("workspace_dir")
    parser.add_argument("--image-id")
    parser.add_argument("--no-name-lookup", action="store_true")
    parser.add_argument("--allow-fragments", action="store_true")
    parser.add_argument("--max-smiles-length", type=int, default=450)
    parser.add_argument("--timeout", type=float, default=20.0)
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

    found = 0
    for record in records:
        result = lookup_image(
            record.image_id,
            Path(record.source_image_path),
            paths,
            lookup_names=not args.no_name_lookup,
            allow_fragments=args.allow_fragments,
            max_length=args.max_smiles_length,
            timeout=args.timeout,
        )
        if result.chosen_smiles:
            record.smiles = result.chosen_smiles
            record.inchikey = result.chosen_inchikey
            record.rdkit_valid = "true"
            record.recognition_method = result.recognition_method
            record.status = "pending"
            record.confidence = "pending"
            record.source_match = "pending"
            add_note(record, result.reason)
            update_candidate(paths, record)
            found += 1
    print(f"text candidates found: {found}/{len(records)}")
    return 0 if found == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
