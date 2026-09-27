# Master workbook handoff

Use the user's submitted workbook as a read-only source. Never modify or rename it.
If a master is supplied, validate the toolkit template before editing. Preserve all
sheets, formulas, formats and non-target content in a complete new workbook.

The first table uses `fixed` at B2:E2 and `data from paper` at G2:N2.
B3:N3 contains, in order:

`ID`, `SMILES`, `InChIKey`, `Solvent (manual)`, `Solvent (AI-assisted)`,
`λmax (nm)`, `τ (μs)`, `E0,0 (eV)`, `Ered (V vs. SCE)`, `Eox (V vs. SCE)`,
`*Ered (V vs. SCE)`, `*Eox (V vs. SCE)`, `Refs.`

An InChIKey value may be blank; its column remains present. Do not guess a mapping
for a different layout. Ask about the necessary adjustment, and preserve the original.
Resolve task project, date and taskname from established context; do not infer a new
taskname from an already suffixed stage filename. The target sheet need not be named
Sheet1. A filename does not certify scientific review.

## Reviewed structures

If a master was supplied for this image task, deliver its structure-stage copy at
`review/YYYYMMDD_taskname_data/taskname_smiles.xlsx` in addition to the unchanged
native audit package. No master supplied means no forced master creation: offer the
package's create-table operation only when needed or requested.

Match `image_id` to `ID`, never row order. Check both SMILES and InChIKey only for
molecules involved in this report. Only source-reviewed `success` results qualify.
Fill both values together; keep a consistent existing value. For any inconsistent
existing value or formula, show the old and proposed pair and ask before replacement.
Do not mix incompatible old/new values. Leave unrelated rows untouched. Report-only
IDs in an existing master require user direction; do not silently append them.

When the user requests a new empty master, establish ID rows from the report;
failed or unreviewed rows retain IDs with blank structures. Preserve the five-column
native report, comparisons, source-review and MOL gates. Never export SMI here.
