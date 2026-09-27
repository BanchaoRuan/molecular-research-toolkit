#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path


GEOMETRY_RECIPE = {
    "openbabel_module": "openbabel/3.1.1-gcc14.2.0",
    "initial_geometry": {
        "add_hydrogens": True,
        "generator": "gen3d",
    },
    "conformer_search": {
        "algorithm": "genetic_algorithm",
        "requested_conformers": 10,
        "score": "energy",
    },
    "minimization": {
        "forcefield": "UFF",
    },
    "ranking": {
        "forcefield": "UFF",
        "operation": "energy",
    },
}

STAGE_MARKER_NAME = ".coordinate-stage.json"
MANIFEST_NAME = "manifest.json"
STATE_SELECTION_PREFIX = "Selected state parameters: "
COORDINATE_FILENAMES = ("initial.xyz", "conformers.xyz", "lowest.xyz")
SAFE_MOLECULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_SOLVENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9,+._-]*$")
ELEMENT = re.compile(r"^[A-Z][a-z]?$|^Xx$")


def parse_charge_marker(marker):
    if marker[0] in "+-":
        sign = 1 if marker[0] == "+" else -1
        rest = marker[1:]

        if rest == "":
            return sign

        if all(char == marker[0] for char in marker):
            return sign * len(marker)

        if rest.isdigit():
            return sign * int(rest)

    if marker[-1] in "+-" and marker[:-1].isdigit():
        sign = 1 if marker[-1] == "+" else -1
        return sign * int(marker[:-1])

    raise ValueError(f"Cannot parse formal charge marker: {marker}")


def bracket_formal_charge(bracket_text):
    atom_part = bracket_text.split(":", 1)[0]

    match = re.search(r"([+-]\d+)$", atom_part)
    if match:
        return parse_charge_marker(match.group(1))

    match = re.search(r"(\d+[+-])$", atom_part)
    if match and not re.search(r"H\d+[+-]$", atom_part):
        return parse_charge_marker(match.group(1))

    match = re.search(r"([+-]{1,15})$", atom_part)
    if match:
        return parse_charge_marker(match.group(1))

    return 0


def formal_charge_from_smiles(smiles):
    charge = 0

    for bracket_text in re.findall(r"\[([^\]]+)\]", smiles):
        charge += bracket_formal_charge(bracket_text)

    return charge


def validate_state_options(options):
    if not isinstance(options, list) or not options:
        raise ValueError("State options must be a non-empty list")

    seen_labels = set()

    for option in options:
        if not isinstance(option, dict) or set(option) != {
            "label", "charge_offset", "multiplicity"
        }:
            raise ValueError(
                "Each state must contain exactly label, charge_offset, and multiplicity"
            )

        label = option["label"]
        if (
            not isinstance(label, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]*", label)
            or label == "overall"
        ):
            raise ValueError(f"Unsafe or reserved state label: {label!r}")
        if label in seen_labels:
            raise ValueError(f"Duplicate state label: {label}")
        seen_labels.add(label)

        if type(option["charge_offset"]) is not int:
            raise ValueError(f"State {label} charge_offset must be an integer")
        if type(option["multiplicity"]) is not int or option["multiplicity"] <= 0:
            raise ValueError(f"State {label} multiplicity must be a positive integer")

    return options


def read_state_selection(path):
    log_path = require_regular_file(path, "Preparation log")
    records = [
        line[len(STATE_SELECTION_PREFIX):]
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.startswith(STATE_SELECTION_PREFIX)
    ]
    if len(records) != 1:
        raise ValueError(f"Preparation log must contain exactly one state selection: {log_path}")
    return validate_state_options(
        json.loads(records[0], object_pairs_hook=reject_duplicate_keys)
    )


def build_state_specs(base_charge, state_options):
    return [
        {
            "state": option["label"],
            "charge": base_charge + option["charge_offset"],
            "multiplicity": option["multiplicity"],
        }
        for option in validate_state_options(state_options)
    ]


