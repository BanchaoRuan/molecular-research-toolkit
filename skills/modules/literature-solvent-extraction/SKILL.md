---
name: literature-solvent-extraction
description: Trace user-designated papers, their supporting information, and relevant citation chains to verify solvents for ground-state electrochemical oxidation and reduction data in an existing workbook. Backfill supported results into a complete new copy of the submitted workbook and deliver an Excel review table with ordered evidence screenshots. Requires a prepared molecular data table and identified starting papers.
---

# Literature Solvent Extraction

Use the current task's workbook, designated starting papers, and explicit clarifications to recover the electrochemical measurement conditions. This is a self-contained task module distributed with the complete toolkit: it requires neither another toolkit module nor personal memory, previous conversations, a particular agent vendor, or a private configuration. Execute the requested solvent-extraction task without automatically invoking other modules before or after it.

Resolve relative file links from the directory of the document containing them, rather than from the working directory or the parent toolkit's entry point. Keep this module folder intact; its instructions, specifications, and examples are contained here.

Use the agent's available browser, document, image, and spreadsheet tools. Follow their operating instructions and the user's existing authorization. Write generated instructions, labels, and review explanations in English; preserve source quotations and search terms exactly.

## 1. Establish the task

Read [the input specification](references/input-schema.md) before research.

Start from the current attachments and chat messages. Obtain missing required information through ordinary conversation; do not require a filled-in prompt template or ask the user to repeat information already clear from the supplied materials.

Verify the agent’s existing spreadsheet, PDF/browser and evidence-capture tools before research; no dedicated Python/Conda environment is required for these native capabilities. Ask if tool availability or access is unclear.

Identify the original workbook, target worksheet, IDs, ground-state oxidation and/or reduction data, and the starting paper assigned to each target. Ask the user about execution-critical ambiguities before proceeding with the affected targets. Do not invent a missing source mapping, molecular identity, measurement, or column interpretation.

Fix the processing scope from the workbook as submitted and the user's request:

- By default, process only cells that were blank in `Solvent (AI-assisted)` at submission.
- Process populated cells only when the user explicitly requests it. Respect the requested change scope; ask if it is unclear whether an existing value may be replaced.
- When both ground-state oxidation and reduction data are provided, investigate both unless the user limits the task.
- Never write to `Solvent (manual)`. Existing solvent entries are not literature evidence.
- Resolve each target by its ID and identity, rather than by row position or a paper's compound number alone.

Prepare to collect the source links, tested locators, and screenshots described in [the review format](references/review-format.md). The user-designated workbook remains the task's source of truth.

### Establish access once

Before literature browsing, check the current conversation for authorization to use the user's browser and institutional access. If the scope is not already clear, make one concise request at the start, covering the designated papers, relevant SI, cited measurement sources, and normal library/DOI/publisher redirects. For continuing work, let the user authorize this scope for the project's solvent-extraction work, including later molecules and batches.

For example: "May I use your signed-in browser to read the designated papers, relevant SI and cited measurement sources for this project's solvent-extraction work, including later batches? You will handle any login or MFA."

Honor the scope and duration the user actually grants. Do not ask again for each molecule, article, redirect, retry, continuation, or new batch within that scope. A new task label alone does not invalidate an existing grant. Ask again only when the scope expands, the user revokes access, or the available conversation does not establish authorization. Do not assume an unseen prior grant or depend on personal memory.

This is permission to read relevant literature, not to change account settings, upload private files, purchase articles, or contact others. It does not suppress browser, operating-system, sandbox, or tool approval prompts. Handle new mandatory prompts under the host's rules; do not promise that every technical permission can be granted in advance.

### Task directories

Use the user's task project as the root for runtime files. Identify that project from the current task context; ask if it is unclear. The installed skill folder is not the task project.

Use the task project's shared `workspace/` and `review/` directories whenever this module is invoked:

```text
<project-root>/
├── workspace/
│   └── YYYYMMDD_taskname_solvent/
└── review/
    └── YYYYMMDD_taskname_solvent/
```

