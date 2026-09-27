# Validation record

This record covers the `0.1.0` initial development release. It verifies the assembled
files and meaningful handoffs. It is not a
claim of a fresh installation or a new HPC calculation on every platform.

| Check | Result |
| --- | --- |
| Component snapshots | Complete module/tool files match the maintained local sources; SHA-256 inventory in components.json. |
| Source and metadata | 49 Python/JavaScript syntax, CLI-help, skill-metadata and snapshot checks passed. Barkla shell syntax passed. |
| Actual crop → recognition | Executed with the 264 × 126 example001 crop; strict attempt and one recovery retained. Incorrect NHMe rejected; source-supported correction re-reviewed and finalized. |
| Master/SMI contracts | 13 cases passed: paired conflict handling, blank-only scope, formulas, missing SMILES, non-target preservation, original-file protection and selection/review gates. |
| Fragment/solvent rules | 9 cases passed, including unchanged single fragments, unique explicit cation, ambiguous salts, descriptors and task-local solvent identity resolution. |
| Complete original workbook | Five-sheet user workbook remained unchanged; an empty-edit copy preserved every ZIP member. Synthetic changed-cell tests preserved unrelated sheets/formulas and all other ZIP members. |
| Stage example | Master snapshots contain the agreed columns and source values. Exported SMI equals the established Barkla example. |
| Dependency gate | Actual macOS arm64 environment passed. A deliberately changed requirement in a disposable component copy caused a mismatch failure; no environment was modified. |
| Generic installation | Four complete entries copied to a project-local test directory; checks also passed from the installed layout. No personal skill directory was changed. |
| Upstream checker | Queried 15 declared PyPI packages and produced supported/latest information without changing requirements. Weekly workflow configured locally. |
| Distribution | Three independent ZIPs passed integrity and content checks; the standalone skills archive includes all four entries, the solvent audit and six evidence images. Its extracted installation passed. All 227 relative documentation links resolve. |
| Presentation | Saved workbooks rendered and inspected; root README rendered in a local browser preview. |
| Publication regression checks | Signal-terminated dependency validators fail; installation reads the declared Python constraint before pip; ordinary caches do not block skill updates; obsolete source files still do. SMI export ignores formulas in unselected molecules while selected formulas, missing IDs and existing outputs are refused. |
| Release consistency | Packaging checks the toolkit version, four-component inventory and file hashes. The `0.1.0` label describes an initial development release. |

## Evidence boundaries

- Public redistribution permission for the original literature crops and evidence
  screenshots has not been confirmed. Source attribution and this technical record
  do not establish that permission; see [third-party notices](THIRD_PARTY_NOTICES.md).
- Recognition ran in the existing Python 3.10 macOS arm64 environment. Fresh pip
  dependency resolution was inspected without installing; native Windows/Linux and a
  fresh full environment have not been executed. Tesseract and Python/package versions
  are checked, but model import/weight/service failures can still occur at runtime.
- DECIMER inference was not exercised by this printed-structure example. Both engine
  dependency groups remain mandatory for the complete recognition gate.
- Literature findings reuse the existing source-audited component example. The manual
  solvent workbook is a curated example fixture reflecting the previously reviewed SMI.
- G298 values are the existing log-verified Barkla results. Its five runtime scripts and
  configuration were not changed. No login, submission, result download or computational
  result backfill occurred.
- The optional table adapter authors values with the existing artifact-tool runtime,
  then preserves unrelated XLSX package members. Other agents may use their own tools.
  User workbooks are not converted into a simplified replacement schema. Formula caches
  outside the changed scope are retained; open/recalculate in Excel when needed.
- GitHub links target the user-supplied repository. Upload, private-repository revision
  selection, Actions activation and publication remain maintainer actions.
