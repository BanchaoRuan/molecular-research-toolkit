<h1 align="center">Molecular Research Toolkit</h1>

<p align="center">From paper figures to reviewed molecular inputs and Barkla result files.</p>

<p align="center">
  <a href="INSTALL.md">Install</a> ·
  <a href="examples/example001/README.md">Walk through example001</a> ·
  <a href="skills/molecular-research-toolkit/references/table-contract.md">Table contract</a> ·
  <a href="MAINTAINING.md">Maintain</a>
</p>

---

Three directly callable skills, a few shared table operations, and standalone Barkla
scripts. Use one task at a time or follow the complete example. The package keeps
molecular identity, source evidence and human review visible at each handoff.

**0.1.0 · Initial development release.** Workflows and interfaces may change. See the
[validation record](VALIDATION.md) and [platform coverage](skills/molecular-research-toolkit/INSTALL.md#platform-coverage)
before reuse.

**This release ends with per-molecule `G298.tsv` files generated on Barkla.** Computational
result download, master-table backfill and regression are outside this version.

## Download what you need

| Package | Contents | Download |
| --- | --- | --- |
| **Skill bundle** | Three modules, package entry, table helpers, template and installation guide | [Skills ZIP](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/molecular-research-toolkit-skills.zip) |
| **Barkla tools** | Standalone repository, example, environment notes and inner uploadable runtime | [Barkla ZIP](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/barkla-redox.zip) |
| **Complete project** | Both packages, the workflow example and maintenance files | [Full ZIP](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/molecular-research-toolkit-all.zip) |

[Checksums](https://github.com/BanchaoRuan/molecular-research-toolkit/raw/main/dist/SHA256SUMS.txt) · [From-zero and existing-environment setup](INSTALL.md)

The ZIPs are stored in `dist/`. These links follow the current `main` branch; for
reproducible work, keep the downloaded ZIP and its checksum or use a published version
tag. Skill registration uses an agent-selected directory;
no particular agent client is required. Dependencies may be installed selectively or
together, with the user's permission.

## Start with a task

Attach the input, or give its path, and say what you want. Equivalent wording works.

| You have | You can ask |
| --- | --- |
| A figure containing several structures | “Crop these molecules into separate images, keeping their IDs.” |
| Single-molecule images | “Use image-to-smiles to identify and review these structures.” |
| Reviewed image results and a master | “Fill the matching SMILES and InChIKey pairs in this table.” |
| A table and its starting paper | “Complete the missing paper data for these molecules.” |
| Reported electrochemical potentials | “Find the supported solvents for these values.” |
| Reviewed structures and manual solvents | “Export only these IDs as a Barkla SMI file.” |

No earlier module is required when the necessary inputs are available. The agent checks
the relevant environment, reuses established context and asks about missing information.
The package entry also creates an empty `taskname.xlsx` when no master is supplied.

## What is included

| Entry | Input → output | Example |
| --- | --- | --- |
| [molecule-image-prep](skills/modules/molecule-image-prep/README.md) | Figures → ID-named PNGs, source map, overview | [Five crops](skills/modules/molecule-image-prep/examples/example/README.md) |
| [image-to-smiles](skills/modules/image-to-smiles/README.md) | Single-molecule images → reviewed SMILES, InChIKey, MOLs and audit | [Recognition and correction](skills/modules/image-to-smiles/examples/example001/README.md) |
| [literature-solvent-extraction](skills/modules/literature-solvent-extraction/README.md) | Master and papers → supported solvents and source evidence | [Electrochemical evidence](skills/modules/literature-solvent-extraction/examples/example001/README.md) |
| [Package operations](skills/molecular-research-toolkit/SKILL.md) | Create master, fill structure pairs, organize paper data, export SMI | [Table stages](examples/example001/README.md#table-stages) |
| [barkla_redox](tools/barkla_redox/README.md) | Reviewed SMI → Gaussian/Slurm preparation → per-molecule G298 | [Barkla example](tools/barkla_redox/examples/example001/README.md) |

## Follow one molecule

**example001 · Michler's ketone**

```text
Paper figure → individual PNG → source-reviewed SMILES
                                      ↓
Master copy → paper data → electrochemical solvent evidence → human review
                                      ↓
                         selected SMI → Barkla → G298.tsv
```

[**Open the complete walkthrough →**](examples/example001/README.md)

The crop-to-recognition handoff was executed for this example. A model error was
rejected and corrected after source comparison. Literature evidence and Barkla energies
come from the existing verified component examples; no new HPC run is implied.

## A table that stays traceable

Each operation leaves the submitted workbook unchanged and delivers a complete new copy.
Only its agreed cells are completed. Other sheets, formulas, manual entries and unrelated
molecules are preserved. SMILES and InChIKey are filled together for the involved images;
conflicting existing values require user direction. Paper and solvent data default to
blank cells. Molecules without complete SMILES are skipped for literature processing.

[Master template](skills/molecular-research-toolkit/assets/master_template.xlsx) ·
[Names, columns and handoff rules](skills/molecular-research-toolkit/references/table-contract.md)

<details>
<summary><strong>Repository layout</strong></summary>

```text
molecular-research-toolkit/
├── skills/
│   ├── molecular-research-toolkit/   # Package entry, environment and small operations
│   │   ├── SKILL.md
│   │   ├── environment.yml
│   │   ├── scripts/
│   │   ├── references/
│   │   └── assets/
│   └── modules/
│       ├── molecule-image-prep/
│       ├── image-to-smiles/
│       └── literature-solvent-extraction/
├── tools/
│   └── barkla_redox/                # Outer docs/example; inner uploadable runtime
├── examples/                       # One combined workflow
├── scripts/                        # Local packaging
├── components.json                 # Recorded component snapshots
└── dist/                           # Independent downloads
```

Modules remain independently maintained. Update and validate the small source component,
then refresh the selected snapshot here. The generic installer makes four separate skill
entries discoverable without changing this distribution layout.

</details>

## Validation and updates

The agent reads the released dependency requirements before running a module. Compatible
existing environments are welcome; Conda is an optional shortcut. Upstream releases are
reported weekly for maintainer review and do not trigger automatic upgrades.

[Validation record](VALIDATION.md) · [Platform coverage](skills/molecular-research-toolkit/INSTALL.md#platform-coverage) ·
[Component versions](components.json) · [Maintenance workflow](MAINTAINING.md)

## License and sources

[MIT](LICENSE) covers original content the maintainer has the right to license.
Third-party figures, paper excerpts, model software and data retain their own rights;
see [license scope and source notices](THIRD_PARTY_NOTICES.md) and the example citations.
