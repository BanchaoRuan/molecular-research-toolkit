# example001 run summary

This publication summary uses relative paths. The complete dated event log and environment-repair records remain in the maintainer's task workspace.

| Stage | Result |
| --- | --- |
| Environment | Full preflight passed after resolving a native SciPy loading error. |
| OCR | No valid text candidate. |
| Strict recognition | Three variants; no valid consensus. |
| One bounded recovery | Three variants; one RDKit-valid candidate, pending review. |
| Source review | Candidate rejected: incorrect nitrogen charges and methyl substituents. |
| Correction | Source-supported SMILES applied and comparison regenerated. |
| Final source review | Match; `success`, `high`. |
| MOL validation | One accepted MOL matches the final SMILES. One rejected seed is retained separately. |
| Finalization | Review package generated successfully. |

See the [walkthrough](../README.md), [recognition records](../evidence/), and [reproducibility manifest](../evidence/run-manifest.json). The initial environment error was not counted as a molecular recognition attempt. Two recognition attempts were completed; no further automatic recognition retries were made.

The workbook contains exactly `image_id`, `smiles`, `inchikey`, `status`, and `confidence`. The accepted structure is in [example001_chemdraw_input/example001.mol](example001_chemdraw_input/example001.mol); [example001_chemdraw/example001.mol](example001_chemdraw/example001.mol) is a rejected seed.
