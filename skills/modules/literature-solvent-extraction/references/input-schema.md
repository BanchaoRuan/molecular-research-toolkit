# Input Specification

This skill starts from a prepared Excel workbook and identified starting papers. It does not require an earlier toolkit skill. This document defines input fields; the scientific workflow and backfill decisions are defined in [SKILL.md](../SKILL.md).

## Workbook layout

Use the [master workbook layout and copy-delivery contract](master-handoff.md).
All thirteen columns must be present in their specified order and units. Ask about
a different schema instead of silently mapping or dropping fields. Keep original
inputs unchanged. Column InChIKey is required, but its value may be blank.

Every target must have a unique ID and complete SMILES. Skip targets missing SMILES
and report them; do not infer their identity. A source/structure conflict requires
clarification before processing that target.

## Data from Paper

Keep the template’s paper-data columns and units. Only the requested solvent findings are filled in this stage.

Every target row must provide at least one identifiable **ground-state oxidation or reduction potential**. When both are present, both are in scope unless the user specifies otherwise.

Read the direction, reported value, sign, units, and reference electrode or scale when supplied. Resolve unclear measurement or value assignments before research. Several reported values are acceptable when their relationship to the target is clear; ask when it is not.

Absorption/emission wavelengths, lifetimes, excited-state potentials, and other photophysical data are optional. Their absence is not a validation failure, and an excited-state potential alone cannot replace the required ground-state datum.

## Starting papers and source mapping

Before researching a target, the user must identify its starting paper through the prompt, attached material, DOI, or URL. A reference or source column inside the workbook is optional.

For one unambiguous starting paper, a single task-level designation is sufficient. With multiple papers, establish which IDs and, where necessary, which oxidation/reduction data belong to each paper. The user may explain this in ordinary language; a separate mapping file is not required.

Interpret a `Ref.` number only within its identified parent paper. Do not assume that every reference number or every datum in a row belongs to the same starting paper. If the mapping is incomplete, ask for the missing correspondence before processing affected targets.

A local PDF can serve as the starting paper. Use its verified bibliographic identity to recover a reliable source URL for review; do not fabricate a DOI or identify a paper from an ambiguous filename.

## Processing scope

Determine the target worksheet and any requested ID subset from the user's task. Inspect the workbook first; ask only if the intended table or scope remains unclear.

Default eligibility is based on `Solvent (AI-assisted)` cells that were blank **when the workbook was submitted**. Freeze that scope rather than reconsidering eligibility as results are written. A populated manual cell does not change the default eligibility of a blank AI cell.

A formula is existing cell content, including one that displays an empty string. Do not overwrite formulas or populated cells under the default fill-blanks request. Explicit requests to recheck or replace existing results must identify their intended scope.

The original workbook is the source of truth and remains unchanged. Keep all non-target content in a complete new solvent-stage copy.