def read_molecules_from_smi(smi_file):
    smi_path = Path(smi_file)
    molecules = []
    seen_ids = set()

    for line_number, line in enumerate(
        smi_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        fields = stripped.split()

        if len(fields) != 3:
            raise ValueError(
                f"{smi_path} line {line_number} must contain exactly three columns: "
                "SMILES molecule_id solvent"
            )

        smiles, molecule_id, solvent = fields

        if not SAFE_MOLECULE_ID.fullmatch(molecule_id):
            raise ValueError(
                f"{smi_path} line {line_number} has unsafe molecule_id "
                f"'{molecule_id}'; use only letters, digits, underscores, and hyphens, "
                "starting with a letter or digit"
            )

        if not SAFE_SOLVENT.fullmatch(solvent):
            raise ValueError(
                f"{smi_path} line {line_number} has unsafe solvent '{solvent}'; "
                "use a single Gaussian solvent token without whitespace or route punctuation"
            )

        if molecule_id in seen_ids:
            raise ValueError(
                f"Duplicate molecule_id '{molecule_id}' at {smi_path} line {line_number}"
            )

        seen_ids.add(molecule_id)
        molecule = {
            "line_number": line_number,
            "smiles": smiles,
            "molecule_id": molecule_id,
            "solvent": solvent,
            "base_charge": formal_charge_from_smiles(smiles),
        }
        molecules.append(molecule)

    if not molecules:
        raise ValueError(f"Input file contains no molecule records: {smi_path}")

    return molecules


def expected_record_text(molecule):
    return (
        f"{molecule['smiles']}\t{molecule['molecule_id']}\t"
        f"{molecule['solvent']}\n"
    )


def read_molecule_record(record_file, molecule_id):
    molecules = read_molecules_from_smi(record_file)

    if len(molecules) != 1:
        raise ValueError(
            f"{record_file} must contain exactly one molecule record; "
            f"found {len(molecules)}"
        )

    molecule = molecules[0]

    if molecule["molecule_id"] != molecule_id:
        raise ValueError(
            f"Molecule ID mismatch: command requested '{molecule_id}' but "
            f"{record_file} contains '{molecule['molecule_id']}'"
        )

    return molecule


def extract_energy_from_title(title):
    numbers = re.findall(
        r"[-+]?\d*\.\d+(?:[Ee][-+]?\d+)?|[-+]?\d+(?:[Ee][-+]?\d+)?",
        title,
    )

    if not numbers:
        return None

    energy = float(numbers[-1])
    return energy if math.isfinite(energy) else None


def parse_xyz_blocks(xyz_file):
    xyz_path = Path(xyz_file)
    lines = xyz_path.read_text(encoding="utf-8").splitlines()
    blocks = []
    index = 0

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue

        try:
            atom_count = int(lines[index].strip())
        except ValueError as error:
            raise ValueError(
                f"Cannot read atom number at {xyz_path} line {index + 1}: "
                f"{lines[index]}"
            ) from error

        if atom_count <= 0:
            raise ValueError(
                f"Atom number must be positive at {xyz_path} line {index + 1}"
            )

        if index + 1 >= len(lines):
            raise ValueError(f"{xyz_path} ended before the XYZ title line")

        title = lines[index + 1].strip()
        geometry_start = index + 2
        geometry_end = geometry_start + atom_count

        if geometry_end > len(lines):
            raise ValueError(f"{xyz_path} ended before all atom coordinates were read")

        geometry = []
        elements = []

        for coordinate_line in lines[geometry_start:geometry_end]:
            fields = coordinate_line.split()

            if len(fields) < 4:
                raise ValueError(
                    f"Bad coordinate line in {xyz_path}: {coordinate_line}"
                )

            element = fields[0]

            if not ELEMENT.fullmatch(element):
                raise ValueError(
                    f"Unsupported element token in {xyz_path}: {element}"
                )

            try:
                x = float(fields[1])
                y = float(fields[2])
                z = float(fields[3])
            except ValueError as error:
                raise ValueError(
                    f"Non-numeric coordinate in {xyz_path}: {coordinate_line}"
                ) from error

            if not all(math.isfinite(value) for value in (x, y, z)):
                raise ValueError(
                    f"Non-finite coordinate in {xyz_path}: {coordinate_line}"
                )

            elements.append(element)
            geometry.append(f"{element:<2} {x:>14.5f} {y:>14.5f} {z:>14.5f}")

        blocks.append(
            {
                "index": len(blocks) + 1,
                "natom": atom_count,
                "title": title,
                "energy": extract_energy_from_title(title),
                "elements": elements,
                "geometry": geometry,
            }
        )
        index = geometry_end

    return blocks


def validate_consistent_blocks(blocks, context):
    if not blocks:
        raise ValueError(f"No XYZ blocks were found in {context}")

    atom_count = blocks[0]["natom"]
    elements = blocks[0]["elements"]

    for block in blocks[1:]:
        if block["natom"] != atom_count or block["elements"] != elements:
            raise ValueError(
                f"XYZ blocks in {context} do not have identical atom order"
            )


def choose_lowest_energy_block(blocks):
    validate_consistent_blocks(blocks, "conformer file")

    if any(block["energy"] is None for block in blocks):
        raise ValueError(
            "A finite energy was not found for every conformer. "
            "Inspect conformers.xyz before continuing."
        )

    return min(blocks, key=lambda block: block["energy"])


def write_selected_xyz(output_file, molecule_id, block):
    output_path = Path(output_file)
    lines = [
        str(block["natom"]),
        (
            f"{molecule_id} lowest conformer_index={block['index']} "
            f"energy={block['energy']}"
        ),
        *block["geometry"],
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def select_shared_geometry(conformers_file, lowest_file, molecule_id):
    blocks = parse_xyz_blocks(conformers_file)
    selected = choose_lowest_energy_block(blocks)
    write_selected_xyz(lowest_file, molecule_id, selected)
    print(f"Conformers found: {len(blocks)}")
    print(f"Selected conformer index: {selected['index']}")
    print(f"Selected conformer energy: {selected['energy']}")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def canonical_json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value

    return result


def read_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def write_json_atomic(path, value):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=True,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def require_regular_directory(path, description):
    directory = Path(path)

    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"{description} must be a regular directory: {directory}")

    return directory


def require_regular_file(path, description):
    file_path = Path(path)

    if file_path.is_symlink() or not file_path.is_file():
        raise ValueError(f"{description} must be a regular file: {file_path}")

    return file_path


def stage_marker(task_input):
    task_path = require_regular_file(task_input, "Task batch input")
    return {
        "batch_sha256": sha256_file(task_path),
        "recipe": GEOMETRY_RECIPE,
    }


def initialize_coordinate_stage(task_input, coordinates_dir):
    coordinates_path = require_regular_directory(
        coordinates_dir, "Coordinate staging directory"
    )

    if any(coordinates_path.iterdir()):
        raise ValueError(
            f"Coordinate staging directory must be empty: {coordinates_path}"
        )

    write_json_atomic(
        coordinates_path / STAGE_MARKER_NAME,
        stage_marker(task_input),
    )


def validate_coordinate_entry(coordinates_root, molecule):
    coordinates_path = Path(coordinates_root)
    molecule_id = molecule["molecule_id"]
    molecule_dir = require_regular_directory(
        coordinates_path / molecule_id,
        f"Coordinate directory for {molecule_id}",
    )
    expected_names = {f"{molecule_id}.smi", *COORDINATE_FILENAMES}
    actual_names = {path.name for path in molecule_dir.iterdir()}

    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        details = []

        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))

        raise ValueError(
            f"Coordinate directory for {molecule_id} has invalid contents: "
            + "; ".join(details)
        )

    record_file = require_regular_file(
        molecule_dir / f"{molecule_id}.smi", f"SMI record for {molecule_id}"
    )
    initial_file = require_regular_file(
        molecule_dir / "initial.xyz", f"Initial geometry for {molecule_id}"
    )
    conformers_file = require_regular_file(
        molecule_dir / "conformers.xyz", f"Conformers for {molecule_id}"
    )
    lowest_file = require_regular_file(
        molecule_dir / "lowest.xyz", f"Lowest geometry for {molecule_id}"
    )

    if record_file.read_text(encoding="utf-8") != expected_record_text(molecule):
        raise ValueError(
            f"SMI record does not match the task batch for molecule_id={molecule_id}"
        )

    initial_blocks = parse_xyz_blocks(initial_file)
    conformer_blocks = parse_xyz_blocks(conformers_file)
    lowest_blocks = parse_xyz_blocks(lowest_file)

    if len(initial_blocks) != 1:
        raise ValueError(
            f"initial.xyz for {molecule_id} must contain exactly one XYZ block"
        )

    if len(lowest_blocks) != 1:
        raise ValueError(
            f"lowest.xyz for {molecule_id} must contain exactly one XYZ block"
        )

    validate_consistent_blocks(conformer_blocks, conformers_file)
    selected = choose_lowest_energy_block(conformer_blocks)
    initial = initial_blocks[0]
    lowest = lowest_blocks[0]

    if (
        initial["natom"] != selected["natom"]
        or initial["elements"] != selected["elements"]
    ):
        raise ValueError(
            f"Initial and conformer atom order differs for molecule_id={molecule_id}"
        )

    if (
        lowest["natom"] != selected["natom"]
        or lowest["elements"] != selected["elements"]
        or lowest["geometry"] != selected["geometry"]
        or lowest["energy"] != selected["energy"]
    ):
        raise ValueError(
            f"lowest.xyz does not match the lowest ranked conformer for "
            f"molecule_id={molecule_id}"
        )

    file_records = {}

    for label, file_path in (
        ("smi", record_file),
        ("initial", initial_file),
        ("conformers", conformers_file),
        ("lowest", lowest_file),
    ):
        file_records[label] = {
            "path": str(file_path.relative_to(coordinates_path)),
            "sha256": sha256_file(file_path),
        }

    return {
        "molecule_id": molecule_id,
        "line_number": molecule["line_number"],
        "smiles_sha256": sha256_bytes(molecule["smiles"].encode("utf-8")),
        "files": file_records,
        "atom_count": selected["natom"],
        "conformer_count": len(conformer_blocks),
        "selected_index": selected["index"],
        "selected_energy": selected["energy"],
    }


