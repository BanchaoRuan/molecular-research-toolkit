#!/usr/bin/env python3

import argparse
import csv
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from make_com import build_state_specs, read_molecules_from_smi, read_state_selection


TASK_NAME = re.compile(r"^[0-9]{8}_[A-Za-z0-9][A-Za-z0-9_-]*$")
METHOD_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def build_header(state_options):
    states = [option["label"] for option in state_options]
    header = ["molecule_id", "smiles", "solvent"]
    header.extend(
        f"{state}_{field}"
        for state in states
        for field in ("charge", "multiplicity")
    )
    header.extend(f"G_{state}" for state in states)
    for field in ("status", "normal_terminations", "frequency_status"):
        header.extend(f"{state}_{field}" for state in states)
    return [*header, "overall_status"]


def extract_g298_from_text(text):
    matches = re.findall(
        r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)",
        text,
    )

    if not matches:
        return None

    return matches[-1]


def count_normal_terminations_from_text(text):
    return text.count("Normal termination")


def extract_final_frequencies_from_text(text):
    marker_index = text.rfind("Harmonic frequencies")
    frequency_section = text[marker_index:] if marker_index != -1 else text
    frequencies = []

    for match in re.finditer(
        r"^\s*Frequencies --\s+(.+)$", frequency_section, re.MULTILINE
    ):
        for value in match.group(1).split():
            try:
                frequencies.append(float(value))
            except ValueError:
                frequencies.append(math.nan)

    return frequencies


def first_five_frequency_status(frequencies):
    if not frequencies:
        return "no_frequencies"

    if len(frequencies) < 5:
        return "not_enough_frequencies"

    if any(not math.isfinite(value) or value <= 0 for value in frequencies[:5]):
        return "first5_not_positive"

    return "first5_positive"


def read_state_result(results_method_dir, molecule_id, state):
    log_file = results_method_dir / molecule_id / f"{state}.log"

    if not log_file.exists():
        return {
            "g298": "NA",
            "status": "missing_log",
            "normal_terminations": 0,
            "frequency_status": "missing_log",
        }

    if not log_file.is_file():
        raise ValueError(f"Expected a Gaussian log file but found another path type: {log_file}")

    text = log_file.read_text(encoding="utf-8", errors="ignore")
    g298 = extract_g298_from_text(text)
    normal_terminations = count_normal_terminations_from_text(text)
    frequencies = extract_final_frequencies_from_text(text)
    frequency_status = first_five_frequency_status(frequencies)

    if g298 is None:
        status = "no_G298"
        g298 = "NA"
    elif normal_terminations == 0:
        status = "not_terminated"
    elif frequency_status != "first5_positive":
        status = frequency_status
    else:
        status = "complete"

    return {
        "g298": g298,
        "status": status,
        "normal_terminations": normal_terminations,
        "frequency_status": frequency_status,
    }


def get_overall_status(state_results):
    if all(result["status"] == "complete" for result in state_results.values()):
        return "complete"

    return "needs_check"


def build_rows(molecules, results_method_dir, state_options):
    rows = []

    for molecule in molecules:
        molecule_id = molecule["molecule_id"]
        row = {
            "molecule_id": molecule_id,
            "smiles": molecule["smiles"],
            "solvent": molecule["solvent"],
        }
        state_results = {}
        for spec in build_state_specs(molecule["base_charge"], state_options):
            state = spec["state"]
            result = read_state_result(results_method_dir, molecule_id, state)
            state_results[state] = result
            row[f"{state}_charge"] = spec["charge"]
            row[f"{state}_multiplicity"] = spec["multiplicity"]
            row[f"G_{state}"] = result["g298"]
            for field in ("status", "normal_terminations", "frequency_status"):
                row[f"{state}_{field}"] = result[field]
        row["overall_status"] = get_overall_status(state_results)
        rows.append(row)

    return rows


