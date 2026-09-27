# Commands and environment

[Agent guide](../SKILL.md) · [Runtime contract](runtime-contract.md) · [Integration](integration.md)

These commands are for the agent or maintainer. Users can send [ordinary prompts](../PROMPTS.md). Resolve `MODULE` to the installed module folder and run from the task project, outside the module.

## Environment

Use the parent toolkit's Python 3.10 environment. Before a complete task:

```bash
python "$MODULE/scripts/validate_setup.py" --models
```

Stop unless it exits `0` and prints `READY`. Use the same interpreter for task commands. The checker prints installation guidance; do not install or download without authorization. See [preflight limits](runtime-contract.md#environment-and-limits).

Use the [toolkit installation guide](https://github.com/BanchaoRuan/molecular-research-toolkit/blob/main/INSTALL.md) for unified or selective setup. The retained module environment file is a maintainer compatibility entry; the existing name `smiles_auto` is not required for a valid environment. Tesseract must also be installed with the relevant system package manager; pip requirements do not supply it. Environment installation belongs to the parent.

### Native-library failures

If preflight passes but inference reports an import or native-library error, stop and inspect the actual failing import in the same interpreter. The checker tests declared versions and package availability rather than every native component. Preserve existing task evidence; resolve the environment before resuming recognition.

The [worked example](../examples/example001/README.md#reproducibility) encountered a SciPy 1.15.3 PROPACK loading error on macOS arm64. SciPy 1.13.1 was verified and installed with authorization, then the full gate was repeated. The verified SciPy version is now included in this release’s requirements. A different environment must satisfy the released requirements before this skill runs. Ask before changing an environment and check its other dependency constraints.

## New batch

```bash
python "$MODULE/scripts/run_source_folder_to_smiles.py" \
  /absolute/path/example001_single_molecule --task-name example001
```

`example001.png` keeps image ID `example001`. The batch creates the dated workspace in the working project, runs candidate generation, performs one bounded recovery for normal recognition failures, and prepares required MOLs.

| Option | Default / purpose |
| --- | --- |
| `--task-name` | Otherwise strips `_single_molecule` from the folder name; pass explicitly from a parent. |
| `--run-date` | Local date; `YYYYMMDD`. |
| `--no-name-lookup` | Disable plain-name queries; explicit SMILES/CID/CAS/InChIKey remain enabled. |
| `--allow-fragments` | Off; enable only after confirming intended fragments. |
| `--max-smiles-length` | `450`. |
| `--pubchem-timeout` | `20.0` seconds per lookup. |
| `--policy` | `strict`; at least two agreeing image variants. |
| `--molscribe-checkpoint` | Existing compatible checkpoint; otherwise MolScribe may request a download. |

Exit `0` means candidate generation completed, including rows needing review or human input. Exit `2` is a task error. Do not blindly rerun a new batch into its existing workspace.

## Compare with the source

Set `TASK` to the actual `workspace/YYYYMMDD_taskname_smiles`. Open every PNG in `candidate_materials/comparisons/`, then record the observed result:

```bash
python "$MODULE/scripts/render_smiles.py" review "$TASK" example001 \
  --source-match yes --confidence high \
  --notes "Source and reverse match, including substituents and charge."
```

For a mismatch, use `--source-match no --confidence low` and specific evidence. Missing reverse files block success. A failed review automatically attempts to prepare an available seed MOL.

To regenerate a comparison from the current candidate:

```bash
python "$MODULE/scripts/render_smiles.py" render "$TASK" --image-id example001
```

## Apply a correction

Once a correction is unambiguous:

```bash
python "$MODULE/scripts/chemdraw_fallback.py" apply "$TASK" example001 \
  --smiles 'CORRECTED_SMILES' --mol /absolute/path/corrected.mol \
  --notes "Evidence supporting this correction."
```

`--mol` is optional; otherwise the script generates a MOL from the corrected SMILES. A supplied MOL must match. The row returns to `pending`; inspect the new comparison before recording success.

Prepare missing required MOLs in an existing task with:

```bash
python "$MODULE/scripts/chemdraw_fallback.py" prepare-all "$TASK"
```

Exit `1` names rows with no valid seed; request manual structures instead of repeatedly retrying. `prepare` is for a failed row after receiving a new explicit seed or evidence.

## Publish

```bash
python "$MODULE/scripts/finalize_source_folder_results.py" "$TASK"
```

All rows must be terminal and required MOLs valid. Existing review/staging directories block publication. Success exits `0`; rejected publication exits `2`. See the [complete gates](runtime-contract.md#mol-and-finalization-checks).

`make_reports.py` is a preview helper using the same workspace staging directory as the finalizer. It is not an extra required step before finalization: an existing staging directory blocks that operation.

## Interrupted tasks

Inspect events, candidates, and the reported cause. Saved rows remain available. Resolve execution problems before retrying; do not convert them to molecular failures or invent suffixed tasks.

For one affected image in an existing valid workspace:

```bash
python "$MODULE/scripts/smiles_auto.py" "$TASK" --image-id example001 \
  --molscribe-checkpoint /absolute/path/existing-checkpoint.pth
```

This helper does not run the batch recovery wrapper. Exit `1` means a pending candidate or normal recognition failure; inspect the row. Exit `2` means a processing error. Preserve original options, including fragment handling and checkpoint selection.

Count completed recognition attempts in the events: after a normal first failure, allow one `--policy best-effort` attempt; after two failures, ask for human input. Retry a resolved transient execution error at most once. Then prepare required MOLs, compare sources, and finalize normally.

## Script map

| File | Responsibility |
| --- | --- |
| `run_source_folder_to_smiles.py` | New batch, preflight, bounded recovery. |
| `smiles_auto.py` | Per-image recognition and controlled recovery entry. |
| `smiles_core.py` | Shared paths, IDs, schema, normalization, events; not a CLI. |
| `text_lookup.py` | OCR and PubChem evidence. |
| `structure_predict.py` | Routing, variants, MolScribe/DECIMER. |
| `render_smiles.py` | Reverse structures, comparisons, reviews. |
| `chemdraw_fallback.py` | Required MOLs, rejected seeds, corrections. |
| `make_reports.py` | Workspace review staging. |
| `finalize_source_folder_results.py` | Validate and publish review. |
| `validate_setup.py` | Read-only environment and syntax gate. |
