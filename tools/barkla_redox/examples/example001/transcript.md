# example001 terminal transcript

Re-typeset current-release usage examples: commands and resource previews use release defaults, while the numerical results are verified from supplied logs, not a fresh run with those defaults. <runtime> replaces personal paths; example001 is the public molecule ID. Figure wrapping is presentation-only; copy commands from the README.

## Select a calculation

```text
$ bash scripts/redox_batch.sh inputs/20000101_example001.smi

Select functional:
  1) M062X -> M062X
  2) B3LYP -> B3LYP
  3) wB97XD -> wB97XD
Enter a number (1-3): 2

Select basis set:
  1) 6-31Gd -> 6-31G(d)
  2) def2TZVP -> def2TZVP
  3) def2SVP -> def2SVP
  4) 6-31plusGdp -> 6-31+G(d,p)
Enter a number (1-4): 1

Select solvation model:
  1) IEFPCM -> SCRF=(Solvent={solvent})
  2) CPCM -> SCRF=(CPCM,Solvent={solvent})
Enter a number (1-2): 1
Prepare base for every molecule? (y/n): y
Prepare oxidized for every molecule? (y/n): y
Prepare reduced for every molecule? (y/n): y

Select walltime:
  1) 24h -> 1-00:00:00
  2) 48h -> 2-00:00:00
  3) 72h -> 3-00:00:00
  4) 96h -> 4-00:00:00
  5) 120h -> 5-00:00:00
Enter a number (1-5): 5
```

## Review the preparation

```text
Resolved customization preview
======================================
Input file: <runtime>/inputs/20000101_example001.smi
Molecule count: 1
Selected states: base oxidized reduced
  base: charge offset +0, multiplicity 1
  oxidized: charge offset +1, multiplicity 2
  reduced: charge offset -1, multiplicity 2
Gaussian jobs: 3
Functional: B3LYP -> B3LYP
Basis set: 6-31Gd -> 6-31G(d)
Solvation model: IEFPCM -> SCRF=(Solvent={solvent})
Walltime: 120h -> 5-00:00:00
Route keywords: opt freq
CPU cores: 4
Gaussian memory: 4000MW
Nodes: 1
Tasks: 1
Partition: troisi
Method name: B3LYP__6-31Gd__IEFPCM
Method publication mode: new
Batch copy: <runtime>/calculations/20000101_example001/20000101_example001.smi
Coordinate mode: create
Coordinate snapshot: <runtime>/calculations/20000101_example001/coordinates
Coordinates already valid: 0
Coordinates to generate: 1
Open Babel required: yes
Calculation directory: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM
Work directory: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/work
Slurm stdout/stderr directory: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/logs
Submit directory: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/submit
Preparation log: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/preparation.log
Results directory: <runtime>/results/20000101_example001/B3LYP__6-31Gd__IEFPCM
======================================
Proceed with this preparation? (y/n): y
```

## Prepare the inputs

```text
*** Open Babel Warning in ReadMolecule
  Problems reading an XYZ file: Cannot read the first line.
10 molecules converted
Conformers found: 10
Selected conformer index: 2
Selected conformer energy: 301.726
Prepared coordinate: molecule_id=example001 smiles=CN(C)c1ccc(C(=O)c2ccc(N(C)C)cc2)cc1
Coordinate status: success for molecule_id=example001
Finalizing coordinate snapshot...
Verified frozen coordinate snapshot: 1 molecules
Verified frozen coordinate snapshot: 1 molecules
Preparing method [1/1]: molecule_id=example001
Status: success for molecule_id=example001
Batch preparation finished
Total molecules: 1
Expected Gaussian jobs: 3
Successful preparations: 1
Prepared Gaussian jobs: 3
Failed preparations: 0
Preparation complete.
Preparation log: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/preparation.log
Submit script: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/submit/submit.sh
```

## Submit the jobs

```text
$ bash calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/submit/submit.sh
[1/3] Submitting molecule_id=example001 state=base
[2/3] Submitting molecule_id=example001 state=oxidized
[3/3] Submitting molecule_id=example001 state=reduced

Batch submission finished
Total jobs attempted: 3
Successfully submitted: 3
Failed submissions: 0
Successful submission records: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM/submit/submitted.tsv
```

## Extract G298

```text
$ python3 scripts/extract_G298_batch.py calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM

Batch input: <runtime>/calculations/20000101_example001/20000101_example001.smi
Calculation method: <runtime>/calculations/20000101_example001/B3LYP__6-31Gd__IEFPCM
Selected states: base, oxidized, reduced
Number of molecules: 1

Quick status:
complete: 1
needs_check: 0

Excel-ready G298:
molecule_id  G_base       G_oxidized   G_reduced    overall_status
example001   -844.297425  -844.109724  -844.359728  complete

No molecules need manual check.

Overwritten per-molecule TSV files:
<runtime>/results/20000101_example001/B3LYP__6-31Gd__IEFPCM/example001/G298.tsv
```