def validate_stage_marker(task_input, coordinates_path):
    marker_path = require_regular_file(
        coordinates_path / STAGE_MARKER_NAME,
        "Coordinate staging marker",
    )
    marker = read_json(marker_path)
    expected = stage_marker(task_input)

    if marker != expected:
        raise ValueError(
            "Coordinate staging marker does not match the current task batch and recipe"
        )


def inspect_coordinate_stage(task_input, coordinates_dir):
    coordinates_path = require_regular_directory(
        coordinates_dir, "Coordinate staging directory"
    )
    manifest_path = coordinates_path / MANIFEST_NAME

    if manifest_path.exists() or manifest_path.is_symlink():
        verify_coordinate_snapshot(
            task_input,
            coordinates_path,
            allow_stage_marker=True,
            emit_message=False,
        )

        for molecule in read_molecules_from_smi(task_input):
            print(f"VALID\t{molecule['molecule_id']}")

        print("READY\t1")
        return

    validate_stage_marker(task_input, coordinates_path)
    molecules = read_molecules_from_smi(task_input)
    expected_names = {STAGE_MARKER_NAME}
    expected_names.update(molecule["molecule_id"] for molecule in molecules)
    actual_names = {path.name for path in coordinates_path.iterdir()}
    unexpected = sorted(actual_names - expected_names)

    if unexpected:
        raise ValueError(
            "Coordinate staging directory contains unexpected entries: "
            + ", ".join(unexpected)
        )

    for molecule in molecules:
        molecule_path = coordinates_path / molecule["molecule_id"]

        if molecule_path.exists() or molecule_path.is_symlink():
            validate_coordinate_entry(coordinates_path, molecule)
            print(f"VALID\t{molecule['molecule_id']}")
        else:
            print(f"MISSING\t{molecule['molecule_id']}")

    print("READY\t0")


