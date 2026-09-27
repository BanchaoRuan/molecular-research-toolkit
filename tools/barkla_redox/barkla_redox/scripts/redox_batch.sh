#!/bin/bash

set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$BASE/redox_customization.json"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required but is not available in the current environment" >&2
    exit 1
fi

if [ "$#" -ne 1 ]; then
    echo "Usage: bash scripts/redox_batch.sh inputs/YYYYMMDD_taskname.smi" >&2
    echo "Calculation choices are read from redox_customization.json." >&2
    exit 1
fi

SMI_ARGUMENT="$1"

if [ ! -f "$SMI_ARGUMENT" ]; then
    echo "Error: cannot find input file: $SMI_ARGUMENT" >&2
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: cannot find customization file: $CONFIG_FILE" >&2
    exit 1
fi

if ! SMI_FILE="$(python3 - "$SMI_ARGUMENT" <<'PY'
import sys
from pathlib import Path

try:
    print(Path(sys.argv[1]).resolve(strict=True))
except OSError as error:
    print(f"Error: cannot resolve input file: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
)"; then
    exit 1
fi

INPUT_BASE="$(basename "$SMI_FILE")"

if [[ ! "$INPUT_BASE" =~ ^[0-9]{8}_[A-Za-z0-9][A-Za-z0-9_-]*\.smi$ ]]; then
    echo "Error: input .smi filename must follow YYYYMMDD_taskname.smi" >&2
    echo "Example: 20260722_photocatalysts.smi" >&2
    exit 1
fi

if ! python3 - "$INPUT_BASE" <<'PY'
import datetime
import sys

date_text = sys.argv[1][:8]

try:
    datetime.datetime.strptime(date_text, "%Y%m%d")
except ValueError:
    print(f"Error: input filename contains an invalid calendar date: {date_text}", file=sys.stderr)
    raise SystemExit(1)
PY
then
    exit 1
fi

if ! CONFIG_ROWS="$(python3 - "$CONFIG_FILE" "$SCRIPT_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])

from make_com import validate_gaussian_memory, validate_state_options


EXPECTED_ROOT_KEYS = {
    "state_options",
    "functional_options",
    "basis_set_options",
    "solvation_model_options",
    "walltime_options",
    "route_keywords",
    "cpu_cores",
    "gaussian_memory",
    "nodes",
    "ntasks",
    "partition",
}
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_PARTITION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_,.-]*$")
SAFE_WALLTIME = re.compile(r"^[0-9]+-(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$")


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value

    return result


def has_control_characters(value):
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def require_text(name, value, *, allow_spaces=True):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")

    if has_control_characters(value):
        raise ValueError(f"{name} cannot contain control characters")

    if not allow_spaces and (any(character.isspace() for character in value) or "/" in value):
        raise ValueError(f"{name} must be one Gaussian route token without '/'")


def require_label(name, value):
    require_text(name, value, allow_spaces=False)

    if not SAFE_LABEL.fullmatch(value) or "__" in value:
        raise ValueError(
            f"{name} must use letters, digits, underscores, and hyphens, "
            "start with a letter or digit, and not contain '__'"
        )


def validate_options(config, key, value_key, record_type, value_validator):
    options = config[key]

    if not isinstance(options, list) or not options:
        raise ValueError(f"{key} must be a non-empty list")

    seen_labels = set()
    seen_values = set()
    rows = []

    for index, option in enumerate(options, start=1):
        if not isinstance(option, dict):
            raise ValueError(f"{key}[{index}] must be a JSON object")

        expected_keys = {"label", value_key}
        actual_keys = set(option)

        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            unknown = sorted(actual_keys - expected_keys)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unknown:
                details.append("unknown " + ", ".join(unknown))
            raise ValueError(f"{key}[{index}] has invalid fields: {'; '.join(details)}")

        label = option["label"]
        value = option[value_key]
        require_label(f"{key}[{index}].label", label)
        value_validator(f"{key}[{index}].{value_key}", value)
        label_key = label.casefold()
        value_key_folded = value.casefold()

        if label_key in seen_labels:
            raise ValueError(f"{key} contains duplicate label: {label}")
        if value_key_folded in seen_values:
            raise ValueError(f"{key} contains duplicate {value_key}: {value}")

        seen_labels.add(label_key)
        seen_values.add(value_key_folded)
        rows.append((record_type, label, value))

    return rows


def validate_route(name, value):
    require_text(name, value)

    if value.count("{solvent}") != 1:
        raise ValueError(f"{name} must contain exactly one {{solvent}} placeholder")


def validate_walltime(name, value):
    require_text(name, value, allow_spaces=False)

    if not SAFE_WALLTIME.fullmatch(value):
        raise ValueError(f"{name} must use Slurm D-HH:MM:SS syntax")


