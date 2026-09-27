# Commands and data

Resolve `<skill_dir>` to this module and `<project_root>` to the working project supplied by the parent workflow. Commands use the same Python interpreter as the environment check. Quote paths that contain spaces.

## Initialize

For a folder:

```bash
python "<skill_dir>/scripts/crops_molecules.py" init "/path/to/images" \
  --project-root "<project_root>" \
  --task-name sample-set \
  --id-prefix IMG --id-width 3 --start-id IMG001 \
  --has-existing-ids no \
  --crop-layout-rules "Keep complete structures, omit captions, add white padding."
```

For attachments saved as local files, replace the single folder argument with their file paths. A folder must contain only the intended images; scanning is not recursive. Hidden entries and operating-system metadata are ignored. Source filename stems must be unique after Unicode and case normalization, including across attachments.

The four business information groups in [SKILL.md](../SKILL.md#establish-the-task) are required. The example values above are illustrative, not defaults. `--run-date YYYYMMDD` is optional and otherwise uses today's local date.

ID options:

| Option | Meaning |
|---|---|
| `--id-prefix` | Prefix for newly allocated IDs, such as `IMG` |
| `--id-width` | Number of numeric digits, from 1 to 12 |
| `--start-id` | Prefix plus exactly that many digits; allocation starts here |
| `--has-existing-ids yes/no` | Whether this batch contains molecules whose IDs must be retained |
| `--reserve-id ID` | Repeat for each known occupied ID to exclude from new numbering |

When retaining IDs, list all of them at initialization, including targets that will be cropped later. For example, `--has-existing-ids yes --reserve-id IMG001 --reserve-id IMG003` makes the first newly allocated ID `IMG002` when starting at `IMG001`. Cropping the retained `IMG001` later does not change this allocation. A batch containing only new targets can still use `--has-existing-ids no --reserve-id ...` to avoid known IDs used elsewhere.

Output IDs use ASCII letters, digits, underscores, and hyphens, begin with a letter or digit, and cannot be reserved operating-system filenames. Retained IDs need not match the new-numbering prefix or width. IDs differing only in case are treated as the same ID.

Initialization creates:

```text
workspace/YYYYMMDD_sample-set_images/
├── task_config.json
├── source_images/
│   └── <original source filenames>
├── crop_review.tsv
├── sample-set_prepare_single_molecule/
└── tmp/
```

Source snapshots preserve the original bytes and filenames. `task_config.json` records the established parameters, reserved IDs, and original source paths. It is internal task context, not a review deliverable.

To inspect source dimensions without creating a task:

```bash
python "<skill_dir>/scripts/scan_images.py" "/path/to/images"
```

## Crop a target

```bash
python "<skill_dir>/scripts/crops_molecules.py" crop \
  "<project_root>/workspace/YYYYMMDD_sample-set_images" \
  --source-image-id figure1 \
  --source-position-id a \
  --source-location top-left \
  --box 20 40 320 280 \
  --padding 12 12 12 12 \
  --notes "Printed label a; caption excluded."
```

`--source-image-id` must exactly match a scanned filename stem. Coordinates are measured in the EXIF-oriented source image with the origin at its top-left. The box order is left, top, right, bottom; right and bottom are exclusive. Padding uses the same order and defaults to zero.

For a retained molecule, add `--image-id IMG001`. That ID must have been reserved at initialization with `--has-existing-ids yes`. For a new molecule, omit `--image-id`; allocation skips every reserved or already recorded ID. A repeated ID or source-image/position pair is rejected.

Use `--canvas WIDTH HEIGHT` for a fixed white canvas. The padded crop must fit at its original pixel size. It is centered unless `--paste-offset X Y` is supplied.

## Correct a crop

```bash
python "<skill_dir>/scripts/crops_molecules.py" recrop \
  "<project_root>/workspace/YYYYMMDD_sample-set_images" \
  --image-id IMG001 \
  --box 16 32 332 292 \
  --padding 12 12 12 12 \
  --notes "Expanded to retain the complete charge label."
```

This replaces the generated PNG and updates its existing mapping row. The source image, source position, and molecule ID remain unchanged. Omitted notes and source location retain their previous values; `--notes ""` clears the notes. Box, padding, canvas, and offset describe the replacement output, so supply the intended layout again.

If a current review exists, a successful crop change archives it under `workspace/.../review_history/<timestamp>/`. The active review is withdrawn until rebuilt, preventing an earlier crop from being mistaken for the corrected result. Existing originals and historical review files are preserved.

## Build or rebuild the review

After visual inspection:

```bash
python "<skill_dir>/scripts/build_review.py" \
  "<project_root>/workspace/YYYYMMDD_sample-set_images"
```

`--overview-columns N` changes the preview grid (default: 5). Individual PNG pixels are unchanged. Use `--replace` only when intentionally rebuilding an existing review; the previous bundle is retained in workspace history. The builder stages a complete bundle inside the task before publishing it.

## Mapping fields

The UTF-8 tab-separated `crop_review.tsv` is the canonical mapping. Its exact column order is:

| Field | Content |
|---|---|
| `image_id` | Stable molecule ID and output PNG filename stem |
| `source_image_id` | Source filename stem |
| `source_position_id` | Printed target label, or a stable position ID within that source |
| `source_location` | One of the relative-position values below |
| `source_image_path` | Source filename, found in `source_images/` or among the original inputs |
| `single_molecule_path` | Task-relative path, such as `sample-set_prepare_single_molecule/IMG001.png` |
| `notes` | Relevant crop, label, identity, or source limitations; may be empty |

`source_location` describes the target's position, not its pixel coordinates. Use exactly one of:

```text
top-left       top-center       top-right
middle-left    center           middle-right
bottom-left    bottom-center    bottom-right

far-left       left-center      center      right-center      far-right
```

Rows are naturally ordered by ID. The report's `crop_review` worksheet reproduces the table as literal text, including values that start with `=`. It retains the default Excel font and plain cells. On each export, column widths are estimated from the headers and contents, up to 60 character units; longer text wraps, and row heights are estimated from the resulting line count. Explicit line breaks and wide Unicode characters are included in the calculation. Excel's maximum row height still applies to exceptionally long text, whose full value remains in the cell. Neither absolute original source paths nor internal config fields are published in the report.

## Resume and failures

Resume an initialized task by passing its existing workspace path to `crop`, `recrop`, or the builder. Initialization refuses an existing workspace or review and does not create alternate numbered directories. This release starts new tasks with its own config format; older task folders are not migrated automatically.

Scan/crop/build commands exit `0` on success and `2` on an input or execution error. The standalone environment check exits `1` on failure. Read the error before retrying; failures do not establish a completed batch.

Caught crop-write failures attempt to restore the previous image, table, and review. A process kill or filesystem failure can still interrupt an operation. Inspect the existing table and files in that case. Missing or unmapped result files block further processing and publication; `recrop` can restore its own missing target PNG from the source snapshot. Do not silently discard unmatched files or overwrite unrelated targets.

Failed review generation leaves diagnostic staging files in the task's `tmp/` and preserves any current review. Fix the reported problem and retry; a new staging directory is used. Runtime temporary files, including spreadsheet scratch files, stay within the task workspace.