def expected_complete_manifest(task_input, coordinates_dir):
    coordinates_path = require_regular_directory(
        coordinates_dir, "Coordinate snapshot directory"
    )
    task_path = require_regular_file(task_input, "Task batch input")
    molecules = read_molecules_from_smi(task_path)
    entries = [
        validate_coordinate_entry(coordinates_path, molecule)
        for molecule in molecules
    ]
    payload = {
        "batch_sha256": sha256_file(task_path),
        "recipe": GEOMETRY_RECIPE,
        "molecules": entries,
    }
    return {
        "status": "complete",
        **payload,
        "coordinate_set_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def build_coordinate_manifest(task_input, coordinates_dir):
    coordinates_path = require_regular_directory(
        coordinates_dir, "Coordinate staging directory"
    )
    marker_path = coordinates_path / STAGE_MARKER_NAME
    manifest_path = coordinates_path / MANIFEST_NAME

    if manifest_path.exists() or manifest_path.is_symlink():
        verify_coordinate_snapshot(
            task_input,
            coordinates_path,
            allow_stage_marker=True,
            emit_message=False,
        )
        marker_path.unlink(missing_ok=True)
        return

    validate_stage_marker(task_input, coordinates_path)
    molecules = read_molecules_from_smi(task_input)
    expected_names = {STAGE_MARKER_NAME}
    expected_names.update(molecule["molecule_id"] for molecule in molecules)
    actual_names = {path.name for path in coordinates_path.iterdir()}

    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        details = []

        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))

        raise ValueError(
            "Coordinate staging directory has invalid contents: "
            + "; ".join(details)
        )

    expected = expected_complete_manifest(task_input, coordinates_path)
    write_json_atomic(manifest_path, expected)
    marker_path.unlink()


