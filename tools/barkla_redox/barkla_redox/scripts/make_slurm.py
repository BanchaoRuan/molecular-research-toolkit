#!/usr/bin/env python3

import argparse
import re
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from make_com import read_state_selection


SAFE_MOLECULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_METHOD_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_PARTITION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_,.-]*$")
SAFE_WALLTIME = re.compile(
    r"^[0-9]+-(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"
)


def validate_positive_integer(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def validate_method_label(name, value):
    if not SAFE_METHOD_LABEL.fullmatch(value) or "__" in value:
        raise ValueError(
            f"Unsafe {name} label '{value}'; use letters, digits, underscores, and "
            "hyphens without a double underscore"
        )


def write_slurm_files(
    molecule_id,
    preparation_log,
    output_work_dir,
    runtime_work_dir,
    runtime_result_dir,
    runtime_logs_dir,
    functional_label,
    basis_set_label,
    solvation_model_label,
    nodes,
    ntasks,
    cpu_cores,
    partition,
    walltime,
):
    states = [option["label"] for option in read_state_selection(preparation_log)]
    if not SAFE_MOLECULE_ID.fullmatch(molecule_id):
        raise ValueError(
            f"Unsafe molecule_id '{molecule_id}'; use only letters, digits, "
            "underscores, and hyphens, starting with a letter or digit"
        )

    validate_method_label("functional", functional_label)
    validate_method_label("basis set", basis_set_label)
    validate_method_label("solvation model", solvation_model_label)
    validate_positive_integer("nodes", nodes)
    validate_positive_integer("ntasks", ntasks)
    validate_positive_integer("CPU cores", cpu_cores)

    if not SAFE_PARTITION.fullmatch(partition):
        raise ValueError(f"Unsafe Slurm partition value: {partition}")

    if not SAFE_WALLTIME.fullmatch(walltime):
        raise ValueError(
            f"Walltime must use Slurm D-HH:MM:SS syntax; received: {walltime}"
        )

    supplied_output_work_path = Path(output_work_dir)

    if supplied_output_work_path.is_symlink() or not supplied_output_work_path.is_dir():
        raise ValueError(
            "Output work directory must be a regular directory: "
            f"{supplied_output_work_path}"
        )

    output_work_path = supplied_output_work_path.resolve(strict=True)

    runtime_work_path = Path(runtime_work_dir).resolve(strict=False)
    runtime_result_path = Path(runtime_result_dir).resolve(strict=False)
    runtime_logs_path = Path(runtime_logs_dir).resolve(strict=False)

    for state in states:
        com_path = output_work_path / f"{state}.com"

        if not com_path.is_file():
            raise FileNotFoundError(f"Cannot find Gaussian input file: {com_path}")

    for state in states:
        com_file = f"{state}.com"
        log_file = runtime_result_path / f"{state}.log"
        slurm_file = output_work_path / f"{state}.slurm"
        job_name = (
            f"{molecule_id}_{state}_{functional_label}_"
            f"{basis_set_label}_{solvation_model_label}"
        )
        lines = [
            "#!/bin/bash -l",
            f"#SBATCH -J {job_name}",
            f"#SBATCH -o {runtime_logs_path / (job_name + '-%j.out')}",
            f"#SBATCH -e {runtime_logs_path / (job_name + '-%j.err')}",
            f"#SBATCH -D {runtime_work_path}",
            f"#SBATCH -N {nodes}",
            f"#SBATCH -p {partition}",
            f"#SBATCH --ntasks={ntasks}",
            f"#SBATCH --cpus-per-task={cpu_cores}",
            f"#SBATCH -t {walltime}",
            "",
            "set -euo pipefail",
            ': "${SLURM_CPUS_PER_TASK:?Slurm did not set SLURM_CPUS_PER_TASK}"',
            ': "${USER:?Slurm did not set USER}"',
            ': "${SLURM_JOB_ID:?Slurm did not set SLURM_JOB_ID}"',
            "",
            "set +e",
            "set +u",
            "set +o pipefail",
            "module load gaussian/16",
            "redox_module_status=$?",
            "set -euo pipefail",
            'if [ "$redox_module_status" -ne 0 ]; then',
            (
                '    echo "Error: module load gaussian/16 failed with exit code '
                '$redox_module_status" >&2'
            ),
            '    exit "$redox_module_status"',
            "fi",
            ': "${g16root:?gaussian/16 did not set g16root}"',
            'readonly REDOX_G16_PROFILE="$g16root/g16/bsd/g16.profile"',
            'if [ ! -r "$REDOX_G16_PROFILE" ]; then',
            '    echo "Error: Gaussian profile is not readable: $REDOX_G16_PROFILE" >&2',
            "    exit 1",
            "fi",
            'export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"',
            "",
            'readonly REDOX_SCRATCH_DIR="/tmp/${USER}/${SLURM_JOB_ID}"',
            'export GAUSS_SCRDIR="$REDOX_SCRATCH_DIR"',
            "",
            'mkdir -p "$GAUSS_SCRDIR"',
            "",
            "cleanup_scratch() {",
            "    local exit_status=$?",
            '    rm -rf -- "$REDOX_SCRATCH_DIR" || true',
            '    exit "$exit_status"',
            "}",
            "trap cleanup_scratch EXIT",
            "",
            "set +e",
            "set +u",
            "set +o pipefail",
            '. "$REDOX_G16_PROFILE"',
            "redox_profile_status=$?",
            "set -euo pipefail",
            'export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"',
            'export GAUSS_SCRDIR="$REDOX_SCRATCH_DIR"',
            "",
            "if ! command -v g16 >/dev/null 2>&1; then",
            '    if [ "$redox_profile_status" -ne 0 ]; then',
            (
                '        echo "Error: Gaussian profile returned exit code '
                '$redox_profile_status and g16 was not found" >&2'
            ),
            '        exit "$redox_profile_status"',
            "    fi",
            '    echo "Error: g16 was not found after loading gaussian/16 profile" >&2',
            "    exit 1",
            "fi",
            'if [ "$redox_profile_status" -ne 0 ]; then',
            (
                '    echo "Warning: Gaussian profile returned exit code '
                '$redox_profile_status, but g16 is available; continuing" >&2'
            ),
            "fi",
            "",
            f"g16 < {shlex.quote(com_file)} > {shlex.quote(str(log_file))}",
            "",
        ]
        slurm_file.write_text("\n".join(lines), encoding="utf-8")
        slurm_file.chmod(0o755)
        print(f"Generated Slurm script: {slurm_file.name}")



SUBMIT_HEADER = r'''#!/bin/bash
set -euo pipefail

METHOD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SUBMISSION_LOG="$METHOD_DIR/submit/submitted.tsv"
SUBMISSION_LOCK="$METHOD_DIR/submit/.submission.lock"
EXPECTED_JOBS={job_count}

MOLECULE_IDS=()
STATES=()
SLURM_PATHS=()

add_job() {
    MOLECULE_IDS+=("$1")
    STATES+=("$2")
    SLURM_PATHS+=("$3")
}
'''

SUBMIT_TAIL = r'''
if [ "${#MOLECULE_IDS[@]}" -ne "$EXPECTED_JOBS" ] \
    || [ "${#STATES[@]}" -ne "$EXPECTED_JOBS" ] \
    || [ "${#SLURM_PATHS[@]}" -ne "$EXPECTED_JOBS" ]; then
    echo "Error: submit script job arrays do not contain the expected $EXPECTED_JOBS entries" >&2
    exit 1
fi

if ! command -v sbatch >/dev/null 2>&1; then
    echo "Error: sbatch is not available in the current environment" >&2
    exit 1
fi

for ((INDEX = 0; INDEX < EXPECTED_JOBS; INDEX++)); do
    if [ ! -f "${SLURM_PATHS[$INDEX]}" ]; then
        echo "Error: cannot find Slurm file: ${SLURM_PATHS[$INDEX]}" >&2
        exit 1
    fi
done

if ! mkdir "$SUBMISSION_LOCK" 2>/dev/null; then
    echo "Error: another submission is active for this method: $SUBMISSION_LOCK" >&2
    exit 1
fi

SUBMISSION_LOCK_HELD=1
SUBMIT_TEMP_DIR=""

# shellcheck disable=SC2329  # Invoked by the EXIT trap below.
cleanup_submission() {
    local exit_status=$?

    if [ -n "$SUBMIT_TEMP_DIR" ] && [ -d "$SUBMIT_TEMP_DIR" ]; then
        rm -rf -- "$SUBMIT_TEMP_DIR" || true
    fi

    if [ "${SUBMISSION_LOCK_HELD:-0}" -eq 1 ]; then
        rmdir "$SUBMISSION_LOCK" 2>/dev/null || true
    fi

    exit "$exit_status"
}

trap cleanup_submission EXIT

if [ -L "$SUBMISSION_LOG" ] \
    || { [ -e "$SUBMISSION_LOG" ] && [ ! -f "$SUBMISSION_LOG" ]; }; then
    echo "Error: submission log path is not a regular file: $SUBMISSION_LOG" >&2
    exit 1
fi

if [ -s "$SUBMISSION_LOG" ]; then
    echo "Error: refusing to repeat a submission recorded in: $SUBMISSION_LOG" >&2
    exit 1
fi

SUBMIT_TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/redox-submit.XXXXXX")"
SBATCH_STDOUT_FILE="$SUBMIT_TEMP_DIR/sbatch.stdout"
SBATCH_STDERR_FILE="$SUBMIT_TEMP_DIR/sbatch.stderr"

printf 'molecule_id\tstate\tslurm_path\tjob_id\n' > "$SUBMISSION_LOG"

FAILED_IDS=()
FAILED_STATES=()
FAILED_PATHS=()
FAILED_CODES=()
FAILED_DIAGNOSTICS=()
SUCCESS_COUNT=0

for ((INDEX = 0; INDEX < EXPECTED_JOBS; INDEX++)); do
    MOLECULE_ID="${MOLECULE_IDS[$INDEX]}"
    STATE="${STATES[$INDEX]}"
    SLURM_PATH="${SLURM_PATHS[$INDEX]}"
    : > "$SBATCH_STDOUT_FILE"
    : > "$SBATCH_STDERR_FILE"

    printf '[%d/%d] Submitting molecule_id=%s state=%s\n' \
        "$((INDEX + 1))" "$EXPECTED_JOBS" "$MOLECULE_ID" "$STATE"

    if sbatch --parsable "$SLURM_PATH" > "$SBATCH_STDOUT_FILE" 2> "$SBATCH_STDERR_FILE"; then
        SUBMISSION_STATUS=0
    else
        SUBMISSION_STATUS=$?
    fi

    JOB_ID="$(<"$SBATCH_STDOUT_FILE")"

    if [ "$SUBMISSION_STATUS" -eq 0 ] \
        && [ -n "$JOB_ID" ] \
        && [[ "$JOB_ID" != *$'\n'* ]] \
        && [[ "$JOB_ID" != *$'\r'* ]] \
        && [[ "$JOB_ID" != *$'\t'* ]]; then
        printf '%s\t%s\t%s\t%s\n' \
            "$MOLECULE_ID" "$STATE" "$SLURM_PATH" "$JOB_ID" >> "$SUBMISSION_LOG"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        continue
    fi

    if [ "$SUBMISSION_STATUS" -eq 0 ]; then
        SUBMISSION_STATUS=1
    fi

    DIAGNOSTIC="$(<"$SBATCH_STDERR_FILE")"
    SBATCH_STDOUT="$(<"$SBATCH_STDOUT_FILE")"

    if [ -n "$SBATCH_STDOUT" ]; then
        if [ -n "$DIAGNOSTIC" ]; then
            DIAGNOSTIC+=$'\n'
        fi
        DIAGNOSTIC+="sbatch stdout: $SBATCH_STDOUT"
    fi

    if [ -z "$DIAGNOSTIC" ]; then
        DIAGNOSTIC="sbatch returned no diagnostic text"
    fi

    FAILED_IDS+=("$MOLECULE_ID")
    FAILED_STATES+=("$STATE")
    FAILED_PATHS+=("$SLURM_PATH")
    FAILED_CODES+=("$SUBMISSION_STATUS")
    FAILED_DIAGNOSTICS+=("$DIAGNOSTIC")
done

FAILURE_COUNT="${#FAILED_IDS[@]}"

echo ""
echo "Batch submission finished"
echo "Total jobs attempted: $EXPECTED_JOBS"
echo "Successfully submitted: $SUCCESS_COUNT"
echo "Failed submissions: $FAILURE_COUNT"
echo "Successful submission records: $SUBMISSION_LOG"

if [ "$FAILURE_COUNT" -ne 0 ]; then
    echo ""
    echo "Failed jobs (reported after all jobs were attempted):"

    for ((INDEX = 0; INDEX < FAILURE_COUNT; INDEX++)); do
        printf '%d) molecule_id=%s state=%s exit_code=%s\n' \
            "$((INDEX + 1))" \
            "${FAILED_IDS[$INDEX]}" \
            "${FAILED_STATES[$INDEX]}" \
            "${FAILED_CODES[$INDEX]}"
        echo "   Slurm file: ${FAILED_PATHS[$INDEX]}"
        echo "   Diagnostic:"

        while IFS= read -r DIAGNOSTIC_LINE || [ -n "$DIAGNOSTIC_LINE" ]; do
            printf '     %s\n' "$DIAGNOSTIC_LINE"
        done <<< "${FAILED_DIAGNOSTICS[$INDEX]}"
    done

    exit 1
fi

exit 0'''


def write_submit_script(output_path, molecule_ids, states):
    """Use the same locked, single-submission workflow for every prepared batch."""
    if not molecule_ids or not states:
        raise ValueError("Submission requires at least one molecule and one state")
    if len(set(molecule_ids)) != len(molecule_ids) or len(set(states)) != len(states):
        raise ValueError("Duplicate molecules or states in submission plan")
    if any(not SAFE_MOLECULE_ID.fullmatch(v) for v in [*molecule_ids, *states]):
        raise ValueError("Unsafe molecule or state label in submission plan")
    job_count = len(molecule_ids) * len(states)
    header = SUBMIT_HEADER.replace("{job_count}", str(job_count))
    jobs = [
        f'add_job {molecule_id} {state} "$METHOD_DIR/work/{molecule_id}/{state}.slurm"'
        for molecule_id in molecule_ids for state in states
    ]
    tail = SUBMIT_TAIL
    output = Path(output_path)
    output.write_text(header + "\n\n" + "\n".join(jobs) + "\n" + tail + "\n",
                      encoding="utf-8")
    output.chmod(0o755)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Create Barkla Slurm scripts for the saved state selection."
    )
    parser.add_argument("--preparation-log", required=True)
    parser.add_argument("--molecule-id", required=True)
    parser.add_argument("--output-work-dir", required=True)
    parser.add_argument("--runtime-work-dir", required=True)
    parser.add_argument("--runtime-result-dir", required=True)
    parser.add_argument("--runtime-logs-dir", required=True)
    parser.add_argument("--functional-label", required=True)
    parser.add_argument("--basis-set-label", required=True)
    parser.add_argument("--solvation-model-label", required=True)
    parser.add_argument("--nodes", required=True, type=int)
    parser.add_argument("--ntasks", required=True, type=int)
    parser.add_argument("--cpu-cores", required=True, type=int)
    parser.add_argument("--partition", required=True)
    parser.add_argument("--walltime", required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    write_slurm_files(
        molecule_id=arguments.molecule_id,
        preparation_log=arguments.preparation_log,
        output_work_dir=arguments.output_work_dir,
        runtime_work_dir=arguments.runtime_work_dir,
        runtime_result_dir=arguments.runtime_result_dir,
        runtime_logs_dir=arguments.runtime_logs_dir,
        functional_label=arguments.functional_label,
        basis_set_label=arguments.basis_set_label,
        solvation_model_label=arguments.solvation_model_label,
        nodes=arguments.nodes,
        ntasks=arguments.ntasks,
        cpu_cores=arguments.cpu_cores,
        partition=arguments.partition,
        walltime=arguments.walltime,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