def validate_method_inputs(calculation_method_dir, molecules, state_options):
    expected = {
        f"{option['label']}.{extension}"
        for option in state_options
        for extension in ("com", "slurm")
    }
    for molecule in molecules:
        work_dir = calculation_method_dir / "work" / molecule["molecule_id"]
        if work_dir.is_symlink() or not work_dir.is_dir():
            raise ValueError(f"Missing regular molecule work directory: {work_dir}")
        actual = {
            path.name
            for path in work_dir.iterdir()
            if path.suffix in {".com", ".slurm"}
        }
        if actual != expected:
            raise ValueError(f"Prepared inputs do not match the recorded state selection: {work_dir}")
        for name in expected:
            path = work_dir / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Prepared input must be a regular file: {path}")


def validate_output_paths(results_method_dir, molecules):
    paths_to_check = [
        results_method_dir.parent.parent,
        results_method_dir.parent,
        results_method_dir,
    ]

    for path in paths_to_check:
        if path.is_symlink():
            raise ValueError(f"Refusing to write through a symbolic link: {path}")
        if not path.is_dir():
            raise ValueError(
                "Prepared calculation method is missing a regular results directory: "
                f"{path}"
            )

    for molecule in molecules:
        result_dir = results_method_dir / molecule["molecule_id"]
        output_file = result_dir / "G298.tsv"

        if result_dir.is_symlink():
            raise ValueError(f"Refusing to write through a symbolic link: {result_dir}")
        if not result_dir.is_dir():
            raise ValueError(
                "Prepared results method is missing a regular molecule directory: "
                f"{result_dir}"
            )
        if output_file.is_symlink():
            raise ValueError(f"Refusing to overwrite a symbolic link: {output_file}")
        if output_file.exists() and not output_file.is_file():
            raise ValueError(f"Expected a TSV file but found another path type: {output_file}")


def write_rows(rows, results_method_dir, header):
    output_files = []

    for row in rows:
        result_dir = results_method_dir / row["molecule_id"]
        output_file = result_dir / "G298.tsv"

        with output_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=header,
                delimiter="\t",
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerow(row)

        output_files.append(output_file)

    return output_files


def build_manual_check_rows(rows, state_options):
    check_rows = []

    for row in rows:
        for option in state_options:
            state = option["label"]
            status = row[f"{state}_status"]

            if status != "complete":
                check_rows.append((row["molecule_id"], state, status))

    return check_rows


def print_terminal_summary(
    batch_input, calculation_method_dir, rows, output_files, state_options
):
    complete_count = sum(1 for row in rows if row["overall_status"] == "complete")
    needs_check_count = len(rows) - complete_count
    manual_check_rows = build_manual_check_rows(rows, state_options)
    states = [option["label"] for option in state_options]

    print(f"Batch input: {batch_input}")
    print(f"Calculation method: {calculation_method_dir}")
    print(f"Selected states: {', '.join(states)}")
    print(f"Number of molecules: {len(rows)}")
    print("")
    print("Quick status:")
    print(f"complete: {complete_count}")
    print(f"needs_check: {needs_check_count}")
    print("")
    print("Excel-ready G298:")
    summary_fields = ["molecule_id", *(f"G_{state}" for state in states), "overall_status"]
    print("\t".join(summary_fields))

    for row in rows:
        print("\t".join(str(row[field]) for field in summary_fields))

    print("")

    if manual_check_rows:
        print("Needs manual check:")
        print("molecule_id\tstate\treason")

        for molecule_id, state, reason in manual_check_rows:
            print(f"{molecule_id}\t{state}\t{reason}")
    else:
        print("No molecules need manual check.")

    print("")
    print("Overwritten per-molecule TSV files:")

    for output_file in output_files:
        print(output_file)

    if any(row[f"{state}_status"] == "no_G298" for row in rows for state in states):
        import shlex
        recovery = Path(__file__).resolve().with_name("recover_no_g298.py")
        print("")
        print("no_G298 is an observation, not proof of a failed or finished job.")
        print("Optional read-only recovery preview (nothing is submitted):")
        print(shlex.join(["python3", str(recovery), str(calculation_method_dir)]))


