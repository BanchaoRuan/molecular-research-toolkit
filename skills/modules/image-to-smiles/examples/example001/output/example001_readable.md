# example001 SMILES review

| image_id | smiles | inchikey | status | confidence |
|---|---|---|---|---|
| example001 | CN(C)c1ccc(C(=O)c2ccc(N(C)C)cc2)cc1 | VVBLNCFGVYUYGU-UHFFFAOYSA-N | success | high |

## Evidence details

### example001

- `source_match`: yes
- `recognition_method`: chemdraw
- `rdkit_valid`: true
- `source_image_path`: example001_single_molecule/example001.png
- `reverse_structure_path`: example001_re_structure/example001.png
- `notes`: no accepted candidate: no_valid_text_candidate; no_variant_consensus; ChemDraw seed prepared: example001.mol; best_effort_single_variant; clean_light_background; Rejected after source comparison: both neutral NMe2 groups were misread as positively charged NH2(CH3) groups, losing one methyl substituent per nitrogen.; ChemDraw seed prepared: example001.mol; Source-guided correction restores two neutral para dimethylamino groups on the benzophenone core; independently checked against PubChem CID 7031. Applied as SMILES through the manual-correction CLI; no ChemDraw GUI was used.; Reviewed the regenerated source/reverse comparison: benzophenone carbonyl, both para N(CH3)2 substituents, aromatic connectivity and neutral charge match the source; no stereochemical or fragment ambiguity is present.