def verify_coordinate_snapshot(
    task_input,
    coordinates_dir,
    *,
    allow_stage_marker=False,
    emit_message=True,
):
    coordinates_path = require_regular_directory(
        coordinates_dir, "Coordinate snapshot directory"
    )
    manifest_path = require_regular_file(
        coordinates_path / MANIFEST_NAME,
        "Coordinate manifest",
    )
    molecules = read_molecules_from_smi(task_input)
    expected_names = {MANIFEST_NAME}
    expected_names.update(molecule["molecule_id"] for molecule in molecules)

    if allow_stage_marker and (
        (coordinates_path / STAGE_MARKER_NAME).exists()
        or (coordinates_path / STAGE_MARKER_NAME).is_symlink()
    ):
        expected_names.add(STAGE_MARKER_NAME)

    actual_names = {path.name for path in coordinates_path.iterdir()}

    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        details = []

        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))

        raise ValueError(
            "Coordinate snapshot has invalid contents: " + "; ".join(details)
        )

    expected = expected_complete_manifest(task_input, coordinates_path)
    actual = read_json(manifest_path)

    if actual != expected:
        raise ValueError(
            "Coordinate manifest or frozen coordinate files do not match the "
            "current task batch and recipe"
        )

    if emit_message:
        print(f"Verified frozen coordinate snapshot: {len(molecules)} molecules")


def validate_route_value(name, value, *, allow_spaces):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} cannot be empty")

    if any(character in value for character in "\r\n\0"):
        raise ValueError(f"{name} cannot contain control characters")

    if not allow_spaces and (
        any(character.isspace() for character in value) or "/" in value
    ):
        raise ValueError(f"{name} must be a single Gaussian route token without '/'")