def require_positive_integer(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


try:
    config_path = Path(sys.argv[1])
    config = json.loads(
        config_path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )

    if not isinstance(config, dict):
        raise ValueError("configuration root must be a JSON object")

    actual_root_keys = set(config)
    if actual_root_keys != EXPECTED_ROOT_KEYS:
        missing = sorted(EXPECTED_ROOT_KEYS - actual_root_keys)
        unknown = sorted(actual_root_keys - EXPECTED_ROOT_KEYS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ValueError("configuration has invalid fields: " + "; ".join(details))

    rows = [
        ("STATE", option["label"], json.dumps(option, separators=(",", ":")))
        for option in validate_state_options(config["state_options"])
    ]
    rows.extend(
        validate_options(
            config,
            "functional_options",
            "value",
            "FUNCTIONAL",
            lambda name, value: require_text(name, value, allow_spaces=False),
        )
    )
    rows.extend(
        validate_options(
            config,
            "basis_set_options",
            "value",
            "BASIS_SET",
            lambda name, value: require_text(name, value, allow_spaces=False),
        )
    )
    rows.extend(
        validate_options(
            config,
            "solvation_model_options",
            "route",
            "SOLVATION_MODEL",
            validate_route,
        )
    )
    rows.extend(
        validate_options(
            config,
            "walltime_options",
            "value",
            "WALLTIME",
            validate_walltime,
        )
    )

    require_text("route_keywords", config["route_keywords"])
    require_positive_integer("cpu_cores", config["cpu_cores"])
    gaussian_memory = validate_gaussian_memory(config["gaussian_memory"])
    require_positive_integer("nodes", config["nodes"])
    require_positive_integer("ntasks", config["ntasks"])
    require_text("partition", config["partition"], allow_spaces=False)

    if not SAFE_PARTITION.fullmatch(config["partition"]):
        raise ValueError("partition contains unsupported characters")

    rows.extend(
        [
            ("DIRECT", "route_keywords", config["route_keywords"]),
            ("DIRECT", "cpu_cores", str(config["cpu_cores"])),
            ("DIRECT", "gaussian_memory", gaussian_memory),
            ("DIRECT", "nodes", str(config["nodes"])),
            ("DIRECT", "ntasks", str(config["ntasks"])),
            ("DIRECT", "partition", config["partition"]),
        ]
    )

    for row in rows:
        print("\t".join(row))
except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
    print(f"Error: invalid customization file {sys.argv[1]}: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
)"; then
    exit 1
fi

STATE_LABELS=()
STATE_RECORDS=()
FUNCTIONAL_LABELS=()
FUNCTIONAL_VALUES=()
BASIS_SET_LABELS=()
BASIS_SET_VALUES=()
SOLVATION_MODEL_LABELS=()
SOLVATION_MODEL_ROUTES=()
WALLTIME_LABELS=()
WALLTIME_VALUES=()
ROUTE_KEYWORDS=""
CPU_CORES=""
GAUSSIAN_MEMORY=""
NODES=""
NTASKS=""
PARTITION=""

while IFS=$'\t' read -r RECORD_TYPE FIRST_VALUE SECOND_VALUE; do
    case "$RECORD_TYPE" in
        STATE)
            STATE_LABELS+=("$FIRST_VALUE")
            STATE_RECORDS+=("$SECOND_VALUE")
            ;;
        FUNCTIONAL)
            FUNCTIONAL_LABELS+=("$FIRST_VALUE")
            FUNCTIONAL_VALUES+=("$SECOND_VALUE")
            ;;
        BASIS_SET)
            BASIS_SET_LABELS+=("$FIRST_VALUE")
            BASIS_SET_VALUES+=("$SECOND_VALUE")
            ;;
        SOLVATION_MODEL)
            SOLVATION_MODEL_LABELS+=("$FIRST_VALUE")
            SOLVATION_MODEL_ROUTES+=("$SECOND_VALUE")
            ;;
        WALLTIME)
            WALLTIME_LABELS+=("$FIRST_VALUE")
            WALLTIME_VALUES+=("$SECOND_VALUE")
            ;;
        DIRECT)
            case "$FIRST_VALUE" in
                route_keywords) ROUTE_KEYWORDS="$SECOND_VALUE" ;;
                cpu_cores) CPU_CORES="$SECOND_VALUE" ;;
                gaussian_memory) GAUSSIAN_MEMORY="$SECOND_VALUE" ;;
                nodes) NODES="$SECOND_VALUE" ;;
                ntasks) NTASKS="$SECOND_VALUE" ;;
                partition) PARTITION="$SECOND_VALUE" ;;
                *)
                    echo "Error: internal configuration parser returned unknown field: $FIRST_VALUE" >&2
                    exit 1
                    ;;
            esac
            ;;
        *)
            echo "Error: internal configuration parser returned unknown record: $RECORD_TYPE" >&2
            exit 1
            ;;
    esac
done <<< "$CONFIG_ROWS"

MOLECULE_SMILES=()
MOLECULE_IDS=()
MOLECULE_SOLVENTS=()
LINE_NUMBER=0

