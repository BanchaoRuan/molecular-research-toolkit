# Barkla-redox

Prepare Gaussian redox calculations on Barkla, extract G298, and inspect unfinished calculations for an independent coordinate-based retry.

The normal workflow and independent retry preparation are implemented and locally regression-tested. The published example includes three log-verified G298 results and monochrome, copyable demonstrations of the current-release workflow.

[Run example001](examples/example001/README.md) · [Environment requirements](ENVIRONMENT.md) · [Independent recovery](#independent-recovery)

## Layout

```text
barkla_redox/                     # Repository root
├── README.md
├── ENVIRONMENT.md                # Reference only; not uploaded
├── examples/
│   └── example001/
│       ├── README.md
│       ├── 20000101_example001.smi
│       ├── transcript.md
│       ├── output/G298.tsv
│       └── assets/                # Five monochrome SVG figures
└── barkla_redox/                  # Self-contained runtime directory
    ├── redox_customization.json
    └── scripts/
        ├── redox_batch.sh
        ├── make_com.py
        ├── make_slurm.py
        ├── extract_G298_batch.py
        └── recover_no_g298.py
```

Upload only `barkla_redox/` as the runtime. Supply your SMI input separately in its `inputs/` directory. README files, environment instructions, examples and figures remain outside that directory and are not runtime dependencies. Runtime data live in `calculations/` and `results/`. There is no skill descriptor, installer, graphical interface or additional core package.

### Deployment under a tools directory

Place the complete runtime at `<tools-directory>/barkla_redox/`. Its `inputs/`, `calculations/` and `results/` remain inside that same runtime root, following the existing layout. The tools directory is only a parent container for this and other tools; it is not a shared calculation root. Keep the existing preparation, submission and extraction commands. Do not add a separate work-directory interface or scan other tools' task directories.

The upload folder contains only the five scripts, required `redox_customization.json` and ignore rules. The outer [environment note](ENVIRONMENT.md) documents existing dependencies; it is not uploaded, installed or read by the scripts. Keep the established Barkla environment when it already meets these requirements. An example SMI is supplied separately as a task input when that example is actually run.

When updating an existing runtime, replace the scripts and configuration together at the same location, keeping `inputs/`, `calculations/` and `results/` intact. Back up your customized configuration before replacing it. Ordinary prepared tasks retain their inputs, saved state selection and extraction commands. Verified results-side XYZ copies from old interrupted preparations are preserved, including a partial temporary copy that matches a prefix of its frozen source. Unverified files are not accepted or deleted.

Historical one-off trial launchers may pin exact extractor/helper checksums. They need a separately reviewed, explicitly confirmed compatibility update before their old wrapper commands can run against new scripts. This is not automatic, and does not change COM files, logs, TSVs or submission records. Do not bypass checks, edit arbitrary hashes, mix script versions or relocate prepared tasks. Direct invocation of the extractor retains its original interface and directory rules.

For the example, use a batch name that has not already been prepared in that runtime. Generate COM and Slurm files on Barkla at their final location: they contain absolute runtime paths and must not be generated on another computer and then relocated.

## Customize for your own task

Edit `barkla_redox/redox_customization.json` before preparing a batch. The supplied configuration is an editable starting point, not a recommended calculation protocol or a list of the only supported methods. All existing method, basis, solvation, state and walltime choices are included; remove the entries you do not need or add suitable entries using the same structure. The default resource example is **4 CPU cores and `4000MW` of Gaussian memory**.

**Every option list must retain at least one entry. Every required field must remain present and valid.** Removing an option is allowed; removing a required key, leaving an empty list, or using a blank string is not. Numeric zero is valid for a neutral state's `charge_offset`, but CPU counts and multiplicities must be positive integers. The configuration is checked before any calculation files are created.

| Field | What you can customize |
| --- | --- |
| `functional_options` | Add or remove functional entries. `label` is used in the menu and directory name; `value` is the Gaussian keyword. |
| `basis_set_options` | Add or remove basis entries, keeping a safe filename label separate from the Gaussian value, such as `6-31Gd` and `6-31G(d)`. |
| `solvation_model_options` | Add or remove solvation routes. Every `route` must contain exactly one literal `{solvent}`, replaced by the solvent in each SMI record. |
| `state_options` | Add, remove or edit state entries. `charge_offset` is added to the formal charge represented by the input SMILES; `multiplicity` is the state's spin multiplicity, not an inferred value. Check these for your own molecules. |
| `walltime_options` | Add or remove time limits. `value` uses `D-HH:MM:SS`, such as `2-00:00:00` for 48 hours. |
| `route_keywords` | Edit Gaussian route keywords as appropriate. The supplied `opt freq` supports this workflow's geometry optimization and thermochemical extraction; arbitrary changes are not guaranteed to be compatible. |
| `cpu_cores`, `nodes`, `ntasks` | Edit positive integer resource counts to match your cluster allocation and calculation. This remains a shared-memory Gaussian workflow; changing counts does not add distributed execution support. |
| `gaussian_memory` | Set the Gaussian `%mem` value, for example `4000MW` or `32GB`. Use a positive integer immediately followed by `KB`, `MB`, `GB`, `TB`, `KW`, `MW`, `GW` or `TW`. Units are case-insensitive; generated inputs use uppercase units. |
| `partition` | Replace `troisi` if necessary with a partition you are authorized to use. The provided name is retained as an example, not as a partition available to every user. |

For example, to offer only B3LYP, replace just the `functional_options` list with:

```json
"functional_options": [
  {"label": "B3LYP", "value": "B3LYP"}
]
```

This is a fragment of the full configuration, not a complete replacement file. Keep the other required fields. Standard JSON does not allow comments or trailing commas. Method-option labels must be unique within their list, contain only letters, digits, single underscores or hyphens, start with a letter or digit, and not contain `__`. State labels use lowercase letters, digits, underscores or hyphens, start with a lowercase letter, and cannot be `overall`.

Changing the configuration affects future preparation only; it does not rewrite prepared COM files, alter saved state selections, or update existing results. The program validates structure and syntax, not the scientific suitability of an arbitrary functional, basis, solvent, charge or spin assignment.

### Memory and cluster settings

`gaussian_memory` controls Gaussian's memory setting; it does **not** request additional scheduler memory. Generated Slurm files retain their existing behavior and do not add `--mem` or `--mem-per-cpu`. Check the memory actually available to the job and leave room for other process overhead. Changing CPU counts can also change the memory allocation on clusters configured with per-CPU memory defaults; that policy is cluster-specific, as described in the [Slurm memory options](https://slurm.schedmd.com/sbatch.html#OPT_mem-per-cpu).

The example values are not a guarantee of sufficient memory for every molecule or partition. Gaussian/Open Babel module names and the Gaussian launch setup remain in the scripts; this configuration is not a general-purpose cluster-environment installer.

## Existing workflow

An input named `YYYYMMDD_taskname.smi` contains exactly three whitespace-separated fields per molecule:

```text
SMILES molecule_id solvent
```

This describes the columns; **do not include a header row**. The input filename does not select a charge state.

From the runtime directory, prepare an input using:

```bash
bash scripts/redox_batch.sh inputs/YYYYMMDD_taskname.smi
```

Select the functional, basis set and solvation model; choose the nonempty set of states; select walltime and confirm the preview. An existing batch/method combination is rejected before the state questions. Preparing files does not submit jobs. Submission remains a separate invocation of the generated `submit/submit.sh`, after checking the selected jobs.

Method directories retain the existing `functional__basis_set__solvation_model` format. Each molecule has only the selected state inputs. The current resource values, including Gaussian memory, are displayed in the confirmation preview and recorded in `preparation.log`. Gaussian initialization, coordinate generation, submission locking and failure reporting retain the existing behavior. Manual coordinate edits to a COM file before its first submission remain supported.

Extract results for a prepared method using:

```bash
python3 scripts/extract_G298_batch.py calculations/YYYYMMDD_taskname/functional__basis_set__solvation_model
```

Extraction overwrites that batch's per-molecule `G298.tsv` files and can be repeated while calculations are running. It reads the recorded state selection, not the current global configuration. The scientific extraction rules are unchanged: the first five frequencies must exist, be finite and be strictly positive; the existing G298 and normal-termination checks remain in place. Unselected states are not reported as missing.

If a log exists but has no G298, extraction writes `NA` in that state's energy column, `no_G298` in its status column and `needs_check` as the overall status. A missing log is recorded as `missing_log` instead. Tables are refreshed only when extraction is invoked, not automatically when a job finishes. The inherited terminal heading `Needs manual check` lists all non-complete states; it is not the recovery script's final `manual` classification.

New results directories no longer receive an initial XYZ copy. Calculation-side frozen coordinates remain available. Existing tasks and their XYZ files are not altered by this snapshot.

## Independent recovery

When extraction observes `no_G298`, it prints an optional command for `recover_no_g298.py`. The default command only reads and reports evidence. It does not create a retry, modify a TSV, submit work or start monitoring. Recovery is optional: a missing G298 does not mean a retry is wanted or safe.

```bash
python3 scripts/recover_no_g298.py calculations/YYYYMMDD_taskname/functional__basis_set__solvation_model
```

Optional `--state oxidized`, `--ids example001` and `--json` arguments narrow or format the preview. State labels come from the source task, not the current configuration. For recorded jobs, recovery checks `squeue` and then `sacct`; absence from the queue alone is not proof of completion. Running, pending or transitional jobs are held, and missing terminal evidence is reported as `unknown`.

`--logs-finished` is an explicit user attestation that the source jobs really have finished, including offline copies. Use it only after verifying that fact. It never overrides a job observed in a live scheduler state. The extractor may continue to run repeatedly without preparing any retry.

An active or unknown job does not by itself stop inspection of the other jobs: finished, eligible jobs can still proceed. An unfinished optimization in a terminated job is different from a job that is still running. Confirming `--prepare` fixes each source batch/method/state's retry subset permanently; wait before confirming if additional jobs should later be included in the same retry batch.

SCF failure is not a blanket exclusion: earlier complete, valid evaluations remain inspectable. Recognized PCM matrix, CPHF and unsupported-basis failures are classified as other faults. Unknown error messages are retained as evidence rather than automatically excluding an otherwise valid candidate. A complete point requires its own coordinates, converged SCF density evidence, energy and all four optimization metrics. An evaluated initial geometry is explicitly distinguished from an improved geometry. A `manual` result means that a safe automatic retry could not be established from the supported evidence, not that recovery is impossible; conservative false negatives remain possible.

For a finished source task, inspect the preview and then request preparation:

```bash
python3 scripts/recover_no_g298.py calculations/YYYYMMDD_taskname/functional__basis_set__solvation_model --prepare
```

Use the same optional filters, and `--logs-finished` only when needed and justified. Review the eligible jobs and their retained resources, then answer `y` to the single confirmation. Cancellation writes nothing. `--json` remains read-only and cannot be combined with `--prepare`.

| Preview status | Meaning |
| --- | --- |
| `ready` | Finished job, validated source parameters, usable coordinates and matching molecular connectivity. Eligible for the confirmed retry. |
| `wait` / `unknown` | Active job or insufficient lifecycle evidence. No retry is prepared. |
| `other_fault` | Recognized PCM matrix, CPHF or unsupported-basis fault. Requires separate handling. |
| `manual` / `missing_log` | Ambiguous evidence, incompatible input, missing coordinates, changed connectivity or no source log. Other eligible jobs can still proceed. |
| `not_no_G298` | G298 is already present; outside this recovery workflow. |

### Coordinate selection and validation

An explicitly completed optimization uses its associated converged geometry. Otherwise, the selector considers the whole sequence of complete evaluations. It uses the latest reliable point for an improving trajectory, or ranks candidates in a reliable historical/pre-oscillation region. It does not use a fixed step-count threshold or a fixed number of steps back. A single fully evaluated initial geometry can be tried once, but is not described as improved.

The score is the largest of the four value/threshold ratios printed by Gaussian, with energy and the later step as tie-breakers. Trend comparison uses energy and the geometric mean of the two force ratios. A force-converged endpoint may supersede a historical score minimum when its energy is lower by more than `1e-6` Hartree; this is a ranking tolerance, not a change to Gaussian convergence. Repeated energy and metrics must also have recurring interatomic distances before being called a cycle. Backtracked phase-consistent regions are labelled as evidence, not proof of a unique oscillation onset. Stationary or contradictory evidence without a reliable candidate remains manual. These heuristics do not guarantee convergence on unseen molecules.

The source COM, logged route, saved method/solvent/state and Slurm resources must agree. Self-contained Cartesian inputs are supported; extra basis sections, checkpoint-dependent inputs, custom Slurm directives and ambiguous optimization sequences require manual review. Missing or failed SCF density evidence cannot be repaired by an isolated `SCF Done` line.

Open Babel checks explicit-hydrogen composition and connectivity against the original SMI. It is reused from normal preparation (`openbabel/3.1.1-gcc14.2.0` when not already on PATH); RDKit is not required on Barkla. No 3D generation, conformer search or geometry optimization occurs during recovery. Connectivity comparison ignores bond order, electronic charge and stereochemistry; electron-count/spin parity is checked separately. This is a safety check, not proof of a minimum or stereochemical correctness. Unsupported connectivity cases are held for review.

### New batch, unchanged extraction

Preparation creates a standard, independent batch, grouped by source batch, method and one state. For example:

```text
20000101_example001_B3LYP__6-31Gd__IEFPCM_oxidized_retry.smi
```

The SMI remains three columns with the original molecule IDs, SMILES and solvents. It supplies identity and extractor compatibility, **not new coordinate generation**. Retry COM coordinates come directly from a validated log point. No separate retry XYZ is produced. `coordinates/manifest.json` records the COM and source-coordinate provenance; it does not pretend that conformers or an initial geometry were regenerated. Detailed evidence is saved in the new method's `retry_provenance.json`.

Original routes, functional, basis, solvent, charge, multiplicity and source COM/Slurm resources are retained, even if the current configuration has different defaults. This workflow does not add XQC, change optimization settings or silently tune resources. The new results directory starts empty and later gets its own per-molecule TSVs. Source tasks and their TSVs are never backfilled or rewritten.

The generated paths follow the same convention:

```text
inputs/<new_batch>.smi
calculations/<new_batch>/<new_batch>.smi
calculations/<new_batch>/coordinates/manifest.json
calculations/<new_batch>/<method>/preparation.log
calculations/<new_batch>/<method>/retry_provenance.json
calculations/<new_batch>/<method>/work/<ID>/<state>.com
calculations/<new_batch>/<method>/work/<ID>/<state>.slurm
calculations/<new_batch>/<method>/submit/submit.sh
results/<new_batch>/<method>/<ID>/
```

Preparation prints the exact new submission path. Review COM files and run that generated `submit.sh` separately when ready. **Do not run `redox_batch.sh` on the generated retry SMI**: the retry has already been prepared from log coordinates. Use `extract_G298_batch.py` with the new calculation method directory to extract its own results, exactly as for a normal batch. New retry batches have also been round-trip tested with the previous extractor.

Only one retry batch may be prepared for a source batch/method/state. The confirmed subset is final: there is no state append, `retry2`, recursive recovery of a retry or automatic submission. Source hashes and job lifecycle are rechecked before publication. Existing targets, concurrent preparation and changed sources are refused. Interrupted `.preparing` stages or partially published artifacts are retained for inspection and are not silently overwritten; review them before any manual cleanup.

## Example and validation

[example001](examples/example001/README.md) contains a three-column SMI, exact run commands, five monochrome SVG figures, a copyable transcript and the verified 22-column G298 table. The three states are complete according to the current extractor's result-reading functions. Only the public molecule ID changes; SMILES, solvent, numerical results and status fields are preserved.

The figures are re-typeset current-release usage examples. Commands and resource previews follow the release defaults; the numerical results come from supplied Gaussian logs, not a fresh run with those defaults. The returned results allow parser verification, not a full CLI replay of the original prepared task tree. No additional Gaussian or scheduler execution is claimed.

Local validation covers all seven nonempty state combinations, saved state parameters, cancellation without output, duplicate preparation, manual COM coordinate edits, cross-version interrupted preparation, submission locks, partial submission failures and Gaussian module/profile initialization. Chemistry and scheduler calls in the end-to-end workflow tests are mocked. Recovery reproduces 92 reviewed selections and 94 completed-optimization geometries from archived logs; an independent local chemistry oracle accepts the reviewed restart geometries and rejects the known bad-connectivity case. New one-state retry batches produce the same TSV with old and new extractors. No real Open Babel/Gaussian/Slurm recovery run is claimed by those local tests. Private fixtures, molecular identifiers and transcripts are not public assets.

The validation approach uses real-log regression fixtures, as described by [cclib](https://cclib.github.io/development.html#regression-tests). Inspection is kept separate from corrective action, a useful pattern in [Custodian's Gaussian handler](https://github.com/materialsproject/custodian/blob/master/src/custodian/gaussian/handlers.py); its changes to Gaussian settings are not adopted here.

## Repository boundary

This directory is the repository itself: maintain the README, environment note, example and runtime together here. There is no separate presentation repository, generated export or preview copy to synchronize. Upload only the inner `barkla_redox/` to Barkla; its five scripts and configuration are the runtime dependencies. Finder metadata and local caches are not required files.

Do not publish calculation directories, raw Gaussian logs, checkpoint files, scheduler records, private test fixtures or local validation transcripts. Generated COM, Slurm and preparation files can contain account names and absolute paths even though the source code is portable. Keep those files private for verification. Ignore rules are a convenience, not a privacy audit, and do not remove files already present in Git history.

Public example figures may be privacy-reviewed captures or clearly labelled re-typeset demonstrations. Preserve checked numerical results, status labels and diagnostic messages; make any current-release presentation settings explicit. Re-typeset figures must not be described as captures of an execution that did not occur. Public result tables must be checked against the supplied logs. Keep account names, personal paths, email addresses, terminal titles and unrelated jobs out of all public assets.

The text-first demonstration format follows the documentation patterns of [VHS](https://github.com/charmbracelet/vhs) and [bat](https://github.com/sharkdp/bat): focused terminal examples with copyable commands. The SVG figures are generated locally from reviewed text; neither project is a runtime dependency.
