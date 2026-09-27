# Start a Solvent Extraction

[← Project overview](README.md) · [Run example001](examples/example001/README.md#run-it-yourself)

After [installing the skill bundle](README.md#1-install-the-skill-bundle), send the messages below in your agent's chat to select `literature-solvent-extraction`. No separate module installation or earlier toolkit task is required.

## What to provide

- Drag the Excel workbook you want updated into the chat.
- Attach the starting paper(s), or provide their DOI or URL in the conversation.

The agent reads the attachments and asks for required information that is missing or unclear. For multiple starting papers, explain their correspondence to the table's data when needed.

If browser access has not already been authorized, the agent asks once at the beginning for the relevant literature scope. You can cover later batches in the same project. It reuses that grant within its scope; you do not need to add a permission statement to every task prompt. Login and mandatory host permission prompts may still require your action.

## Start the task

```text
Use literature-solvent-extraction to fill the missing
electrochemical solvents in the attached workbook.
```

If you supply a DOI or URL instead of attaching the paper, add one line identifying it. To reproduce **example001**, attach its [input workbook](examples/example001/input/example001.xlsx) and send:

```text
Use literature-solvent-extraction to fill the missing
electrochemical solvents in the attached workbook.
Starting paper: https://doi.org/10.1055/a-1390-9065 (Table 1).
```

## Optional task instructions

To limit the task, add a short message such as:

```text
Process only Molecule001 and Molecule005.
```

```text
Investigate reduction only.
```

The skill carries the detailed input, evidence, writeback, and review rules. See [what you receive](README.md#what-you-receive) for the updated workbook and review materials.

For a complete demonstration, use the [example001 input and walkthrough](examples/example001/README.md).