while IFS= read -r LINE || [ -n "$LINE" ]; do
    LINE_NUMBER=$((LINE_NUMBER + 1))
    FIELDS=()
    read -r -a FIELDS <<< "$LINE"

    if [ "${#FIELDS[@]}" -eq 0 ]; then
        continue
    fi

    if [[ "${FIELDS[0]}" == \#* ]]; then
        continue
    fi

    if [ "${#FIELDS[@]}" -ne 3 ]; then
        echo "Error: line $LINE_NUMBER must contain exactly three columns: SMILES molecule_id solvent" >&2
        exit 1
    fi

    SMILES="${FIELDS[0]}"
    MOLECULE_ID="${FIELDS[1]}"
    SOLVENT="${FIELDS[2]}"

    if [[ ! "$MOLECULE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
        echo "Error: line $LINE_NUMBER has unsafe molecule_id '$MOLECULE_ID'" >&2
        exit 1
    fi

    if [[ ! "$SOLVENT" =~ ^[A-Za-z0-9][A-Za-z0-9,+._-]*$ ]]; then
        echo "Error: line $LINE_NUMBER has unsafe solvent '$SOLVENT'" >&2
        exit 1
    fi

    for ((INDEX = 0; INDEX < ${#MOLECULE_IDS[@]}; INDEX++)); do
        if [ "${MOLECULE_IDS[$INDEX]}" = "$MOLECULE_ID" ]; then
            echo "Error: duplicate molecule_id '$MOLECULE_ID' at line $LINE_NUMBER" >&2
            exit 1
        fi
    done

    MOLECULE_SMILES+=("$SMILES")
    MOLECULE_IDS+=("$MOLECULE_ID")
    MOLECULE_SOLVENTS+=("$SOLVENT")
done < "$SMI_FILE"

MOLECULE_COUNT="${#MOLECULE_IDS[@]}"

if [ "$MOLECULE_COUNT" -eq 0 ]; then
    echo "Error: input file contains no molecule records" >&2
    exit 1
fi

choose_option() {
    local heading="$1"
    shift
    local options=("$@")
    local choice
    local option_index

    while true; do
        echo ""
        echo "$heading"

        for ((option_index = 0; option_index < ${#options[@]}; option_index++)); do
            printf '  %d) %s\n' "$((option_index + 1))" "${options[$option_index]}"
        done

        printf 'Enter a number (1-%d): ' "${#options[@]}"

        if ! IFS= read -r choice; then
            echo "" >&2
            echo "Error: input ended before a selection was confirmed" >&2
            return 1
        fi

        if [[ "$choice" =~ ^[1-9][0-9]*$ ]] \
            && [ "$choice" -ge 1 ] \
            && [ "$choice" -le "${#options[@]}" ]; then
            SELECTED_INDEX=$((choice - 1))
            return 0
        fi

        echo "Invalid selection. Enter one of the displayed numbers." >&2
    done
}

FUNCTIONAL_DISPLAY=()
for ((INDEX = 0; INDEX < ${#FUNCTIONAL_LABELS[@]}; INDEX++)); do
    FUNCTIONAL_DISPLAY+=("${FUNCTIONAL_LABELS[$INDEX]} -> ${FUNCTIONAL_VALUES[$INDEX]}")
done

BASIS_SET_DISPLAY=()
for ((INDEX = 0; INDEX < ${#BASIS_SET_LABELS[@]}; INDEX++)); do
    BASIS_SET_DISPLAY+=("${BASIS_SET_LABELS[$INDEX]} -> ${BASIS_SET_VALUES[$INDEX]}")
done

SOLVATION_MODEL_DISPLAY=()
for ((INDEX = 0; INDEX < ${#SOLVATION_MODEL_LABELS[@]}; INDEX++)); do
    SOLVATION_MODEL_DISPLAY+=("${SOLVATION_MODEL_LABELS[$INDEX]} -> ${SOLVATION_MODEL_ROUTES[$INDEX]}")
done

WALLTIME_DISPLAY=()
for ((INDEX = 0; INDEX < ${#WALLTIME_LABELS[@]}; INDEX++)); do
    WALLTIME_DISPLAY+=("${WALLTIME_LABELS[$INDEX]} -> ${WALLTIME_VALUES[$INDEX]}")
done

choose_option "Select functional:" "${FUNCTIONAL_DISPLAY[@]}"
FUNCTIONAL_INDEX="$SELECTED_INDEX"
choose_option "Select basis set:" "${BASIS_SET_DISPLAY[@]}"
BASIS_SET_INDEX="$SELECTED_INDEX"
choose_option "Select solvation model:" "${SOLVATION_MODEL_DISPLAY[@]}"
SOLVATION_MODEL_INDEX="$SELECTED_INDEX"

FUNCTIONAL_LABEL="${FUNCTIONAL_LABELS[$FUNCTIONAL_INDEX]}"
FUNCTIONAL_VALUE="${FUNCTIONAL_VALUES[$FUNCTIONAL_INDEX]}"
BASIS_SET_LABEL="${BASIS_SET_LABELS[$BASIS_SET_INDEX]}"
BASIS_SET_VALUE="${BASIS_SET_VALUES[$BASIS_SET_INDEX]}"
SOLVATION_MODEL_LABEL="${SOLVATION_MODEL_LABELS[$SOLVATION_MODEL_INDEX]}"
SOLVATION_MODEL_ROUTE="${SOLVATION_MODEL_ROUTES[$SOLVATION_MODEL_INDEX]}"

TASK_NAME="${INPUT_BASE%.smi}"
METHOD_NAME="${FUNCTIONAL_LABEL}__${BASIS_SET_LABEL}__${SOLVATION_MODEL_LABEL}"
CALCULATIONS_ROOT="$BASE/calculations"
RESULTS_ROOT="$BASE/results"
CALCULATION_TASK_DIR="$CALCULATIONS_ROOT/$TASK_NAME"
CALCULATION_METHOD_DIR="$CALCULATION_TASK_DIR/$METHOD_NAME"
BATCH_COPY="$CALCULATION_TASK_DIR/$INPUT_BASE"
COORDINATES_DIR="$CALCULATION_TASK_DIR/coordinates"
COORDINATE_STAGE="$CALCULATION_TASK_DIR/.coordinates.build"
METHOD_STAGE="$CALCULATION_TASK_DIR/.${METHOD_NAME}.build"
WORK_ROOT="$CALCULATION_METHOD_DIR/work"
LOGS_DIR="$CALCULATION_METHOD_DIR/logs"
SUBMIT_DIR="$CALCULATION_METHOD_DIR/submit"
PREPARATION_LOG="$CALCULATION_METHOD_DIR/preparation.log"
RESULT_TASK_DIR="$RESULTS_ROOT/$TASK_NAME"
RESULT_METHOD_DIR="$RESULT_TASK_DIR/$METHOD_NAME"
RESULT_METHOD_STAGE="$RESULT_TASK_DIR/.${METHOD_NAME}.build"
SUBMIT_SCRIPT="$SUBMIT_DIR/submit.sh"
TASK_LOCK="$CALCULATIONS_ROOT/.${TASK_NAME}.prepare.lock"

path_exists() {
    [ -e "$1" ] || [ -L "$1" ]
}

validate_result_tree() {
    local result_path="$1"
    local completeness="$2"

    python3 - "$result_path" "$completeness" "$COORDINATES_DIR" "${MOLECULE_IDS[@]}" <<'PY'
import os
import stat
import sys
from pathlib import Path


result_path = Path(sys.argv[1])
completeness = sys.argv[2]
coordinates_path = Path(sys.argv[3])
expected_ids = set(sys.argv[4:])

try:
    if completeness not in {"exact", "partial"}:
        raise ValueError(f"unsupported completeness rule: {completeness}")

    result_stat = result_path.lstat()

    if not stat.S_ISDIR(result_stat.st_mode):
        raise ValueError("path is not a regular directory")

    entries = list(os.scandir(result_path))
    actual_ids = {entry.name for entry in entries}
    unexpected = sorted(actual_ids - expected_ids)
    missing = sorted(expected_ids - actual_ids)

    if unexpected:
        raise ValueError("unexpected entries: " + ", ".join(unexpected))

    if completeness == "exact" and missing:
        raise ValueError("missing molecule directories: " + ", ".join(missing))

    for entry in entries:
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            raise ValueError(f"entry is not a regular directory: {entry.name}")

        with os.scandir(entry.path) as contents:
            molecule_entries = list(contents)
        # Older preparations copied lowest.xyz here. Preserve a verified copy
        # when resuming them, but never create new results-side coordinates.
        if len(molecule_entries) > 1:
            raise ValueError(f"ambiguous legacy coordinate entries: {entry.name}")
        for item in molecule_entries:
            original = coordinates_path / entry.name / "lowest.xyz"
            if (item.name not in {"lowest.xyz", ".lowest.xyz.tmp"} or item.is_symlink()
                    or not item.is_file(follow_symlinks=False)
                    or original.is_symlink() or not original.is_file()):
                raise ValueError(f"unexpected or unverified results entry: {entry.name}/{item.name}")
            saved, source = Path(item.path).read_bytes(), original.read_bytes()
            if (item.name == "lowest.xyz" and saved != source) or not source.startswith(saved):
                raise ValueError(f"legacy coordinates differ from the source: {entry.name}/{item.name}")
except (OSError, ValueError) as error:
    print(
        f"Error: results directory is not a valid preparation tree: {error}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
}

assess_method_publication_state() {
    local calculation_method_exists=0
    local result_method_exists=0

    METHOD_PUBLICATION_MODE="new"

    if path_exists "$CALCULATION_METHOD_DIR"; then
        calculation_method_exists=1
    fi

    if path_exists "$RESULT_METHOD_DIR"; then
        result_method_exists=1
    fi

    if [ "$calculation_method_exists" -eq 1 ] \
        && [ "$result_method_exists" -eq 1 ]; then
        echo "Error: this task and method have already been prepared:" >&2
        echo "$CALCULATION_METHOD_DIR" >&2
        return 1
    fi

    if [ "$calculation_method_exists" -eq 1 ]; then
        echo "Error: calculation method exists without its results directory:" >&2
        echo "$CALCULATION_METHOD_DIR" >&2
        return 1
    fi

    if [ "$result_method_exists" -eq 1 ]; then
        if path_exists "$RESULT_METHOD_STAGE"; then
            echo "Error: final and staging results methods both exist:" >&2
            echo "$RESULT_TASK_DIR" >&2
            return 1
        fi

        if ! validate_result_tree "$RESULT_METHOD_DIR" exact; then
            return 1
        fi

        METHOD_PUBLICATION_MODE="recover-results"
    fi
}

inspect_coordinate_stage() {
    local inspection_output
    local record_type
    local record_value

    VALID_COORDINATE_IDS=()
    MISSING_COORDINATE_IDS=()
    COORDINATE_STAGE_READY=0

    if ! inspection_output="$(
        python3 "$SCRIPT_DIR/make_com.py" inspect-coordinate-stage \
            --task-input "$BATCH_COPY" \
            --coordinates-dir "$COORDINATE_STAGE"
    )"; then
        return 1
    fi

    while IFS=$'\t' read -r record_type record_value; do
        [ -n "$record_type" ] || continue

        case "$record_type" in
            VALID)
                VALID_COORDINATE_IDS+=("$record_value")
                ;;
            MISSING)
                MISSING_COORDINATE_IDS+=("$record_value")
                ;;
            READY)
                case "$record_value" in
                    0|1) COORDINATE_STAGE_READY="$record_value" ;;
                    *)
                        echo "Error: coordinate inspection returned an invalid READY value" >&2
                        return 1
                        ;;
                esac
                ;;
            *)
                echo "Error: coordinate inspection returned an unknown record: $record_type" >&2
                return 1
                ;;
        esac
    done <<< "$inspection_output"

    if [ "$COORDINATE_STAGE_READY" -eq 1 ] \
        && [ "${#MISSING_COORDINATE_IDS[@]}" -ne 0 ]; then
        echo "Error: a complete coordinate build cannot contain missing molecules" >&2
        return 1
    fi
}

verify_coordinate_snapshot() {
    python3 "$SCRIPT_DIR/make_com.py" verify-coordinate-snapshot \
        --task-input "$BATCH_COPY" \
        --coordinates-dir "$COORDINATES_DIR"
}

coordinate_id_is_missing() {
    local requested_id="$1"
    local candidate_id

    for candidate_id in "${MISSING_COORDINATE_IDS[@]}"; do
        if [ "$candidate_id" = "$requested_id" ]; then
            return 0
        fi
    done

    return 1
}

assess_coordinate_state() {
    VALID_COORDINATE_IDS=()
    MISSING_COORDINATE_IDS=()
    COORDINATE_STAGE_READY=0

    if ! path_exists "$CALCULATION_TASK_DIR"; then
        COORDINATE_MODE="create"
        MISSING_COORDINATE_IDS=("${MOLECULE_IDS[@]}")
        return 0
    fi

    if [ -L "$CALCULATION_TASK_DIR" ] || [ ! -d "$CALCULATION_TASK_DIR" ]; then
        echo "Error: calculation task path is not a regular directory: $CALCULATION_TASK_DIR" >&2
        return 1
    fi

    if [ -L "$BATCH_COPY" ] || [ ! -f "$BATCH_COPY" ]; then
        echo "Error: existing task is missing its batch input copy: $BATCH_COPY" >&2
        return 1
    fi

    if ! cmp -s "$SMI_FILE" "$BATCH_COPY"; then
        echo "Error: input does not exactly match the existing task batch copy:" >&2
        echo "$BATCH_COPY" >&2
        return 1
    fi

    if path_exists "$COORDINATES_DIR" && path_exists "$COORDINATE_STAGE"; then
        echo "Error: task contains both a coordinate snapshot and a coordinate build:" >&2
        echo "$CALCULATION_TASK_DIR" >&2
        return 1
    fi

    if path_exists "$COORDINATES_DIR"; then
        if [ -L "$COORDINATES_DIR" ] || [ ! -d "$COORDINATES_DIR" ]; then
            echo "Error: coordinate snapshot path is not a regular directory: $COORDINATES_DIR" >&2
            return 1
        fi

        if ! verify_coordinate_snapshot; then
            return 1
        fi

        COORDINATE_MODE="reuse"
        VALID_COORDINATE_IDS=("${MOLECULE_IDS[@]}")
        return 0
    fi

    if path_exists "$COORDINATE_STAGE"; then
        if [ -L "$COORDINATE_STAGE" ] || [ ! -d "$COORDINATE_STAGE" ]; then
            echo "Error: coordinate build path is not a regular directory: $COORDINATE_STAGE" >&2
            return 1
        fi

        if ! inspect_coordinate_stage; then
            return 1
        fi

        COORDINATE_MODE="resume"
        return 0
    fi

    echo "Error: existing task does not contain a valid coordinate snapshot or coordinate build:" >&2
    echo "$CALCULATION_TASK_DIR" >&2
    return 1
}

for ROOT_PATH in "$CALCULATIONS_ROOT" "$RESULTS_ROOT"; do
    if path_exists "$ROOT_PATH" && { [ -L "$ROOT_PATH" ] || [ ! -d "$ROOT_PATH" ]; }; then
        echo "Error: managed output root must be a regular directory: $ROOT_PATH" >&2
        exit 1
    fi
done

if path_exists "$METHOD_STAGE" \
    && { [ -L "$METHOD_STAGE" ] || [ ! -d "$METHOD_STAGE" ]; }; then
    echo "Error: method build path is not a regular directory: $METHOD_STAGE" >&2
    exit 1
fi

if path_exists "$RESULT_TASK_DIR" \
    && { [ -L "$RESULT_TASK_DIR" ] || [ ! -d "$RESULT_TASK_DIR" ]; }; then
    echo "Error: result task path must be a regular directory: $RESULT_TASK_DIR" >&2
    exit 1
fi

if path_exists "$RESULT_METHOD_STAGE" \
    && { [ -L "$RESULT_METHOD_STAGE" ] || [ ! -d "$RESULT_METHOD_STAGE" ]; }; then
    echo "Error: result build path is not a regular directory: $RESULT_METHOD_STAGE" >&2
    exit 1
fi

if path_exists "$RESULT_METHOD_STAGE"; then
    if ! validate_result_tree "$RESULT_METHOD_STAGE" partial; then
        exit 1
    fi
fi

if ! assess_method_publication_state; then
    exit 1
fi

PREVIEW_METHOD_PUBLICATION_MODE="$METHOD_PUBLICATION_MODE"

SELECTED_STATES=()
SELECTED_STATE_RECORDS=()

for ((INDEX = 0; INDEX < ${#STATE_LABELS[@]}; INDEX++)); do
    while true; do
        printf 'Prepare %s for every molecule? (y/n): ' "${STATE_LABELS[$INDEX]}"

        if ! IFS= read -r STATE_ANSWER; then
            echo "" >&2
            echo "Error: input ended before state selection; nothing was created" >&2
            exit 1
        fi

        case "$STATE_ANSWER" in
            y|Y)
                SELECTED_STATES+=("${STATE_LABELS[$INDEX]}")
                SELECTED_STATE_RECORDS+=("${STATE_RECORDS[$INDEX]}")
                break
                ;;
            n|N)
                break
                ;;
            *)
                echo "Please answer y or n." >&2
                ;;
        esac
    done
done

STATE_COUNT="${#SELECTED_STATES[@]}"

if [ "$STATE_COUNT" -eq 0 ]; then
    echo "No states selected; nothing was created."
    exit 0
fi

choose_option "Select walltime:" "${WALLTIME_DISPLAY[@]}"
WALLTIME_INDEX="$SELECTED_INDEX"
WALLTIME_LABEL="${WALLTIME_LABELS[$WALLTIME_INDEX]}"
WALLTIME_VALUE="${WALLTIME_VALUES[$WALLTIME_INDEX]}"
EXPECTED_JOBS=$((MOLECULE_COUNT * STATE_COUNT))

if ! assess_coordinate_state; then
    exit 1
fi

VALID_COORDINATE_COUNT="${#VALID_COORDINATE_IDS[@]}"
MISSING_COORDINATE_COUNT="${#MISSING_COORDINATE_IDS[@]}"

if [ "$COORDINATE_MODE" = "reuse" ]; then
    OPEN_BABEL_REQUIRED="no"
elif [ "$MISSING_COORDINATE_COUNT" -eq 0 ]; then
    OPEN_BABEL_REQUIRED="no"
else
    OPEN_BABEL_REQUIRED="yes"
fi

echo ""
echo "Resolved customization preview"
echo "======================================"
echo "Input file: $SMI_FILE"
echo "Molecule count: $MOLECULE_COUNT"
echo "Selected states: ${SELECTED_STATES[*]}"
python3 - "${SELECTED_STATE_RECORDS[@]}" <<'PY'
import json
import sys

for record in sys.argv[1:]:
    option = json.loads(record)
    print(
        f"  {option['label']}: charge offset {option['charge_offset']:+d}, "
        f"multiplicity {option['multiplicity']}"
    )
PY
echo "Gaussian jobs: $EXPECTED_JOBS"
echo "Functional: $FUNCTIONAL_LABEL -> $FUNCTIONAL_VALUE"
echo "Basis set: $BASIS_SET_LABEL -> $BASIS_SET_VALUE"
echo "Solvation model: $SOLVATION_MODEL_LABEL -> $SOLVATION_MODEL_ROUTE"
echo "Walltime: $WALLTIME_LABEL -> $WALLTIME_VALUE"
echo "Route keywords: $ROUTE_KEYWORDS"
echo "CPU cores: $CPU_CORES"
echo "Gaussian memory: $GAUSSIAN_MEMORY"
echo "Nodes: $NODES"
echo "Tasks: $NTASKS"
echo "Partition: $PARTITION"
echo "Method name: $METHOD_NAME"
echo "Method publication mode: $METHOD_PUBLICATION_MODE"
echo "Batch copy: $BATCH_COPY"
echo "Coordinate mode: $COORDINATE_MODE"
echo "Coordinate snapshot: $COORDINATES_DIR"
echo "Coordinates already valid: $VALID_COORDINATE_COUNT"
echo "Coordinates to generate: $MISSING_COORDINATE_COUNT"
echo "Open Babel required: $OPEN_BABEL_REQUIRED"
echo "Calculation directory: $CALCULATION_METHOD_DIR"
echo "Work directory: $WORK_ROOT"
echo "Slurm stdout/stderr directory: $LOGS_DIR"
echo "Submit directory: $SUBMIT_DIR"
echo "Preparation log: $PREPARATION_LOG"
echo "Results directory: $RESULT_METHOD_DIR"
echo "======================================"

if [ "$MOLECULE_COUNT" -gt 10 ]; then
    echo "Warning: this batch contains more than 10 molecules."
    echo "The batch will remain intact and all molecules will be prepared."
fi

if path_exists "$METHOD_STAGE"; then
    echo "An incomplete method build will be replaced after confirmation:"
    echo "$METHOD_STAGE"
fi

if [ "$METHOD_PUBLICATION_MODE" = "recover-results" ]; then
    echo "An incomplete results method will be recovered after confirmation:"
    echo "$RESULT_METHOD_DIR"
fi

if path_exists "$RESULT_METHOD_STAGE"; then
    echo "An incomplete results build will be reused after confirmation:"
    echo "$RESULT_METHOD_STAGE"
fi

while true; do
    printf 'Proceed with this preparation? (y/n): '

    if ! IFS= read -r CONFIRMATION; then
        echo "" >&2
        echo "Error: input ended before confirmation; nothing was created" >&2
        exit 1
    fi

    case "$CONFIRMATION" in
        y|Y)
            break
            ;;
        n|N)
            echo "Preparation cancelled; nothing was created."
            exit 0
            ;;
        *)
            echo "Please answer y or n." >&2
            ;;
    esac
done

mkdir -p "$CALCULATIONS_ROOT"

if ! mkdir "$TASK_LOCK" 2>/dev/null; then
    echo "Error: another preparation is active for this task:" >&2
    echo "$TASK_LOCK" >&2
    exit 1
fi

TASK_LOCK_HELD=1

cleanup_task_lock() {
    local exit_status=$?

    if [ "${TASK_LOCK_HELD:-0}" -eq 1 ]; then
        rmdir "$TASK_LOCK" 2>/dev/null || true
    fi

    exit "$exit_status"
}

trap cleanup_task_lock EXIT

if ! assess_method_publication_state; then
    exit 1
fi

if [ "$METHOD_PUBLICATION_MODE" != "$PREVIEW_METHOD_PUBLICATION_MODE" ]; then
    echo "Error: method publication state changed after confirmation; run again" >&2
    exit 1
fi

if [ "$METHOD_PUBLICATION_MODE" = "recover-results" ]; then
    if path_exists "$RESULT_METHOD_STAGE"; then
        echo "Error: result build appeared before recovery:" >&2
        echo "$RESULT_METHOD_STAGE" >&2
        exit 1
    fi

    if ! validate_result_tree "$RESULT_METHOD_DIR" exact; then
        exit 1
    fi

    if ! mv "$RESULT_METHOD_DIR" "$RESULT_METHOD_STAGE"; then
        echo "Error: failed to recover incomplete results method" >&2
        exit 1
    fi
fi

if ! assess_coordinate_state; then
    exit 1
fi

MISSING_COORDINATE_COUNT="${#MISSING_COORDINATE_IDS[@]}"
COORDINATES_REUSED_COUNT="${#VALID_COORDINATE_IDS[@]}"
COORDINATES_GENERATED_COUNT=0

if [ "$MISSING_COORDINATE_COUNT" -ne 0 ]; then
    if ! command -v module >/dev/null 2>&1; then
        echo "Error: the Environment Modules command is unavailable" >&2
        exit 1
    fi

    if ! module load openbabel/3.1.1-gcc14.2.0; then
        echo "Error: failed to load openbabel/3.1.1-gcc14.2.0" >&2
        exit 1
    fi

    for REQUIRED_COMMAND in obabel obminimize; do
        if ! command -v "$REQUIRED_COMMAND" >/dev/null 2>&1; then
            echo "Error: $REQUIRED_COMMAND is unavailable after loading Open Babel" >&2
            exit 1
        fi
    done
fi

if ! path_exists "$CALCULATION_TASK_DIR"; then
    mkdir "$CALCULATION_TASK_DIR"
    cp "$SMI_FILE" "$BATCH_COPY"
fi

if [ ! -f "$BATCH_COPY" ]; then
    echo "Error: task batch input copy is missing after task initialization: $BATCH_COPY" >&2
    exit 1
fi

if [ "$COORDINATE_MODE" != "reuse" ] && ! path_exists "$COORDINATE_STAGE"; then
    mkdir "$COORDINATE_STAGE"
    python3 "$SCRIPT_DIR/make_com.py" initialize-coordinate-stage \
        --task-input "$BATCH_COPY" \
        --coordinates-dir "$COORDINATE_STAGE"
fi

if [ "$COORDINATE_MODE" != "reuse" ]; then
    if ! inspect_coordinate_stage; then
        exit 1
    fi
fi

prepare_coordinate() (
    local smiles="$1"
    local molecule_id="$2"
    local solvent="$3"
    local temporary_root
    local coordinate_dir
    local record_file
    local raw_conformers
    local minimized_conformers

    # shellcheck disable=SC2329  # Invoked by the EXIT trap below.
    cleanup_coordinate_temp() {
        local exit_status=$?

        if [ -n "${temporary_root:-}" ] && [ -d "$temporary_root" ]; then
            rm -rf -- "$temporary_root" || true
        fi

        exit "$exit_status"
    }

    trap cleanup_coordinate_temp EXIT
    temporary_root="$(mktemp -d "$COORDINATE_STAGE/.${molecule_id}.build.XXXXXX")" || exit 1
    coordinate_dir="$temporary_root/$molecule_id"
    record_file="$coordinate_dir/${molecule_id}.smi"
    raw_conformers="$coordinate_dir/.raw_conformers.xyz"
    minimized_conformers="$coordinate_dir/.minimized_conformers.xyz"
    mkdir "$coordinate_dir" || exit 1
    printf '%s\t%s\t%s\n' "$smiles" "$molecule_id" "$solvent" > "$record_file" || exit 1
    cd "$coordinate_dir" || exit 1

    obabel \
        -ismi "$record_file" \
        -oxyz \
        -h \
        --gen3d \
        -O initial.xyz || exit 1

    obabel \
        -ixyz initial.xyz \
        -oxyz \
        -O "$raw_conformers" \
        --conformer \
        --nconf 10 \
        --score energy \
        --writeconformers || exit 1

    obminimize \
        -ff UFF \
        -ixyz "$raw_conformers" \
        -oxyz > "$minimized_conformers" || exit 1

    obabel \
        -ixyz "$minimized_conformers" \
        -oxyz \
        -O conformers.xyz \
        --energy \
        --ff UFF \
        --append Energy || exit 1

    python3 "$SCRIPT_DIR/make_com.py" select-geometry \
        --molecule-id "$molecule_id" \
        --conformers-file "$coordinate_dir/conformers.xyz" \
        --lowest-file "$coordinate_dir/lowest.xyz" || exit 1

    rm -f "$raw_conformers" "$minimized_conformers" || exit 1

    python3 - "$SCRIPT_DIR" "$BATCH_COPY" "$temporary_root" "$molecule_id" <<'PY' || exit 1
import sys

sys.path.insert(0, sys.argv[1])

from make_com import read_molecules_from_smi, validate_coordinate_entry

task_input = sys.argv[2]
coordinates_root = sys.argv[3]
molecule_id = sys.argv[4]
molecules = {
    molecule["molecule_id"]: molecule
    for molecule in read_molecules_from_smi(task_input)
}
validate_coordinate_entry(coordinates_root, molecules[molecule_id])
PY

    if path_exists "$COORDINATE_STAGE/$molecule_id"; then
        echo "Error: coordinate entry appeared before publication: $molecule_id" >&2
        exit 1
    fi

    mv "$coordinate_dir" "$COORDINATE_STAGE/$molecule_id" || exit 1
    rmdir "$temporary_root" || exit 1
    temporary_root=""

    echo "Prepared coordinate: molecule_id=$molecule_id smiles=$smiles"
)

if [ "$COORDINATE_MODE" != "reuse" ] \
    && [ "$COORDINATE_STAGE_READY" -eq 0 ]; then
    COORDINATE_SUCCESS=0

    for ((INDEX = 0; INDEX < MOLECULE_COUNT; INDEX++)); do
        MOLECULE_ID="${MOLECULE_IDS[$INDEX]}"

        if ! coordinate_id_is_missing "$MOLECULE_ID"; then
            continue
        fi

        echo "Preparing coordinate [$((INDEX + 1))/$MOLECULE_COUNT]: molecule_id=$MOLECULE_ID"

        if prepare_coordinate \
            "${MOLECULE_SMILES[$INDEX]}" \
            "$MOLECULE_ID" \
            "${MOLECULE_SOLVENTS[$INDEX]}"; then
            COORDINATE_SUCCESS=$((COORDINATE_SUCCESS + 1))
            COORDINATES_GENERATED_COUNT=$((COORDINATES_GENERATED_COUNT + 1))
            echo "Coordinate status: success for molecule_id=$MOLECULE_ID"
        else
            echo "Coordinate status: failed for molecule_id=$MOLECULE_ID" >&2
        fi
    done

    if ! inspect_coordinate_stage; then
        exit 1
    fi

    if [ "${#MISSING_COORDINATE_IDS[@]}" -ne 0 ]; then
        echo ""
        echo "Coordinate preparation finished with failures"
        echo "Coordinates prepared in this run: $COORDINATE_SUCCESS"
        echo "Coordinates still missing: ${#MISSING_COORDINATE_IDS[@]}"
        echo "Missing molecule IDs:"

        for MOLECULE_ID in "${MISSING_COORDINATE_IDS[@]}"; do
            echo "  $MOLECULE_ID"
        done

        echo "Run the same command again to resume the valid coordinate build."
        exit 1
    fi

fi

if [ "$COORDINATE_MODE" != "reuse" ]; then
    if [ "$COORDINATE_STAGE_READY" -eq 1 ]; then
        echo "Recovering completed coordinate build..."
    else
        echo "Finalizing coordinate snapshot..."
    fi

    python3 "$SCRIPT_DIR/make_com.py" build-coordinate-manifest \
        --task-input "$BATCH_COPY" \
        --coordinates-dir "$COORDINATE_STAGE"

    python3 "$SCRIPT_DIR/make_com.py" verify-coordinate-snapshot \
        --task-input "$BATCH_COPY" \
        --coordinates-dir "$COORDINATE_STAGE"

    if path_exists "$COORDINATES_DIR"; then
        echo "Error: coordinate snapshot appeared before publication: $COORDINATES_DIR" >&2
        exit 1
    fi

    mv "$COORDINATE_STAGE" "$COORDINATES_DIR"
fi

if ! verify_coordinate_snapshot; then
    exit 1
fi

if path_exists "$METHOD_STAGE"; then
    if [ -L "$METHOD_STAGE" ] || [ ! -d "$METHOD_STAGE" ]; then
        echo "Error: method build path is not a regular directory: $METHOD_STAGE" >&2
        exit 1
    fi

    rm -rf -- "$METHOD_STAGE"
fi

mkdir -p "$METHOD_STAGE/work" "$METHOD_STAGE/logs" "$METHOD_STAGE/submit"
STAGE_PREPARATION_LOG="$METHOD_STAGE/preparation.log"

{
    echo "Batch preparation started"
    echo "Input file: $SMI_FILE"
    echo "Batch copy: $BATCH_COPY"
    echo "Coordinate snapshot: $COORDINATES_DIR"
    echo "Coordinate mode: $COORDINATE_MODE"
    echo "Coordinates reused: $COORDINATES_REUSED_COUNT"
    echo "Coordinates generated: $COORDINATES_GENERATED_COUNT"
    echo "Functional: $FUNCTIONAL_LABEL -> $FUNCTIONAL_VALUE"
    echo "Basis set: $BASIS_SET_LABEL -> $BASIS_SET_VALUE"
    echo "Solvation model: $SOLVATION_MODEL_LABEL -> $SOLVATION_MODEL_ROUTE"
    echo "Walltime: $WALLTIME_LABEL -> $WALLTIME_VALUE"
    echo "Route keywords: $ROUTE_KEYWORDS"
    echo "CPU cores: $CPU_CORES"
    echo "Gaussian memory: $GAUSSIAN_MEMORY"
    echo "Nodes: $NODES"
    echo "Tasks: $NTASKS"
    echo "Partition: $PARTITION"
    echo "Method publication mode: $METHOD_PUBLICATION_MODE"
    echo "Molecule count: $MOLECULE_COUNT"
    echo "Expected Gaussian jobs: $EXPECTED_JOBS"
    echo "Calculation directory: $CALCULATION_METHOD_DIR"
    echo "Results directory: $RESULT_METHOD_DIR"
    echo "Selected states: ${SELECTED_STATES[*]}"
    python3 - "$SCRIPT_DIR" "${SELECTED_STATE_RECORDS[@]}" <<'PY'
import json
import sys

sys.path.insert(0, sys.argv[1])

from make_com import STATE_SELECTION_PREFIX, validate_state_options

selection = validate_state_options([json.loads(record) for record in sys.argv[2:]])
print(STATE_SELECTION_PREFIX + json.dumps(selection, separators=(",", ":")))
PY
    echo "======================================"
} > "$STAGE_PREPARATION_LOG"

prepare_method_molecule() (
    local molecule_id="$1"
    local output_work_dir="$METHOD_STAGE/work/$molecule_id"
    local runtime_work_dir="$WORK_ROOT/$molecule_id"
    local runtime_result_dir="$RESULT_METHOD_DIR/$molecule_id"
    local coordinate_dir="$COORDINATES_DIR/$molecule_id"

    mkdir -p "$output_work_dir" || exit 1

    python3 "$SCRIPT_DIR/make_com.py" write-inputs \
        --preparation-log "$STAGE_PREPARATION_LOG" \
        --molecule-id "$molecule_id" \
        --record-file "$coordinate_dir/${molecule_id}.smi" \
        --geometry-file "$coordinate_dir/lowest.xyz" \
        --output-work-dir "$output_work_dir" \
        --runtime-result-dir "$runtime_result_dir" \
        --functional "$FUNCTIONAL_VALUE" \
        --basis-set "$BASIS_SET_VALUE" \
        --solvation-route "$SOLVATION_MODEL_ROUTE" \
        --route-keywords "$ROUTE_KEYWORDS" \
        --cpu-cores "$CPU_CORES" \
        --gaussian-memory "$GAUSSIAN_MEMORY" || exit 1

    python3 "$SCRIPT_DIR/make_slurm.py" \
        --preparation-log "$STAGE_PREPARATION_LOG" \
        --molecule-id "$molecule_id" \
        --output-work-dir "$output_work_dir" \
        --runtime-work-dir "$runtime_work_dir" \
        --runtime-result-dir "$runtime_result_dir" \
        --runtime-logs-dir "$LOGS_DIR" \
        --functional-label "$FUNCTIONAL_LABEL" \
        --basis-set-label "$BASIS_SET_LABEL" \
        --solvation-model-label "$SOLVATION_MODEL_LABEL" \
        --nodes "$NODES" \
        --ntasks "$NTASKS" \
        --cpu-cores "$CPU_CORES" \
        --partition "$PARTITION" \
        --walltime "$WALLTIME_VALUE" || exit 1

    echo "Prepared molecule_id=$molecule_id"
)

SUCCESS=0
FAILED=0
FAILED_METHOD_IDS=()

for ((INDEX = 0; INDEX < MOLECULE_COUNT; INDEX++)); do
    MOLECULE_ID="${MOLECULE_IDS[$INDEX]}"

    echo "Preparing method [$((INDEX + 1))/$MOLECULE_COUNT]: molecule_id=$MOLECULE_ID" | tee -a "$STAGE_PREPARATION_LOG"
    echo "SMILES: ${MOLECULE_SMILES[$INDEX]}" >> "$STAGE_PREPARATION_LOG"
    echo "Solvent: ${MOLECULE_SOLVENTS[$INDEX]}" >> "$STAGE_PREPARATION_LOG"

    if prepare_method_molecule "$MOLECULE_ID" >> "$STAGE_PREPARATION_LOG" 2>&1; then
        SUCCESS=$((SUCCESS + 1))
        echo "Status: success for molecule_id=$MOLECULE_ID" | tee -a "$STAGE_PREPARATION_LOG"
    else
        FAILED=$((FAILED + 1))
        FAILED_METHOD_IDS+=("$MOLECULE_ID")
        echo "Status: failed for molecule_id=$MOLECULE_ID" | tee -a "$STAGE_PREPARATION_LOG"
    fi

    echo "--------------------------------------" >> "$STAGE_PREPARATION_LOG"
done

PREPARED_JOBS=$((SUCCESS * STATE_COUNT))

{
    echo "Batch preparation finished"
    echo "Total molecules: $MOLECULE_COUNT"
    echo "Expected Gaussian jobs: $EXPECTED_JOBS"
    echo "Successful preparations: $SUCCESS"
    echo "Prepared Gaussian jobs: $PREPARED_JOBS"
    echo "Failed preparations: $FAILED"
} | tee -a "$STAGE_PREPARATION_LOG"

if [ "$FAILED" -ne 0 ]; then
    echo "Failed molecule IDs:" | tee -a "$STAGE_PREPARATION_LOG" >&2

    for MOLECULE_ID in "${FAILED_METHOD_IDS[@]}"; do
        echo "  $MOLECULE_ID" | tee -a "$STAGE_PREPARATION_LOG" >&2
    done

    echo "Error: preparation was incomplete; no submit.sh was generated" | tee -a "$STAGE_PREPARATION_LOG" >&2
    echo "Incomplete method build: $METHOD_STAGE" >&2
    exit 1
fi

STAGE_SUBMIT_SCRIPT="$METHOD_STAGE/submit/submit.sh"

python3 - "$SCRIPT_DIR" "$STAGE_SUBMIT_SCRIPT" "$STAGE_PREPARATION_LOG" "$BATCH_COPY" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from make_com import read_molecules_from_smi, read_state_selection
from make_slurm import write_submit_script
write_submit_script(
    sys.argv[2],
    [m["molecule_id"] for m in read_molecules_from_smi(sys.argv[4])],
    [s["label"] for s in read_state_selection(sys.argv[3])],
)
PY

chmod +x "$STAGE_SUBMIT_SCRIPT"

if grep -R -F --include='*.com' --include='*.slurm' \
    "$METHOD_STAGE" "$METHOD_STAGE/work" >/dev/null 2>&1; then
    echo "Error: generated inputs contain a method build path" >&2
    exit 1
fi

{
    echo "Submit script: $SUBMIT_SCRIPT"
    echo "Check it before submission with:"
    printf 'cat %q\n' "$SUBMIT_SCRIPT"
    echo "Real Barkla submission remains a separate manual step:"
    printf 'bash %q\n' "$SUBMIT_SCRIPT"
} >> "$STAGE_PREPARATION_LOG"

mkdir -p "$RESULTS_ROOT" "$RESULT_TASK_DIR"

if path_exists "$RESULT_METHOD_STAGE"; then
    if ! validate_result_tree "$RESULT_METHOD_STAGE" partial; then
        exit 1
    fi
else
    mkdir "$RESULT_METHOD_STAGE"
fi

for MOLECULE_ID in "${MOLECULE_IDS[@]}"; do
    if ! path_exists "$RESULT_METHOD_STAGE/$MOLECULE_ID"; then
        mkdir "$RESULT_METHOD_STAGE/$MOLECULE_ID"
    fi


done

if ! validate_result_tree "$RESULT_METHOD_STAGE" exact; then
    exit 1
fi

if path_exists "$RESULT_METHOD_DIR"; then
    echo "Error: results method appeared before publication:" >&2
    echo "$RESULT_METHOD_DIR" >&2
    exit 1
fi

if ! mv "$RESULT_METHOD_STAGE" "$RESULT_METHOD_DIR"; then
    echo "Error: failed to publish result method directory" >&2
    exit 1
fi

if path_exists "$CALCULATION_METHOD_DIR"; then
    echo "Error: calculation method appeared before publication:" >&2
    echo "$CALCULATION_METHOD_DIR" >&2
    exit 1
fi

if ! mv "$METHOD_STAGE" "$CALCULATION_METHOD_DIR"; then
    echo "Error: failed to publish calculation method directory" >&2
    exit 1
fi

echo "Preparation complete."
echo "Preparation log: $PREPARATION_LOG"
echo "Submit script: $SUBMIT_SCRIPT"
