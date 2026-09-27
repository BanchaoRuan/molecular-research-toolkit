# Maintaining the toolkit

Change and test a small component first. Synchronize its private repository yourself,
then copy the selected complete component into this project's recorded location.
The bundled copy is a snapshot, not a second independently edited implementation.

| Component | Toolkit snapshot |
| --- | --- |
| molecule-image-prep | `skills/modules/molecule-image-prep/` |
| image-to-smiles | `skills/modules/image-to-smiles/` |
| literature-solvent-extraction | `skills/modules/literature-solvent-extraction/` |
| barkla_redox | `tools/barkla_redox/` |

Small table/file operations belong to `skills/molecular-research-toolkit/`. They do
not have a separate manage-data-auto skill, private repository or version. The old
implementation remains an integration reference outside this distribution.

## Release names and versions

The first public development version is `0.1.0`, with tag `v0.1.0` and release title
`Molecular Research Toolkit v0.1.0`. A suitable initial commit message is
`chore(release): initial development release v0.1.0`.

While the project is below 1.0, use a patch such as `0.1.1` for compatible corrections
and a minor version such as `0.2.0` for new capabilities or changes to existing
interfaces. Describe any changed columns, command options, output formats or supported
environments. Reserve `1.0.0` for the workflows and interfaces accepted as stable.
These conventions follow [Semantic Versioning](https://semver.org/).

Use descriptive commits such as `fix(smi): ...`, `feat(tables): ...`, `docs(install): ...`
or `chore(deps): ...`. A commit need not create a new release. Before a release, align
`VERSION`, `components.json` and the README, record relevant validation limits in
`VALIDATION.md`, and rebuild the archives and checksums. Never replace a published tag
or its release assets; publish a new version for a correction. Public `main` download
links change as the branch changes; use a tag and recorded checksum for reproducibility.

## Update a component

1. Change its maintained source and validate the affected behavior. Keep scientific
   decisions, example evidence and runtime safety rules with the component.
2. Review dependency changes in that component's `requirements.txt` and
   `dependencies.json`. The shared installer reads those files directly. Test proposed
   upgrades separately; do not rewrite a user's working environment automatically.
3. Synchronize the component's private repository and choose its revision. Refresh
   the complete bundled folder. Preserve third-party source attribution.
4. Run `python scripts/package.py --record` after reviewing the copied components.
   This records their exact file hashes and resets revision fields to null. Add the real
   selected private-repository revision identifiers to `components.json` when available;
   never invent a Git commit for an unpublished local snapshot.
5. Check module discovery, CLI/help, dependency gates, relevant table handoffs and the
   example. Validate the current platform honestly; list untested platforms.
6. Run `python scripts/package.py --check`, then build into a fresh project-local
   directory: `python scripts/package.py --output-dir workspace/release-build`.
   After review, replace the distributable ZIPs in `dist/` with those exact outputs.
   GitHub synchronization and publication are manual.

The root ignore rules exclude root-level task `workspace/` and `review/` folders;
published examples inside components remain included. ZIP creation uses its own
filter, independently of Git: common environment/credential files, private-key
containers, local environments, caches and symbolic links are omitted. These filename
rules do not inspect file contents, so review unfamiliar files before a release.

## Dependency review

The weekly GitHub Actions workflow and its manual trigger call the read-only upstream
checker. Open its job summary or download `dependency-review.json` from the run.
It reports release differences and query failures without changing any pinned version.
Actions must be enabled after publication. This local assembly did not activate a remote
schedule or create an app reminder.

For a local check, run the package entry's `scripts/environment.py updates`. A reported
new release is a review candidate, not a requirement for existing users. Handle cluster
Gaussian, Slurm and module changes under Barkla's own environment instructions.

## Presentation

Write the README after interfaces, installation and examples are stable. Keep the
homepage brief: purpose, download choices, usable starts, component map and one linked
workflow example. Use short tables and expandable details; keep most scientific evidence
inside the component examples. Preserve their established names, including image prep's
`examples/example/`.

The presentation borrows academic navigation from [MDAnalysis](https://github.com/MDAnalysis/mdanalysis)
and self-contained task folders from [Anthropic Skills](https://github.com/anthropics/skills)
and [OpenAI Skills](https://github.com/openai/skills). These are design references, not
runtime dependencies or a requirement to adopt their plugin/release frameworks.
