# Reviewed SMI export

Keep the original manage-data-auto scientific rules. The user must select IDs explicitly
and confirm reviewed structures and manual solvent choices. Never export every row by
default or copy AI solvents to the manual column automatically.

Every selected ID must be unique and present. Validate all selected SMILES and solvents
before writing; if any fails, produce no partial SMI. Match by ID, not row position.

- One fragment: preserve the exact reviewed SMILES.
- Dot-separated fragments: retain the unique fragment with an explicit net-positive
  formal charge. If no fragment or more than one qualifies, stop and ask. Do not infer
  a charge, neutralize, canonicalize, or change the full workbook SMILES.
- Resolve manual solvents to the bundled Gaussian 16 C.01 whitelist. Strip only the
  established leading descriptors such as dry/anhydrous. Unclear names, aliases and
  mixtures require source/identity clarification. A task-local `--resolve RAW=NAME`
  records a verified identity, not a permanent alias database or a guessed mixture.
- The output is `YYYYMMDD_taskname.smi`: `SMILES ID gaussian_keyword`, one molecule per
  line, no header, exactly three whitespace-separated fields. Preserve table order.

The optional `build_smi.mjs` adapter accepts `--report`, repeated `--id`, and `--reviewed`.
That last flag records actual user review; it is not a substitute for asking. It reads
only `Solvent (manual)`, never fills it, and never overwrites an existing output.
Run `--help` for arguments. Its conversion summary records removed fragments and solvent
mapping decisions; keep this with the task workspace evidence.

Upload the SMI separately from the [Barkla runtime](https://github.com/BanchaoRuan/molecular-research-toolkit/tree/main/tools/barkla_redox).
Preparing inputs and submitting jobs are separate actions. This release ends with Barkla's
per-molecule `G298.tsv`, without downstream table backfill.
