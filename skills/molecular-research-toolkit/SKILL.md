---
name: molecular-research-toolkit
description: Use the molecular-research-toolkit bundle to create a molecular master table, fill reviewed SMILES and InChIKey, organize paper data, or export selected reviewed molecules as Gaussian-ready SMI. Also use for toolkit setup and handoffs between directly callable image preparation, image-to-SMILES and electrochemical solvent skills. Any one operation may be requested on its own.
---

# Molecular Research Toolkit

This entry packages three directly callable skills and small table/file operations.
It does not require a complete sequence or replace the scientific rules in the modules.
Choose only the operation implied by the user's request; equivalent natural wording is
sufficient. Reuse established project, taskname, IDs, inputs, environment and permissions.
Ask only about missing or ambiguous information needed for this operation.

## Select the operation

| User intent | Action |
| --- | --- |
| Crop structure figures into individual molecules | Call `molecule-image-prep` directly. |
| Recognize or review SMILES from single-molecule images | Call `image-to-smiles` directly. |
| Trace solvents behind ground-state redox data | Call `literature-solvent-extraction` directly. |
| Start a master without an existing workbook | Copy the empty template as `taskname.xlsx`. |
| Put reviewed image results into a supplied master | Follow the structure-pair operation below. |
| Complete literature values in a table | Follow the paper-data operation below. |
| Export particular reviewed molecules for Barkla | Follow the SMI operation below. |

Resolve modules by their registered names. In the download, their full folders are
under `../modules/`; after generic directory installation they are sibling skill folders.
Read the chosen module's SKILL.md. No earlier skill is required when its inputs exist.
Keep the explicit taskname across the crop-to-recognition handoff.

## Check before work

Read [environment guidance](references/environment.md). Check the actual interpreter
against the selected module's released files before creating a task. Use
`scripts/environment.py check --component <module-name>` with that interpreter, or
its native validator. A failed check stops the operation: explain the executable,
missing/mismatched versions and repair instructions; obtain permission before installation.
Reuse a compatible environment. Ask if the user says an environment exists but its
location or suitability is uncertain. Conda is optional. Recheck after any repair.

Table/literature operations may use the agent's existing spreadsheet and source-reading
tools. Verify those tools are available; do not install an OCSR stack just to edit a table.
The optional existing Node adapter requires its provided `@oai/artifact-tool` runtime
and Python for copy preservation. It is not a mandatory Excel engine for other agents.

## Preserve the master

Read [table contract](references/table-contract.md) before any table operation.
The supplied workbook is read-only. Deliver a complete copy with only the operation's
authorized cells changed. Preserve other sheets, formulas, manual values and formatting.
Use the agreed thirteen-column template, even for a user-provided master; ask about a
nonconforming schema rather than silently remapping it. If no master is provided and
the user wants one, use `assets/master_template.xlsx`. Do not force master creation for
an images-only task.

Use `<task-project>/review/YYYYMMDD_taskname_data/`. Only create outputs for executed
operations: `taskname.xlsx`, `taskname_smiles.xlsx`, `taskname_paper.xlsx`, or
`taskname_solvent.xlsx`. Do not overwrite an existing deliverable or guess a numbered
suffix. Human solvent review uses the same solvent-stage name. Keep native module
reports and their filenames unchanged. Runtime notes and source locators go in the
corresponding task workspace, never in this installed folder.

## Structure pairs

Match the source-reviewed image report's `image_id` to master `ID`. Process only the
molecules involved in that report. For each `success`, check both SMILES and InChIKey:
fill empty values, retain consistent values, and ask before replacing conflicting
existing values or formulas. Show the complete old/new pair; never mix incompatible
values. Ignore unrelated rows. Failed/unreviewed candidates are ineligible.
For a newly requested empty master, establish report IDs and leave failed structures
blank. Do not silently append report-only IDs to an existing master.

## Paper data

Process only rows with complete SMILES and an unambiguous identity-to-starting-paper
mapping. Skip missing/incomplete SMILES and report the reason. InChIKey values may be
blank. Read the supplied papers, tables, SI and source notes under the original
[literature rules](references/literature-data.md). Default to paper-data cells blank
at submission; an existing value or formula needs explicit scope. Preserve the source's
signs, precision, units, reference scale and compound correspondence. Do not convert
units, infer missing measurements, substitute papers, or fill unresolved values with
status text. Record provenance outside the master in workspace.

## SMI export

Ask for explicit IDs and confirmation that their structures and `Solvent (manual)`
values have been reviewed. A stage name or nonempty cell is not proof of review.
Use [SMI rules](references/smi.md), preserving the established fragment and Gaussian
solvent rules. Validate every selected row before writing anything. The output is
`YYYYMMDD_taskname.smi`, exactly three headerless fields per line. Do not generate SMI
inside the image-recognition module. Do not edit the full workbook SMILES when selecting
a computational fragment.

## Finish at the requested boundary

Report delivered paths, changed scope, skipped/conflicting items and remaining user
review. Do not automatically run the next skill or log into Barkla. The standalone
Barkla tools prepare jobs separately from submission. Real submission requires its
own scope preview and user confirmation. This release ends with per-molecule `G298.tsv`
files generated on Barkla; result download, master backfill and regression are outside
this version.
