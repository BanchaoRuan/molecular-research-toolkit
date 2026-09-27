#!/usr/bin/env python3
"""Check molecule-image-prep dependencies without installing packages or writing files."""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.metadata
import io
import json
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True

DEPENDENCIES = json.loads((Path(__file__).resolve().parent.parent / "dependencies.json").read_text())
PACKAGES = tuple((p["module"], p["distribution"]) for p in DEPENDENCIES["packages"])



def run_validation() -> bool:
    scripts = Path(__file__).resolve().parent
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {Path(sys.executable).resolve()}")
    try:
        from packaging.specifiers import SpecifierSet
        ok = SpecifierSet(DEPENDENCIES["python"]).contains(sys.version.split()[0])
    except ImportError:
        ok = False
    pins = {line.split("==")[0].lower(): line for line in (scripts.parent / "requirements.txt").read_text().splitlines() if "==" in line and not line.startswith("#")}
    if not ok:
        print(f"FAILED: Python {DEPENDENCIES['python']} and packaging are required.")
    for path in sorted(scripts.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            print(f"OK syntax: {path.name}")
        except (OSError, SyntaxError) as exc:
            print(f"FAILED syntax: {path.name}: {exc}")
            ok = False
    packages_ok = True
    for module, distribution in PACKAGES:
        try:
            importlib.import_module(module)
            from packaging.requirements import Requirement
            requirement = Requirement(pins[distribution.lower()])
            version = importlib.metadata.version(distribution)
            if not requirement.specifier.contains(version, prereleases=True):
                raise ValueError(f"installed {version}; required {requirement}")
            print(f"OK dependency: {distribution} {version}; required {requirement}")
        except Exception as exc:
            print(f"FAILED dependency: {distribution}: {exc}")
            packages_ok = False
    if packages_ok:
        try:
            from PIL import Image, ImageFont
            from openpyxl import Workbook
            from prepare_images_core import natural_sort_key

            buffer = io.BytesIO()
            Image.new("RGB", (8, 6), "white").save(buffer, format="PNG")
            buffer.seek(0)
            with Image.open(buffer) as image:
                image.load()
                if image.size != (8, 6):
                    raise ValueError("PNG round-trip failed")
            ImageFont.load_default(size=16).getbbox("IMG001")
            workbook = Workbook()
            workbook.active.append(["image_id", "IMG001"])
            if workbook.active["B1"].value != "IMG001":
                raise ValueError("workbook cell check failed")
            workbook.close()
            if sorted(["IMG010", "IMG002"], key=natural_sort_key) != ["IMG002", "IMG010"]:
                raise ValueError("natural ordering check failed")
            print("OK in-memory checks: PNG, overview font, workbook cells, ID ordering")
        except Exception as exc:
            print(f"FAILED in-memory checks: {exc}")
            ok = False
    ok = ok and packages_ok
    if ok:
        print("READY molecule-image-prep")
    else:
        executable = shlex.quote(str(Path(sys.executable).resolve()))
        requirements = shlex.quote(str(scripts.parent / "requirements.txt"))
        print("STOP: resolve the environment through the parent skill's installation process.",
              file=sys.stderr)
        if not packages_ok:
            print("If dependency installation is authorized, use this same interpreter:",
                  file=sys.stderr)
            print(f"  {executable} -m pip install -r {requirements}", file=sys.stderr)
        print("Rerun this check with the task interpreter before initializing a task.",
              file=sys.stderr)
    return ok


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Check Python, dependencies, syntax, and in-memory operations; no files are written."
    ).parse_args(argv)
    return 0 if run_validation() else 1


if __name__ == "__main__":
    raise SystemExit(main())
