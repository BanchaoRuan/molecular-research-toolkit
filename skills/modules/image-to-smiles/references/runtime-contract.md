# Runtime contract

[Agent guide](../SKILL.md) · [Commands](commands.md)

## Inputs and identity

Supported extensions are `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.bmp`, and `.webp`. The batch enumerates files directly inside the input folder; it does not recurse or split figures. Each image must contain one complete target.

Filename stems become naturally sorted image IDs. Unicode-normalized, case-insensitive duplicates and sanitized-filename collisions are rejected before workspace creation. Do not reassign established IDs to other molecules.

Without `--task-name`, the input folder must end in `_single_molecule`; only that suffix is removed. `--run-date` accepts eight digits in `YYYYMMDD` form and defaults to the local date. The task identity is independent of module installation location.

## Directories

```text
<task-project>/
├── workspace/YYYYMMDD_taskname_smiles/
│   ├── candidates.tsv
│   ├── events.jsonl
│   ├── candidate_materials/
│   │   ├── normalized_images/
│   │   ├── ocr/
│   │   ├── model_predictions/
│   │   ├── reverse_structures/
│   │   ├── comparisons/
│   │   └── chemdraw/
│   │       ├── failed/
│   │       └── input/
│   ├── cache/
│   └── tmp/
└── review/YYYYMMDD_taskname_smiles/
    ├── taskname_smiles_report.xlsx
    ├── taskname_single_molecule_overview.png
    ├── taskname_single_molecule/
    ├── taskname_re_structure_overview.png
    ├── taskname_re_structure/
    ├── taskname_chemdraw/
    ├── taskname_chemdraw_input/
    ├── taskname_readable.md
    └── run_log.md
```

Runtime write paths inside the module are rejected. Sources stay read-only. Supported model caches and temporary directories are configured under the task workspace before inference. Existing workspace or review directories block a new task; no automatic `_2` is appended.

The finalizer builds `review_staging/` in the workspace, validates, and renames it into the review directory. Existing staging requires inspection rather than silent replacement.

## Candidate table

`candidates.tsv` is the sole candidate-state table, with exactly these ordered fields:

| Field | Meaning / values |
| --- | --- |
| `image_id` | Unique filename stem. |
| `smiles` | Canonical isomeric candidate SMILES; blank if absent. |
| `inchikey` | Identifier derived from the candidate when available. |
| `status` | `pending`, `success`, `failure`. |
| `confidence` | `pending`, `high`, `medium`, `low`; review assessment. |
| `source_match` | `pending`, `yes`, `no`. |
| `recognition_method` | Such as `text:cid`, `model:molscribe`, `chemdraw`, or `unresolved`. |
| `rdkit_valid` | `pending`, `true`, `false`. |
| `source_image_path` | Source for this candidate. |
| `reverse_structure_path` | Rendered candidate or clearly identified failure placeholder. |
| `notes` | Recognition, correction, and review evidence. |

The workbook uses the first five fields. The readable review includes remaining details and relative image paths. Runtime TSV/JSON can contain absolute paths; review and redact these before publishing examples.

## States

- Accepted text/model candidates remain `pending` until source comparison.
- A reviewed match becomes `success` with valid SMILES and an existing reverse image.
- A mismatch becomes `failure` with low confidence; it may retain a valid but rejected SMILES and seed MOL.
- `apply` resets status, confidence, and source match to `pending` and regenerates the comparison.
- A normal recognition failure gets at most one automatic recovery pass; a second failure needs human input.
- OCR, service/network, model execution, rendering, and other processing errors stop the task. PubChem `404` indicates no matching record and may proceed to other evidence routes.

No-valid-text and conflicting-text are distinct evidence outcomes. A model candidate proposed afterward still needs review against the source and conflicting evidence.

## MOL and finalization checks

Exactly one RDKit-readable `<image_id>.mol` is required per row. A valid candidate's MOL must canonicalize to the same structure. Missing, unreadable, extra, or mismatched MOLs block finalization.

With no valid seed, obtain a real manually drawn structure; never create placeholder MOLs. `taskname_chemdraw/` contains rejected seeds; `taskname_chemdraw_input/` holds required structures. Failed-row MOLs remain unresolved.

Finalization requires terminal rows, completed bounded recovery for unresolved first-pass failures, and existing reverse files for successful rows. It does not itself inspect source images. Never bypass it by editing TSV flags.

## Environment and limits

The declared Python version is **3.10**, not an unrestricted minimum. [requirements.txt](../requirements.txt) pins the current set; [dependencies.json](../dependencies.json) defines Python, system requirements, and package groups. Tesseract is a separate system prerequisite. The complete gate checks both model stacks even if an image needs only one.

Preflight checks declared package versions, Python and Tesseract versions, import availability, syntax, and a small RDKit/core smoke test. It does not import model engines, test remote services, or download checkpoints. `READY` is not a guarantee of inference success or platform-wide support.

Routing favors MolScribe for clean printed images and DECIMER hand-drawn mode for suitable camera images. Lined backgrounds and unsuitable photographs can be rejected. Routing is heuristic; no broad recognition benchmark or calibrated confidence is claimed.

`.smi` generation and Gaussian/HPC submission are outside this module.