def resolve_method_paths(method_argument):
    script_dir = Path(__file__).resolve().parent
    base = script_dir.parent
    calculations_root = (base / "calculations").resolve(strict=True)
    supplied_method_dir = Path(method_argument)

    if supplied_method_dir.is_symlink():
        raise ValueError(
            f"Calculation method path cannot be a symbolic link: {supplied_method_dir}"
        )

    calculation_method_dir = supplied_method_dir.resolve(strict=True)

    if not calculation_method_dir.is_dir():
        raise ValueError(
            f"Calculation method path is not a directory: {calculation_method_dir}"
        )

    if calculation_method_dir.parent.parent != calculations_root:
        raise ValueError(
            "Calculation method directory must be exactly "
            f"{calculations_root}/YYYYMMDD_taskname/method_name"
        )

    method_parts = calculation_method_dir.name.split("__")

    if len(method_parts) != 3 or any(
        not METHOD_LABEL.fullmatch(part) for part in method_parts
    ):
        raise ValueError(
            "Calculation method directory name must contain exactly three safe "
            "labels: functional__basis_set__solvation_model"
        )

    task_dir = calculation_method_dir.parent
    task_name = task_dir.name

    if not TASK_NAME.fullmatch(task_name):
        raise ValueError(
            f"Calculation task directory must follow YYYYMMDD_taskname: {task_name}"
        )

    batch_input = task_dir / f"{task_name}.smi"

    if batch_input.is_symlink() or not batch_input.is_file():
        raise FileNotFoundError(f"Cannot find task batch input copy: {batch_input}")

    coordinates_dir = task_dir / "coordinates"
    coordinate_manifest = coordinates_dir / "manifest.json"

    if coordinates_dir.is_symlink() or not coordinates_dir.is_dir():
        raise ValueError(
            f"Task is missing its frozen coordinate directory: {coordinates_dir}"
        )

    if coordinate_manifest.is_symlink() or not coordinate_manifest.is_file():
        raise ValueError(
            f"Task is missing its coordinate manifest: {coordinate_manifest}"
        )

    required_directories = (
        calculation_method_dir / "work",
        calculation_method_dir / "logs",
        calculation_method_dir / "submit",
    )

    for required_directory in required_directories:
        if required_directory.is_symlink() or not required_directory.is_dir():
            raise ValueError(
                "Prepared calculation method is missing a regular directory: "
                f"{required_directory}"
            )

    required_files = (
        calculation_method_dir / "preparation.log",
        calculation_method_dir / "submit" / "submit.sh",
    )

    for required_file in required_files:
        if required_file.is_symlink() or not required_file.is_file():
            raise ValueError(
                "Prepared calculation method is missing a regular file: "
                f"{required_file}"
            )

    results_method_dir = base / "results" / task_name / calculation_method_dir.name
    return calculation_method_dir, batch_input, results_method_dir


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Extract the saved state selection for one prepared calculation method and "
            "overwrite every batch molecule's G298.tsv."
        )
    )
    parser.add_argument(
        "calculation_method_directory",
        help="calculations/YYYYMMDD_taskname/functional__basis_set__solvation_model",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    calculation_method_dir, batch_input, results_method_dir = resolve_method_paths(
        arguments.calculation_method_directory
    )
    molecules = read_molecules_from_smi(batch_input)
    state_options = read_state_selection(calculation_method_dir / "preparation.log")
    validate_method_inputs(calculation_method_dir, molecules, state_options)
    validate_output_paths(results_method_dir, molecules)
    rows = build_rows(molecules, results_method_dir, state_options)
    output_files = write_rows(rows, results_method_dir, build_header(state_options))
    print_terminal_summary(
        batch_input,
        calculation_method_dir,
        rows,
        output_files,
        state_options,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
