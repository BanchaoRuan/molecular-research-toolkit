# Toolkit integration

The module remains independently maintained and directly callable. Its complete
folder is bundled at `skills/modules/image-to-smiles/` in
[molecular-research-toolkit](https://github.com/BanchaoRuan/molecular-research-toolkit).
The toolkit owns shared installation and version tracking. Do not rely on recursive
skill discovery: register this SKILL.md using the agent's supported mechanism, or use
the generic directory installer provided by the toolkit.

Pass the task project and established taskname explicitly. Preserve existing IDs.
The image-preparation handoff is the independent PNG folder, not the overview;
`taskname_prepare_single_molecule` must not yield the mistaken taskname `taskname_prepare`.
Suitable images can start this module directly. [Master handoff](master-handoff.md)
defines optional workbook delivery; scientific recognition and native reports remain
under [SKILL.md](../SKILL.md) and [runtime contract](runtime-contract.md).

`smiles_auto.py`, `smiles_core.py`, the historical Conda name `smiles_auto`, and the
`_smiles` task suffix are implementation names, not additional skill entries.
Runtime outputs never belong in the installed folder. Keep all module scripts,
references and the public example together when synchronizing a tested revision.
