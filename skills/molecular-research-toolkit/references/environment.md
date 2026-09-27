# Environment checks

The agent selects the actual interpreter with the user’s context, reads this release's
requirements, and checks before each requested task. Do not ask the user to manually
compare versions. If the user already has Conda, venv or another environment, reuse it
when compatible; ask when its location or suitability is uncertain.

| Operation | Check |
| --- | --- |
| Image preparation | Module `scripts/validate_setup.py` |
| Complete image recognition | Same task Python: module `scripts/validate_setup.py --models` |
| Paper/solvent/table work with agent tools | Verify spreadsheet, PDF/browser and evidence capabilities actually used |
| Optional `.mjs` adapters | Node 20+, supplied artifact-tool runtime, Python 3.10+ for preservation |
| Barkla scripts | Their `ENVIRONMENT.md`, on the cluster; no local Gaussian install |

Run `python scripts/environment.py check --component MODULE` from this entry folder
for the first two module checks. The batch entry repeats its full gate. Models are
not downloaded by a check. A valid package version is not a guarantee of inference
success: native libraries and weights may still fail at runtime; stop and diagnose in
the same environment rather than marking every molecule as a scientific failure.

Package versions are maintained in each module’s `requirements.txt`; Python, module
imports and system versions are declared in `dependencies.json`. This entry's
`environment.yml` is only the optional shared Conda bootstrap. The installer composes
selected requirements directly from the modules, avoiding a second set of copied pins.

`environment.py install --component all` shows the proposed command; add `--apply`
only after authorization. Select one component to install just its requirements. After
installation the same interpreter is checked again. Do not auto-activate base or edit
shell startup files. The [installation guide](../INSTALL.md) covers all three local OSes.

`environment.py updates` is a maintainer report of upstream releases. It never changes
requirements. A satisfied environment is not a failure merely because PyPI has a newer
version. Test an update in a disposable environment, update the small component first,
then rebuild and validate the total package. GitHub's weekly report is informational.
