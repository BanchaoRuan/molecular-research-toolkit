#!/usr/bin/env python3
"""Read-only validation and installation guidance for smiles_auto."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import importlib.metadata
import json
import re
import subprocess
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


sys.dont_write_bytecode = True

DEPENDENCIES = json.loads((Path(__file__).resolve().parent.parent / "dependencies.json").read_text())
PYTHON_REQUIREMENT = DEPENDENCIES["python"]


@dataclass(frozen=True)
class PackageSpec:
    module: str
    label: str
    requirement: str


def declared_packages(group):
    lines = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text().splitlines()
    pins = {line.split("==", 1)[0].lower(): line.strip() for line in lines if "==" in line and not line.startswith("#")}
    return tuple(PackageSpec(p["module"], p["distribution"], pins[p["distribution"].lower()])
                 for p in DEPENDENCIES["packages"] if p["group"] == group)


CORE_PACKAGES = declared_packages("core")
MODEL_PACKAGES = declared_packages("models")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    python_compatible: bool
    missing_python: tuple[PackageSpec, ...]
    missing_system: tuple[str, ...]


def package_available(spec: PackageSpec) -> bool:
    try:
        from packaging.requirements import Requirement
        requirement = Requirement(spec.requirement)
        installed = importlib.metadata.version(requirement.name)
        available = (importlib.util.find_spec(spec.module) is not None
                     and requirement.specifier.contains(installed, prereleases=True))
        print(f"{'OK' if available else 'MISMATCH'}  {spec.label} {installed}; required {spec.requirement}")
        return available
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"MISSING  {spec.requirement}: {exc}")
        return False



def syntax_check(script_dir: Path) -> bool:
    ok = True
    for path in sorted(script_dir.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            print(f"OK       syntax {path.name}")
        except (OSError, SyntaxError) as exc:
            print(f"FAILED   syntax {path.name}: {exc}")
            ok = False
    return ok


def core_smoke() -> bool:
    try:
        from smiles_core import (
            FINAL_REPORT_FIELDS,
            CandidateRecord,
            candidate_fields,
            canonicalize_smiles,
            natural_sort_key,
        )

        result = canonicalize_smiles("CCO")
        record = CandidateRecord(image_id="1")
        record.validate()
        ordered = sorted(["10", "2", "1a"], key=natural_sort_key)
        fields = candidate_fields()
        if (
            not result.rdkit_valid
            or result.canonical != "CCO"
            or ordered != ["1a", "2", "10"]
            or len(fields) != 11
            or list(record.as_dict()) != fields
            or FINAL_REPORT_FIELDS
            != ["image_id", "smiles", "inchikey", "status", "confidence"]
        ):
            raise RuntimeError("unexpected core smoke-test result")
    except Exception as exc:
        print(f"FAILED   smiles_core smoke: {exc}")
        return False
    print("OK       smiles_core smoke")
    return True


def print_install_guidance(
    script_dir: Path,
    python_compatible: bool,
    missing_python: list[PackageSpec],
    missing_system: list[str],
) -> None:
    executable = shlex.quote(str(Path(sys.executable).resolve()))
    print("\nSTOP: smiles_auto environment validation failed.", file=sys.stderr)
    print(
        "Do not create a task workspace or bypass this check with an unrelated interpreter.",
        file=sys.stderr,
    )
    if not python_compatible:
        print(f"Python {PYTHON_REQUIREMENT} is required. Use the toolkit INSTALL.md, or select a compatible existing environment with the user.", file=sys.stderr)
    if missing_python:
        requirements = " ".join(shlex.quote(spec.requirement) for spec in missing_python)
        requirements_file = shlex.quote(str((script_dir.parent / "requirements.txt").resolve()))
        print("Install the missing Python packages into this same interpreter:", file=sys.stderr)
        print(f"  {executable} -m pip install {requirements}", file=sys.stderr)
        print("Or install the complete declared environment:", file=sys.stderr)
        print(f"  {executable} -m pip install -r {requirements_file}", file=sys.stderr)
    if "tesseract" in missing_system:
        print("Install the missing Tesseract command, then rerun validation:", file=sys.stderr)
        print("  Use the package manager documented for the current system.", file=sys.stderr)
    if python_compatible:
        print("Rerun with the same interpreter:", file=sys.stderr)
        print(f"  {executable} {shlex.quote(str((script_dir / 'validate_setup.py').resolve()))} --models", file=sys.stderr)
    print("Proceed only after that command exits with status 0.", file=sys.stderr)


def run_validation(*, check_models: bool) -> ValidationResult:
    """Validate without downloads or writes and return a machine-readable result."""

    script_dir = Path(__file__).resolve().parent
    print(f"python   {sys.version.split()[0]}")
    print(f"executable {Path(sys.executable).resolve()}")
    try:
        from packaging.specifiers import SpecifierSet
        python_compatible = SpecifierSet(PYTHON_REQUIREMENT).contains(sys.version.split()[0])
    except ImportError:
        python_compatible = False
    print(
        f"{'OK' if python_compatible else 'MISMATCH'}  "
        f"Python {PYTHON_REQUIREMENT} required"
    )
    ok = syntax_check(script_dir) and python_compatible
    missing_python: list[PackageSpec] = []
    packages = CORE_PACKAGES + (MODEL_PACKAGES if check_models else ())
    for spec in packages:
        if not package_available(spec):
            missing_python.append(spec)
            ok = False

    missing_system: list[str] = []
    tesseract = shutil.which("tesseract")
    try:
        if not tesseract:
            raise ValueError("command not found")
        from packaging.specifiers import SpecifierSet
        result = subprocess.run([tesseract, "--version"], capture_output=True, text=True, timeout=15, check=True)
        version = re.search(r"tesseract\s+(\d+\.\d+(?:\.\d+)?)", result.stdout + result.stderr).group(1)
        if not SpecifierSet(DEPENDENCIES["system"]["tesseract"]).contains(version):
            raise ValueError(f"version {version} does not satisfy {DEPENDENCIES['system']['tesseract']}")
        print(f"OK       tesseract {version}: {tesseract}")
    except Exception as exc:
        print(f"MISSING/MISMATCH tesseract: {exc}")
        missing_system.append("tesseract")
        ok = False

    if not any(spec.module == "rdkit" for spec in missing_python):
        ok = core_smoke() and ok

    if not ok:
        print_install_guidance(
            script_dir,
            python_compatible,
            missing_python,
            missing_system,
        )
    else:
        print("READY    smiles_auto environment is complete")
    return ValidationResult(
        ok=ok,
        python_compatible=python_compatible,
        missing_python=tuple(missing_python),
        missing_system=tuple(missing_system),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate smiles_auto without downloading models.")
    parser.add_argument(
        "--models",
        action="store_true",
        help="Check every package required by the full OCR/OCSR workflow without importing models.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_validation(check_models=args.models)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
