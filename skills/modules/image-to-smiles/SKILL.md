---
name: image-to-smiles
description: Convert single-molecule images into source-reviewed SMILES, reverse structures, MOL files, and an Excel review package using OCR, PubChem, and OCSR candidates. Use when molecular images are ready for recognition; split multi-molecule figures before this stage.
---

# Image to SMILES

This is a task module within a parent toolkit. The parent owns installation, routing, and versions. Resolve `<module_dir>` to the folder containing this file. Resolve references relative to their containing document and scripts relative to this module. Run task commands from the user's working project, outside the module.

Read [commands](references/commands.md) for execution and recovery, [the runtime contract](references/runtime-contract.md) for schemas and output gates, and [integration](references/integration.md) when embedding this module in a parent workflow.

## Establish the task

Reuse images, working project, task name, existing IDs, and authorization supplied in the conversation or by the parent. Ask only about missing or ambiguous information. Do not assume private memory or a particular agent client.

- Each image must contain one complete target. Preserve source images and filename-stem IDs.
- Use an explicit single-molecule directory. For a directory not ending in `_single_molecule`, supply `--task-name`. A parent should always pass its established task name explicitly, including after image preparation.
- Resolve ambiguous abbreviations, fragment/salt treatment, conflicting structures, and uncertain charges with the user. Do not silently change molecular identity.
- Do not install packages or download weights without authorization. Reuse a compatible interpreter and approved checkpoint. Identifiers extracted from images may be sent to PubChem; honor access restrictions.

## Mandatory environment gate

Before creating or modifying a task workspace, use the same Python that will run the task:

```bash
python <module_dir>/scripts/validate_setup.py --models
```

Continue only after exit `0` and `READY`. If it fails, stop recognition, report the executable and missing requirements, show the installation guidance, and wait for authorization. Do not run a partial phase or switch interpreters to bypass failure. Revalidate with the same interpreter after the environment is fixed. The batch entry repeats this gate.

## Generate and review

1. Run `run_source_folder_to_smiles.py` with the source directory and established task name. It creates `workspace/YYYYMMDD_taskname_smiles/` in the task project. An existing same-date workspace or review is a collision: do not overwrite or invent an automatic suffix.
2. Treat batch exit `0` as candidate generation, not source confirmation. Normal first-pass recognition failures receive one `best-effort` retry. Recovered candidates remain `pending`. After two recognition attempts, stop automatic retries for unresolved rows and request human input.
3. Treat batch exit `2` as an input, environment, or execution error. Read the cause and evidence; do not label it a molecule failure. If a workspace exists, inspect it and use per-image recovery after resolving the cause; do not rerun the new-task command into it. Retry a verified transient execution error at most once, then report continued failure.
4. Inspect **every** image in `candidate_materials/comparisons/`. Compare atom identities, connectivity, bond orders, substituent positions, charges, stereochemistry, and fragments with the source. RDKit validity alone is insufficient. Printed abbreviations, salts, low-quality images, and photographs require care.
5. Record each actual comparison using `render_smiles.py review`. A match uses `--source-match yes` with evidence-based confidence and notes. A mismatch uses `--source-match no` and remains `failure`; ask about scientifically ambiguous corrections. Never set `success` without viewing the source and reverse structure.
6. Apply a corrected candidate with `chemdraw_fallback.py apply`, corrected SMILES, and optional matching MOL. This returns the row to `pending`; inspect the regenerated comparison and record a fresh review. A MOL inconsistent with supplied SMILES is rejected.
7. Finalize with `finalize_source_folder_results.py` only after all rows are terminal and required MOLs pass validation. Deliver the workbook, images, MOLs, readable review, and log. Distinguish confirmed and failed rows; keep unresolved structures out of downstream calculations.

## Required structures and publication gates

`candidate_materials/chemdraw/input/` must contain exactly one RDKit-readable `<image_id>.mol` per candidate. The batch generates it from the candidate or valid evidence seed. `prepare-all` can complete missing MOLs in an existing task; exit `1` names rows without a valid seed and is not a crash.

Do not invent an empty or placeholder MOL. With no valid seed, request a real manually drawn structure and apply it before finalizing. A valid candidate's MOL must represent the same structure. Rejected seeds remain under `chemdraw/failed/` and are not accepted downstream inputs.

The finalizer rejects pending rows, unattempted bounded recovery for unresolved first-pass failures, missing reverse images for successful rows, invalid or mismatched MOLs, and existing publication/staging directories. Do not bypass these gates by editing flags or reclassifying execution errors.

## Deliver a supplied master

When a master workbook is supplied, read [master handoff](references/master-handoff.md), check the involved IDs, and deliver a new `taskname_smiles.xlsx` alongside the native report. The original remains unchanged.

## Invariants

- `candidates.tsv` is the sole candidate-state table, with the eleven fields in the [runtime contract](references/runtime-contract.md#candidate-table). The Excel report uses its first five fields.
- Disagreeing text candidates are not accepted automatically. The existing model stage may propose a separate candidate; conflicting evidence must remain visible during review.
- Strict OCSR requires at least two agreeing image variants. Best-effort results remain review candidates.
- OCR, lookup, models, and RDKit are evidence, not truth. `success` requires valid SMILES, `rdkit_valid=true`, `source_match=yes`, and an existing reverse structure.
- Runtime data, logs, caches, and temporary files belong to the task project's `workspace/`; final deliverables belong to `review/`. Bundled examples are maintained snapshots, not writable task directories.
- Do not generate `.smi` files. Preserve IDs in handoffs and use accepted structures only under the next module's own input contract.

Use a compatible existing Conda, venv or other interpreter when available; Conda is optional. If the intended environment is unclear, ask the user. Read this release’s requirements on every invocation; after an authorized installation or update, rerun the same interpreter’s check. A newer upstream release alone is not a validation failure.
