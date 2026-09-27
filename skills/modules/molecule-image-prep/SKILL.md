---
name: molecule-image-prep
description: Prepare molecular structure images as visually checked, ID-named single-molecule PNGs with a source-mapping spreadsheet and overview. Use for image cropping and layout before a downstream molecular-image workflow.
---

# molecule-image-prep

Produce one checked PNG per target molecule, preserving its ID and source correspondence. Use the agent's visual judgment to select and inspect crops; the scripts handle pixels, filenames, mapping, and review packaging.

This component is maintained independently and installed with a parent skill. Resolve `<skill_dir>` from this file's directory and use the parent workflow's working project. Read [commands and data](references/commands.md) when running the scripts or inspecting a task.

## Establish the task

Retain all four groups of user-established information:

1. Task name.
2. ID prefix, number of digits, and starting ID.
3. Whether existing IDs must be retained and which molecule each ID represents.
4. Cropping and layout requirements, including treatment of surrounding text.

Reuse explicit information from the parent workflow or conversation. Ask only for missing or ambiguous values; do not require the user to repeat them or complete a prompt template. Determine source-image paths from the supplied folder or attachments using the host's normal file tools.

Accept one flat image folder or a list of image files. Supported inputs are single-frame PNG, JPEG, TIFF, BMP, and WebP. A source may contain one or several targets. PDF, HEIC, SVG, and other conversion workflows are outside this release.

## Preserve molecular identity

An ID denotes the same molecule across batches and downstream subskills. Reusing that ID for the same molecule is allowed; assigning it to a different molecule is not. Use the user's mapping and available task context to establish identity. Ask when that correspondence is uncertain.

Before initialization, collect the known occupied IDs relevant to the numbering scheme, including every ID to retain in this batch. Pass them with repeated `--reserve-id` options. New numbering skips all reserved IDs, even before their crops exist. Pass `--image-id` only for a retained molecule; omit it to allocate a new ID.

The scripts enforce one row and PNG per ID within a task. They do not infer chemical identity or maintain a global registry. Keep established IDs when correcting crops and pass them unchanged to later stages.

## Working directories and environment

Use the established task-project directories:

```text
<project_root>/workspace/YYYYMMDD_taskname_images/
<project_root>/review/YYYYMMDD_taskname_images/
```

The working project is separate from the installed subskill. Use `--project-root` explicitly when initializing, or run from that project's root. Keep attachment staging, inspection images, and other intermediate material in the project's workspace. Never write task materials into this module.

Use the interpreter provided by the parent installation. Before initializing, run:

```bash
python "<skill_dir>/scripts/validate_setup.py"
```

Continue when it exits `0` and prints `READY molecule-image-prep`. If it fails, report the checked interpreter and actual failure, resolve it through the parent's installation process, and rerun the check. Do not silently install dependencies or change environments. Initialization repeats this check.

`init` validates the inputs and required parameters, then stores byte-identical source snapshots in the task's `source_images/`. Original files and these source snapshots remain read-only during cropping. If the task's workspace or review directory already exists, resume the existing task instead of initializing again or adding a numbered suffix.

## Crop and inspect

Visually identify the requested targets and establish their source positions. Preserve a printed position label when available; otherwise choose a stable, unambiguous position ID within that source. The user does not need to supply crop coordinates or position IDs.

Use `crop` for a new target. Coordinates refer to the EXIF-oriented source image. The script crops existing pixels, optionally adds white padding or a white canvas, and saves a lossless RGB PNG. It does not resize the structure. Transparent input is composited on white.

Inspect every resulting PNG against its source. Check:

- All target atoms, bonds, charges, and stereochemical marks are visible.
- Neighboring structures are excluded and surrounding text follows the agreed rules.
- Separate components belonging to the target are retained; resolve uncertain salts or groupings before assigning identity.
- The requested targets are covered without missing or duplicate crops.

Choose an efficient inspection method appropriate to the images. Successful decoding or a plausible overview alone does not establish crop quality. This workflow uses visual selection, not OCR, OCSR, OpenCV, or automated chemical-structure detection, and does not reconstruct missing chemical information.

Use `recrop` to correct an existing target while preserving its ID, source image, and source position. Reapply the intended padding/canvas when recropping. If a review package already exists, a successful crop change moves it into the task's `review_history/`; inspect the updated result and rebuild the current review package. Perform mutations of one task sequentially.

## Build and deliver

After checking the intended targets, run `build_review.py`. The canonical mapping is `workspace/.../crop_review.tsv`, with exactly these seven fields:

```text
image_id
source_image_id
source_position_id
source_location
source_image_path
single_molecule_path
notes
```

The builder checks the mapping and PNG files and produces exactly:

```text
review/YYYYMMDD_taskname_images/
├── taskname_images_report.xlsx
├── single_molecule_overview.png
└── taskname_prepare_single_molecule/
    └── <image_id>.png
```

The spreadsheet retains the default Excel font and plain cells, with content-sized columns, wrapped text, and content-sized row heights calculated on each export. It uses the same seven fields and natural ID order as the canonical table. Source references are portable filenames; crop paths are relative to the task directory. The internal config retains original source locations for traceability.

Deliver the review directory and state any unresolved source limitations. Use the individual PNGs as downstream inputs; the overview is a preview. Pass the intended task name explicitly to the next subskill: deriving it from `taskname_prepare_single_molecule` can incorrectly produce `taskname_prepare`.

The package checks file consistency, while the agent checks molecular coverage and crop quality. Do not present a partial batch as complete. For interrupted operations or intended rebuilds, use the recovery guidance in [commands and data](references/commands.md).

Use a compatible existing Conda, venv or other interpreter when available; Conda is optional. If the intended environment is unclear, ask the user. Read this release’s requirements on every invocation; after an authorized installation or update, rerun the same interpreter’s check. A newer upstream release alone is not a validation failure.
