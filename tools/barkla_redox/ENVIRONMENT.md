# Runtime environment

Use the existing working Barkla environment. This file documents the current requirements; it does not install software, create a Conda environment, change shell startup files or alter module and scheduler settings. No environment change is needed if the existing workflow already meets these requirements.

## Dependencies by operation

| Operation | Requirements |
| --- | --- |
| Prepare an ordinary SMI batch | Bash, Python 3 and standard Unix utilities. Generating new shared coordinates also requires Environment Modules and Open Babel (`obabel` and `obminimize`). |
| Submit prepared jobs | Bash and Slurm `sbatch`, with permission to submit to the configured partition. |
| Run a Gaussian job | A Linux compute node, the existing Gaussian 16 module/profile, the `g16` executable, authorized Gaussian access and writable scratch storage. |
| Extract G298 | Python 3 and the original prepared task tree with its available logs. Gaussian, Open Babel and scheduler commands are not needed for extraction. |
| Preview or prepare a retry | Python 3 on a POSIX system, including its standard-library `fcntl` locking support. Eligible coordinate candidates also need Open Babel for composition/connectivity checks. Recorded jobs are checked using Slurm `squeue` and `sacct`. |

The scripts use standard-library interfaces introduced in Python 3.8, including `shlex.join`, `math.dist` and `Path.unlink(missing_ok=...)`; use Python 3.8 or later. A complete Python-version compatibility matrix has not been tested. There are no third-party Python package requirements.

## Existing Barkla setup

- **Open Babel:** ordinary coordinate generation loads `openbabel/3.1.1-gcc14.2.0`. Recovery uses `obabel` already on PATH, or tries the same module through Bash if it is absent. The `module` command must be available to that shell when loading is needed. Recovery does not generate conformers or optimize coordinates.
- **Gaussian:** generated jobs load `gaussian/16`, read `g16root` from that module and initialize `$g16root/g16/bsd/g16.profile`. The existing initialization and strict-mode handling are unchanged.
- **Slurm:** jobs use the existing partition and resource settings. Slurm supplies `SLURM_CPUS_PER_TASK` and `SLURM_JOB_ID`; the job also expects `USER`. These values should not be fabricated manually.
- **Finished-job evidence:** absence from `squeue` alone does not prove completion. Without reliable accounting evidence, recovery holds the affected job as `unknown`. For verified finished jobs, including offline copies, `--logs-finished` records explicit user confirmation; it never overrides a job observed as still active.

Module names and the Gaussian launch setup remain in the scripts. This is a Barkla workflow, not an automatic environment installer or a generic cluster adapter.

## Resources, storage and task files

- The supplied example defaults are 4 CPU cores and `4000MW` of Gaussian memory. Keep `redox_customization.json` valid and each option list nonempty. The supplied `troisi` partition requires appropriate access.
- `gaussian_memory` sets Gaussian `%mem`; it does not add Slurm `--mem` or `--mem-per-cpu`. The actual job allocation must cover Gaussian memory and process overhead. Do not infer available memory from the configured value alone.
- Recovery retains each source COM/Slurm resource setting; changing the current defaults does not rewrite old tasks or their retries.
- Keep the runtime at its final location under the tools directory. Its `inputs/`, `calculations/` and `results/` need the appropriate read/write permissions. Preparation uses filesystem locks and same-filesystem renames. Do not relocate already-prepared jobs: their COM and Slurm files contain absolute paths.
- Gaussian scratch uses `/tmp/${USER}/${SLURM_JOB_ID}` on the compute node and needs sufficient space. Submission uses a temporary directory under `TMPDIR`, or `/tmp` when it is unset.
- Keep the prepared task tree intact: frozen batch SMI, coordinate manifest, `preparation.log`, COM/Slurm inputs, submission files and the corresponding result directories/logs. An isolated Gaussian log is not enough to reconstruct a compatible task safely.

## Not required

No RDKit, NumPy, pandas, pip installation, Conda activation, Git command, network service or AI API is required by the runtime. Local development checks that used RDKit do not make it a Barkla dependency. Native Windows is not a supported recovery environment because recovery uses POSIX file locking.

The README, this environment note, example inputs and presentation assets stay outside `barkla_redox/`. Upload only the runtime scripts and required configuration. The runtime directory is also the task root for inputs, calculations and results; the scripts do not read this document.

## Verification boundary

The published example includes results verified against supplied Gaussian logs. Its commands and resource preview use the current release defaults; those defaults do not rewrite the supplied logs. Local regression checks do not prove scheduler allocation or a new Gaussian execution. Keep the established environment when it works; investigate a concrete missing dependency or error before changing it.