Use the same task folder name in both locations. Derive `taskname` from the workbook name unless the user supplies a task name. Keep separate runs distinct and do not overwrite another task's materials.

- `workspace/YYYYMMDD_taskname_solvent/`: downloaded article/SI copies, extracted text, working notes, temporary captures, temporary scripts, and validation materials.
- `review/YYYYMMDD_taskname_solvent/`: only `solvent_review.xlsx` and the final `evidence/` images.

These shared directories belong to the task project, not to an individual module inside `code/` or an installed skills directory. Create the needed task folders there when permitted; do not scatter runtime files through the skill source. Keep the original workbook untouched at its user-designated location. Write the complete updated copy to `review/YYYYMMDD_taskname_data/taskname_solvent.xlsx`; follow [master handoff](references/master-handoff.md).

When reproducing a bundled example, use a working copy of its input workbook in the task project as the designated workbook. Preserve the packaged input, output, and evidence files for comparison and future runs.

## 2. Trace the designated literature

Every evidence route must start at the paper designated by the user for that target.

Follow the parts of that paper, its supporting information (SI), and cited sources that relate to the target electrochemical datum or its experimental method. Continue through further citations when the same measurement's provenance or method requires it. Reference numbers belong to their parent papers; the same number in two papers is not the same source.

Use a known paper's DOI, title, or bibliographic details to locate its full text, SI, or a verified copy of that same work. Within these materials, use compound labels, structures, target values, table headings, and measurement terms to locate evidence. Do not search the wider literature for the molecule and substitute an unrelated paper's solvent.

The relevant search scope includes:

- the target row or figure, its caption, and applicable footnotes;
- the electrochemical methods and any stated scope or exceptions;
- related SI and explicit citations needed to connect the datum to its measurement conditions.

A first failed keyword search, an abstract, or a search snippet does not complete this work. Inspect relevant tables and figures visually when text search does not expose their contents. A redox value can help locate a passage, but a matching number alone does not establish identity or applicability.

### Access and execution problems

Work in the actual browser session that the agent can control; do not assume it shares another browser's institutional login.

Handle ordinary navigation or connection recovery with the available tools. When user action is needed, explain the affected source and next action in chat at that point. The user completes login, MFA, or CAPTCHA in the browser. Resume the same source after access is restored. An authorized local or publicly accessible copy of the same work is also acceptable.

Do not keep refreshing an unchanged access barrier. Do not bypass access controls, request credentials, or inspect authentication storage.

Login requirements, denied access, browser faults, unavailable files, and interrupted research are execution issues. Keep them in chat, not in the scientific review status or other review-table cells. Pause affected research while continuing independent targets where possible. An unread necessary source cannot justify a negative literature finding.

## 3. Assess the evidence

For each in-scope oxidation or reduction measurement, establish the complete chain:

1. **Molecule:** the source structure or unambiguous identity corresponds to the submitted SMILES and ID.
2. **Datum:** the source contains the requested ground-state potential, or explicitly establishes its provenance. Check direction, sign, units, and reference scale when stated. Do not silently convert or substitute values to force a match.
3. **Measurement:** the solvent statement concerns the electrochemical experiment producing that datum.
4. **Applicability:** the statement governs that compound, table entry, series, or experiment. Retain the footnote, scope statement, or cross-reference that establishes the connection.

A general electrochemical methods statement can be sufficient when its applicability is clear. A nearby paragraph, the same molecule name, or coincidentally matching numbers are not sufficient. Check which property a mixed electrochemical/photophysical table's solvent note actually governs.

Photophysical data may help identify or locate the target within the permitted sources. Solvents used for absorption, emission, lifetime, transient absorption, excited-state measurements, synthesis, reactions, purification, or chromatography cannot replace the target ground-state electrochemical solvent. Excited-state values alone do not satisfy this skill's input requirement.

Use these scientific assessments:

| Status | Meaning |
| --- | --- |
| `Supported` | The complete chain establishes the applicable solvent, with no unresolved contradiction affecting that assignment. |
| `Unresolved` | Relevant evidence has been examined, but an essential connection or conflicting assignment remains unresolved after following the relevant available leads. |
| `Not found` | The necessary related sources and leads have been examined, but no applicable electrochemical solvent information was found. This is a finding within the checked source chain, not a claim of universal absence. |

Several documents can jointly establish `Supported`. Neither the number of documents nor use of SI lowers the assessment. Only `Supported` solvents are eligible for backfill; an incomplete candidate must not be written as a low-confidence substitute.

### When to finish searching

Finish a measurement once its full evidence chain is established and relevant scope qualifications have been checked. Otherwise follow the concrete remaining leads in the designated chain. Do not stop while a clearly relevant cited source or SI remains unchecked and accessible.

Once those leads are exhausted, use the applicable scientific assessment above. Stop unproductive repetition of the same searches or already checked citation cycles; do not expand into unrelated literature. If execution ends before the necessary research is complete, report the unfinished target in chat instead of assigning a completed scientific assessment.

## 4. Prepare and write supported results

Assemble the evidence images and reliable source locators before backfilling a supported result. Use the detailed presentation rules in [the review format](references/review-format.md).

Assess oxidation and reduction separately. If only one is supported, its solvent can still be written; the review material must make clear which measurement it supports.

When several conditions are each demonstrably correct for the in-scope measurements, retain all distinct supported solvents. A conflict between incompatible claims is not a list of verified alternatives.

Write solvent names or reported solvent mixtures, using these conventions:

- Use unambiguous English solvent names; source abbreviations may be expanded when their identity is certain.
- Separate distinct supported conditions with ` | `, for example `acetonitrile | dichloromethane`.
- Keep an actual mixture together, including its reported ratio: `acetonitrile/water (1:1)`.
- Do not infer a mixture from separate experiments, invent a ratio, or list an electrolyte as the solvent.
- If the same solvent supports both oxidation and reduction, write it once in the output cell and state each measurement's applicability separately in the review table.
- Put scientific statuses, citations, search terms, and explanations in the review material, not in the output solvent cell.

Write only to the new complete solvent-stage copy, within the scope established at submission. A separate user approval of each AI result is not required before this backfill. The user's later scientific review is represented by the manual column, which this skill does not edit.

Leave an originally blank cell blank when no solvent is supported. Do not erase a pre-existing value merely because the new investigation is unresolved or interrupted. Preserve IDs, SMILES, other data, formulas, charts, and sheet structure. Apply the target table's [group-heading and alignment rules](references/input-schema.md#workbook-layout) and [content-based sizing checks](references/review-format.md#spreadsheet-layout-and-saved-file-checks); preserve unrelated formatting. Use spreadsheet tools that can preserve the workbook, and verify the saved values and non-target content with those tools.

## 5. Deliver

Create only the agreed review deliverables in the task's shared review location:

```text
review/YYYYMMDD_taskname_solvent/
├── solvent_review.xlsx
└── evidence/
    ├── <ID>_01.png
    └── <ID>_02.png
```

The review is a compact scientific audit, not another result workbook. Its column definitions, link layout, search verification, scanned-PDF fallback, and screenshot rules are maintained in [the review format](references/review-format.md).

Before delivery, check that every written solvent has its complete evidence chain, that image numbering follows human reading order, and that the review accurately distinguishes oxidation and reduction. Confirm that all source links and locators refer to the material actually checked.

Complete the [saved-file layout checks](references/review-format.md#spreadsheet-layout-and-saved-file-checks) for both the new solvent-stage workbook and `solvent_review.xlsx`. Group headings and column titles must be centered, ordinary text left-aligned, and all content visible at the saved row/column sizes without manual resizing by the recipient. Correct clipping or broken row/column layout before delivery.

In chat, identify the new solvent-stage workbook and review folder, summarize completed findings, and explicitly identify any unfinished targets and required user action. If only part of an ID was completed, distinguish the completed and unfinished measurements. Do not claim a complete batch when an access or execution issue still prevents assessment.
