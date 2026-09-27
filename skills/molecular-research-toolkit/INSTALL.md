# Installation and updates

Install the skill bundle, the Barkla tools, or both. Your agent selects its supported
skill directory and checks the environment for the operation you request. You do not
need to install recognition models just to organize a table or trace literature.

## 1. Start from an empty computer

1. Install your preferred AI agent and an Excel-compatible workbook viewer. Use the
   agent's own file, spreadsheet and browser capabilities for literature/table work.
2. Download the [skill ZIP](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/molecular-research-toolkit-skills.zip)
   and extract it. For cluster work, separately download the
   [Barkla ZIP](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/barkla-redox.zip).
   You can also use the complete project ZIP. The default links follow `main`; keep
   the downloaded ZIP and checksum, or choose a published version tag for repeatable use.
3. If local image processing is needed, install [Miniforge](https://github.com/conda-forge/miniforge#download)
   for your operating system and CPU. This supplies Conda and Python; no Git or Node
   install is needed for the standard Python modules. A compatible existing environment
   can be reused instead.

| Computer | From-zero entry |
| --- | --- |
| macOS | Choose the macOS arm64 installer for Apple Silicon, or x86_64 for Intel. Run the downloaded installer and follow its prompts. Open a fresh terminal. |
| Linux | Choose the installer matching your CPU and run it with Bash. Open a fresh terminal after initialization. |
| Windows | Run the Windows x86_64 installer. Open Miniforge Prompt for the commands below; ordinary PowerShell also works after Conda is initialized. |

Keep activation manual. If Conda automatically enters base, run
`conda config --set auto_activate_base false`. Do not change an existing environment
or shell configuration without the user's permission.

## 2. Make the skill entries discoverable

Ask your agent: “Install the four entries in this downloaded skill bundle into the
skill directory you support. Keep all supporting files and confirm each entry is
independently discoverable.” The agent resolves the directory; this project does not
assume any client's folder conventions or arbitrary recursive scanning.

Optional shortcut: open a terminal in `skills/molecular-research-toolkit/`, the folder
containing this guide and the package SKILL.md. With Python available, preview:

```sh
python scripts/install_skills.py --skills-dir "PATH_SELECTED_BY_YOUR_AGENT"
```

After confirming the destination, add `--write`. The source distribution retains
`skills/modules/`; the installer copies four whole folders side by side into the
agent-selected discovery directory. Existing destinations are refused unless `--update`
is explicitly requested. Updates preview changed files and refuse stale source files,
leaving removal decisions to the user. Python caches and Finder metadata are ignored
and are not copied or deleted. Installing instructions does not install dependencies.

## 3. Choose a local environment

**Existing environment:** tell the agent its name or interpreter path. Activate it
manually. The agent checks it; if it cannot determine which environment to use, it asks.
A different environment name, venv, or system Python is acceptable when requirements pass.

**New optional shared Conda environment:** from the folder containing this guide:

```sh
conda env create -f environment.yml
conda activate molecular-research-toolkit
python scripts/environment.py install --component all
```

The last command shows the proposed pip command without installing. After authorization:

```sh
python scripts/environment.py install --component all --apply
```

Before pip runs, the installer checks this interpreter against each selected module's
`dependencies.json`. It installs the declared packages and rechecks them afterward.
The environment includes Tesseract; model weights are separate and may require
an authorized download on first use. Do not rename/copy a checkpoint to simulate success.

**Only cropping:** create a smaller environment, then install the selected requirements:

```sh
conda create -n molecule-images -c conda-forge python=3.10 pip
conda activate molecule-images
python scripts/environment.py install --component molecule-image-prep --apply
```

These `--apply` examples are for an installation the user has authorized. Literature
and native spreadsheet operations require their agent tools, not this Conda stack.
Agents with the existing artifact-tool runtime may use the optional `.mjs` adapters;
pass that runtime's `--node-modules` directory. The project does not require other
agents to install a different Excel engine.

## 4. Check on each invocation

The agent runs the relevant check with the same interpreter that will run the task:

```sh
python scripts/environment.py check --component molecule-image-prep
python scripts/environment.py check --component image-to-smiles
```

A mismatch or missing dependency stops that task before creating its workspace. The
agent reports the executable, installed/required versions, and a repair command. It
asks before installing or changing environments, then rechecks. It does not silently
switch Python or run only part of a gated recognition task. No check automatically
upgrades packages. The literature module checks its actual browser/spreadsheet tools.

## Platform coverage

The guide covers macOS, Linux and Windows. Local recognition and handoff validation
were performed on macOS arm64 with Python 3.10. Native Windows/Linux inference and a
fresh full environment have not been executed in this review; package resolution alone
is not an inference test. Crop/table instructions are portable but still require the
agent's saved-file checks.

The full recognition pins require Python 3.10 and Tesseract 5+. TensorFlow 2.20 supplies
macOS arm64 wheels but no macOS Intel wheel ([release files](https://pypi.org/project/tensorflow/2.20.0/#files)).
On an Intel Mac, use a compatible Linux environment for the full recognition stack;
do not claim that native installation passed or silently replace TensorFlow. Cropping
and literature/table operations remain separate choices. The agent should inspect
platform/package errors and stop for a supported environment choice.

## Barkla

Extract the Barkla package and read its `README.md` and `ENVIRONMENT.md`. Upload only
the inner `barkla_redox/` runtime under your cluster tools directory. Upload SMI separately.
Use the cluster's authorized Gaussian, Open Babel, Slurm and module setup. Do not install
Gaussian or Slurm with local pip. Real job submission needs a separate scope preview
and confirmation. Extraction writes each molecule's G298.tsv on Barkla.

## Updating

Users update the downloaded project/bundle, review the installer's changed-file preview,
update the four installed folders, and let the agent recheck requirements on the next
operation. A toolkit update does not silently alter an existing Conda environment.

For maintainers, `python scripts/environment.py updates` reports supported and upstream
versions. The repository includes a weekly GitHub Actions report (Monday, UTC) and manual
trigger; it becomes active only after upload with Actions enabled on the default branch.
Read its job summary and JSON artifact. No version is changed or merged automatically.
Check the small component first, validate changes, then refresh the total package.
