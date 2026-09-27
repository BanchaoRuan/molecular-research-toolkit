# Starting an image-to-smiles task

[Project overview](README.md) · [Worked example](examples/example001/README.md)

Use these prompts after installing the complete parent toolkit. Attach images or provide a readable folder path. The agent handles commands and asks for missing or ambiguous information.

## Your own images

```text
Use image-to-smiles with these single-molecule images.
Keep the existing molecule IDs and prepare the reviewed SMILES package.
```

Supply the working project and task name if not already established. Each image contains one complete target; its filename stem becomes the image ID.

## Continue after image preparation

```text
Use image-to-smiles on the single-molecule images from the previous step.
Reuse the working project, task name, and molecule IDs.
Ask me about any ambiguous structure before accepting it.
```

The agent uses the individual PNG folder, not the overview, and passes the task name explicitly so an upstream folder suffix does not rename the task.

## Run the example

Copy [example001.png](examples/example001/input/example001_single_molecule/example001.png) into a working `example001_single_molecule` folder in your task project, then send:

```text
Use image-to-smiles on example001_single_molecule.
Use example001 as the task name and keep example001 as the image ID.
Run recognition, compare the candidate with the image, and prepare the review package.
```

Keep the bundled output as a reference. Run outside the module and leave the packaged example unchanged.

## Supply a correction

```text
For image <ID>, use this corrected SMILES: <SMILES>.
Apply the attached MOL if it represents the same structure.
Compare the regenerated structure with the original image before finalizing.
```

State intended salt/counterion handling, charge, and stereochemistry when unclear. Corrections return to source review; parseable SMILES alone do not establish a match.

The agent may ask about the working project, task name, image selection, ambiguous IDs, incomplete structures, or fragment handling. It reuses information supplied by you or the parent. Dependency installation and model downloads require authorization when not already granted.