def validate_gaussian_memory(value):
    """Require an explicit positive, single-line Gaussian memory size and unit."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[1-9][0-9]*(?:KB|MB|GB|TB|KW|MW|GW|TW)", value, flags=re.IGNORECASE
    ):
        raise ValueError(
            "gaussian_memory must be a positive integer followed by KB, MB, GB, TB, "
            "KW, MW, GW, or TW, without spaces; for example 4000MW or 32GB"
        )
    return value.upper()


def write_com_files(
    molecule_id,
    preparation_log,
    record_file,
    geometry_file,
    output_work_dir,
    runtime_result_dir,
    functional,
    basis_set,
    solvation_route,
    route_keywords,
    cpu_cores,
    gaussian_memory,
):
    state_options = read_state_selection(preparation_log)
    if not SAFE_MOLECULE_ID.fullmatch(molecule_id):
        raise ValueError(
            f"Unsafe molecule_id '{molecule_id}'; use only letters, digits, "
            "underscores, and hyphens, starting with a letter or digit"
        )

    validate_route_value("functional", functional, allow_spaces=False)
    validate_route_value("basis set", basis_set, allow_spaces=False)
    validate_route_value("route keywords", route_keywords, allow_spaces=True)

    if solvation_route.count("{solvent}") != 1:
        raise ValueError("Solvation route must contain exactly one {solvent} placeholder")

    if any(character in solvation_route for character in "\r\n\0"):
        raise ValueError("Solvation route cannot contain control characters")

    if cpu_cores <= 0:
        raise ValueError("CPU cores must be a positive integer")

    gaussian_memory = validate_gaussian_memory(gaussian_memory)

    work_path = require_regular_directory(output_work_dir, "Output work directory")
    record_path = require_regular_file(record_file, "Molecule SMI record")
    geometry_path = require_regular_file(geometry_file, "Frozen lowest geometry")
    result_path = Path(runtime_result_dir).resolve()
    molecule = read_molecule_record(record_path, molecule_id)
    solvent = molecule["solvent"]
    resolved_solvation = solvation_route.replace("{solvent}", solvent)
    blocks = parse_xyz_blocks(geometry_path)

    if len(blocks) != 1:
        raise ValueError(
            f"Frozen lowest geometry must contain exactly one XYZ block: {geometry_path}"
        )

    selected = blocks[0]
    state_specs = build_state_specs(molecule["base_charge"], state_options)

    for state_spec in state_specs:
        state = state_spec["state"]
        charge = state_spec["charge"]
        multiplicity = state_spec["multiplicity"]
        checkpoint_path = result_path / f"{state}.chk"
        com_path = work_path / f"{state}.com"
        lines = [
            f"%nprocshared={cpu_cores}",
            f"%mem={gaussian_memory}",
            f"%chk={checkpoint_path}",
            f"#p {route_keywords} {functional}/{basis_set} {resolved_solvation}",
            "",
            (
                f"{molecule_id} {state} charge {charge} multiplicity {multiplicity} "
                f"{functional}/{basis_set}"
            ),
            "",
            f"{charge} {multiplicity}",
            *selected["geometry"],
            "",
            "",
        ]
        com_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"SMILES: {molecule['smiles']}")
    print(f"Solvent: {solvent}")
    print(f"Base charge from SMILES: {molecule['base_charge']}")

    for state_spec in state_specs:
        print(
            f"Generated Gaussian input: {state_spec['state']}.com "
            f"charge={state_spec['charge']} multiplicity={state_spec['multiplicity']}"
        )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Manage frozen Open Babel coordinates and create Gaussian input files."
        )
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    initialize_parser = subparsers.add_parser("initialize-coordinate-stage")
    initialize_parser.add_argument("--task-input", required=True)
    initialize_parser.add_argument("--coordinates-dir", required=True)

    inspect_parser = subparsers.add_parser("inspect-coordinate-stage")
    inspect_parser.add_argument("--task-input", required=True)
    inspect_parser.add_argument("--coordinates-dir", required=True)

    select_parser = subparsers.add_parser("select-geometry")
    select_parser.add_argument("--molecule-id", required=True)
    select_parser.add_argument("--conformers-file", required=True)
    select_parser.add_argument("--lowest-file", required=True)

    manifest_parser = subparsers.add_parser("build-coordinate-manifest")
    manifest_parser.add_argument("--task-input", required=True)
    manifest_parser.add_argument("--coordinates-dir", required=True)

    verify_parser = subparsers.add_parser("verify-coordinate-snapshot")
    verify_parser.add_argument("--task-input", required=True)
    verify_parser.add_argument("--coordinates-dir", required=True)

    inputs_parser = subparsers.add_parser("write-inputs")
    inputs_parser.add_argument("--preparation-log", required=True)
    inputs_parser.add_argument("--molecule-id", required=True)
    inputs_parser.add_argument("--record-file", required=True)
    inputs_parser.add_argument("--geometry-file", required=True)
    inputs_parser.add_argument("--output-work-dir", required=True)
    inputs_parser.add_argument("--runtime-result-dir", required=True)
    inputs_parser.add_argument("--functional", required=True)
    inputs_parser.add_argument("--basis-set", required=True)
    inputs_parser.add_argument("--solvation-route", required=True)
    inputs_parser.add_argument("--route-keywords", required=True)
    inputs_parser.add_argument("--cpu-cores", required=True, type=int)
    inputs_parser.add_argument("--gaussian-memory", required=True, type=validate_gaussian_memory)
    return parser.parse_args()


def main():
    arguments = parse_arguments()

    if arguments.action == "initialize-coordinate-stage":
        initialize_coordinate_stage(arguments.task_input, arguments.coordinates_dir)
    elif arguments.action == "inspect-coordinate-stage":
        inspect_coordinate_stage(arguments.task_input, arguments.coordinates_dir)
    elif arguments.action == "select-geometry":
        select_shared_geometry(
            arguments.conformers_file,
            arguments.lowest_file,
            arguments.molecule_id,
        )
    elif arguments.action == "build-coordinate-manifest":
        build_coordinate_manifest(arguments.task_input, arguments.coordinates_dir)
    elif arguments.action == "verify-coordinate-snapshot":
        verify_coordinate_snapshot(arguments.task_input, arguments.coordinates_dir)
    elif arguments.action == "write-inputs":
        write_com_files(
            molecule_id=arguments.molecule_id,
            preparation_log=arguments.preparation_log,
            record_file=arguments.record_file,
            geometry_file=arguments.geometry_file,
            output_work_dir=arguments.output_work_dir,
            runtime_result_dir=arguments.runtime_result_dir,
            functional=arguments.functional,
            basis_set=arguments.basis_set,
            solvation_route=arguments.solvation_route,
            route_keywords=arguments.route_keywords,
            cpu_cores=arguments.cpu_cores,
            gaussian_memory=arguments.gaussian_memory,
        )
    else:
        raise ValueError(f"Unsupported action: {arguments.action}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
