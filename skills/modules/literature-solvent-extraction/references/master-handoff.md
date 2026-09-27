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

## Solvent-stage delivery

Freeze the eligible blank AI-assisted cells at submission, or use an explicitly
requested existing-cell scope. Write supported results only to a new
`review/YYYYMMDD_taskname_data/taskname_solvent.xlsx`. Never change `Solvent (manual)`.
The user performs manual review in this same solvent-stage file; no renaming is needed.
Keep the independent `solvent_review.xlsx` and evidence in the `_solvent` review folder.
No earlier module or fixed phrase is required to invoke this skill.
