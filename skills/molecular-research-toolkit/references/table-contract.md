# Master table contract

The first-sheet layout follows the agreed master, not an invented final-report schema.
The sheet name is not fixed. Group labels are `fixed` at B2:E2 and `data from paper`
at G2:N2. Leave F2 outside the fixed merge, as in the supplied layout.

| Column | Header | Responsible operation |
| --- | --- | --- |
| B | ID | Established identity; preserve across all stages |
| C | SMILES | Reviewed structure backfill |
| D | InChIKey | Filled with the corresponding reviewed SMILES |
| E | Solvent (manual) | User's scientific review |
| F | Solvent (AI-assisted) | Literature solvent skill |
| G | λmax (nm) | Paper data |
| H | τ (μs) | Paper data |
| I | E0,0 (eV) | Paper data |
| J | Ered (V vs. SCE) | Paper data |
| K | Eox (V vs. SCE) | Paper data |
| L | *Ered (V vs. SCE) | Paper data |
| M | *Eox (V vs. SCE) | Paper data |
| N | Refs. | Paper data |

Headers are row 3, records start at row 4. Do not rename units, reorder columns,
drop the InChIKey column, add calculation fields, or guess an unfamiliar layout.
InChIKey values may be blank for literature work. Complete SMILES are required for
processing a literature row. A formula counts as existing content even if it looks blank.

## Copies and names

| Requested operation | Accepted input | New deliverable |
| --- | --- | --- |
| Create table | No supplied master | `taskname.xlsx` |
| Fill reviewed structures | Current master + accepted image report | `taskname_smiles.xlsx` |
| Organize paper data | Current master + identified papers | `taskname_paper.xlsx` |
| Find electrochemical solvents | Current master + target redox data + papers | `taskname_solvent.xlsx` |
| User checks manual solvent | Solvent-stage table | Same `taskname_solvent.xlsx` |
| Export computation input | Reviewed current master + explicit IDs | `YYYYMMDD_taskname.smi` |

These are operation outputs, not mandatory prerequisites or evidence of approval.
Use the latest user-designated input for an independent call. Preserve the entire
workbook, including other tabs, formulas, drawings and non-target cells. Originals
uploaded in chat and originals in folders have the same protection.

Do not create stage files for stages that did not run. Existing output collisions
require user direction. The `_data` folder is separate from native `_images`, `_smiles`
and `_solvent` audit folders. No calculation result is written back in this release.

## Reference adapter

Agents may use their own spreadsheet tools under this contract. The optional
[`master_table.mjs`](../scripts/master_table.mjs) reuses the original artifact-tool
adapter, shows a JSON preview, and writes only with `--write`. Run `--help` for exact
options. Its copy-preservation step retains every unrelated XLSX ZIP member and only
changes the approved cell values in the selected sheet. It preserves formula text
and caches outside scope; recalculate in Excel when dependent formula results are needed.

`--overwrite-cell` is an execution record of actual user approval, not permission to
invent it. `--initialize-ids` is for a genuinely empty template only. The adapter
refuses unknown/duplicate IDs and unresolved structure conflicts. It does not perform
scientific source review itself. View the saved workbook and compare non-target
content before delivery. Signed workbooks and unfamiliar OOXML layouts need the agent's
native spreadsheet tools rather than a lossy conversion.
