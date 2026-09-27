# Organize literature data

Use the existing master header and user-designated papers. This is a small operation
inside the package, callable directly in ordinary conversation, not a separate skill.

1. Identify the task project, taskname, input master, requested IDs/cells and starting
   paper(s). Reuse a clear existing mapping; ask about ambiguous compound labels.
2. Freeze the requested scope. By default, only initially blank G:N cells are eligible.
   Existing content and formulas need explicit user scope. Do not touch C:F.
3. Process only molecules with complete SMILES. Missing SMILES means skip that molecule;
   report it, do not reconstruct identity from its ID. Blank InChIKey is acceptable.
4. Follow the designated table and source material. Preserve raw values, signs, units,
   qualifiers, precision, reference numbers and original molecular structure. Do not
   perform unit/reference-electrode conversion to make a value fit a header; ask if it
   does not match. Do not substitute unrelated papers found by molecular name.
5. Keep row/cell provenance in workspace: ID, target column, value and raw value/unit,
   source file/DOI, page/table/compound label, notes and reason for any skipped finding.
   Use the original evidence statuses when useful: `filled`, `excluded_by_user`,
   `not_found`, `ambiguous`, `unreadable`, `source_unavailable`. They are workspace
   notes, never replacement scientific values in the master.
6. Deliver the complete `taskname_paper.xlsx` copy. Preserve all other workbook content.
   Summarize processed, skipped and unresolved targets; stop at the requested operation.

The optional adapter reads an agent-prepared JSON list of `{id, column, value, evidence}`.
The evidence string must identify the source location, not simply say “checked”.
A missing finding is omitted from the patch. Use native numeric values where the source
is numeric; preserve qualified values such as `2.70t; 2.98s` as literal text.
