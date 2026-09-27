# Review Format

This document defines the review deliverables. Scientific assessment and backfill eligibility are defined in [SKILL.md](../SKILL.md); this document does not introduce an additional confidence scale.

## Deliverables

```text
review/YYYYMMDD_taskname_solvent/
├── solvent_review.xlsx
└── evidence/
    ├── Molecule001_01.png
    ├── Molecule001_02.png
    └── Molecule002_01.png
```

Resolve the task project and paired runtime folders using [Task directories](../SKILL.md#task-directories). The original user workbook is never modified. Deliver its complete updated copy at `review/YYYYMMDD_taskname_data/taskname_solvent.xlsx`. Put only the audit workbook and final evidence images in `review/YYYYMMDD_taskname_solvent/`. Put working notes, downloaded paper/SI copies, temporary captures, and other intermediate materials in `workspace/YYYYMMDD_taskname_solvent/`.

## Review table

Create one worksheet named `Solvent_Review`, with exactly these six columns in order:

```text
ID
Solvent (AI-assisted)
Verification status
Related references
Evidence route
Source location
```

Use one row per ID with completed scientific assessments, in the original table's order. Within a row, distinguish `Oxidation:` and `Reduction:` when both were assessed. Do not use `Both` or duplicate the ID into separate rows.

Keep one flat header row, enable filters, and freeze the header. Center the column headings horizontally and vertically. Left-align and top-align body text, including IDs, statuses, solvents, and source entries. Store IDs as text when needed to preserve their exact display, including leading zeros. Do not merge cells in `Solvent_Review` or rely on color to convey status. The merged group headings belong only to the master molecular data table, as specified in [the input specification](input-schema.md#workbook-layout).

### Spreadsheet layout and saved-file checks

Apply these rules to generated examples, the review workbook, and the target table after backfill. Keep unrelated workbook content and formatting intact.

- Use black text on white cells, thin light-gray borders, and visible gray worksheet gridlines. Headers may be bold. Do not use colored fills, colored text, alternating row shading, or decorative table themes. Use a consistent readable font; for new workbooks, ensure that the default workbook font and the cell font agree.
- Finish all text and set the font and alignment **before sizing**. Fit each column from its actual heading and cell contents, including number formats and filter-button space. Do not copy the example's widths or estimate width only by character count. Give brief fields enough room to display normally; wrap long SMILES, solvent lists, URLs, and source entries at readable widths. Never shorten an identifier or URL for appearance.
- **Set column widths first, then fit each row's height to the greatest wrapped height required by any cell in that row.** Count both explicit line breaks and automatic wrapping, including strings without spaces. Leave a small margin for font/rendering differences. Rows have one shared height across all columns; do not split one ID into extra rows to accommodate links.
- Set the height of merged group-heading rows explicitly from the combined span. Do not rely on AutoFit to handle merged cells. Merge only the identified group headings, never data records or review cells. Do not shrink the font to hide an overflow.
- Save actual column widths, row heights, wrapping, and alignment in the XLSX. A `bestFit` flag, an AutoFit API call, or a successful export alone is not proof that Excel will display the text. Refit affected rows after changing text or column widths. The recipient must not need to drag borders or run AutoFit after opening the delivered file.
- Reopen the **saved XLSX** and check the group headings, all column titles, longest IDs/SMILES, longest solvent result, and densest source cells. Verify centered headings, left-aligned body text, regular data-cell borders, and fully visible text. Open it in Microsoft Excel when available; an authoring-tool preview alone does not establish native Excel layout. If Excel is unavailable, inspect the saved file with the available renderer and report that compatibility limitation in chat.
- Check representative short, long, multiline, and blank content when maintaining the skill or its examples. Include different row lengths, multiple supported solvents, long URLs without spaces, several source entries, optional InChIKey, and varying paper-data columns. Keep synthetic test data outside the published example and scientific results.

If unusually long content still cannot fit within Excel's display limits, revise the relevant widths and recheck. If no readable single-row layout is possible, explain the affected ID in chat and agree on a layout before delivery; never silently clip or discard content.

### Field content

| Column | Content |
| --- | --- |
| `ID` | The user's exact ID. No additional molecule-name or identity-mapping column. |
| `Solvent (AI-assisted)` | Supported solvent results, with measurement labels as needed. Use an em dash for an assessed measurement with no supported result; do not display an unverified candidate as a result. |
| `Verification status` | The corresponding scientific status for each assessed measurement. For `Unresolved`, add a short, specific evidence gap or conflict only when needed to understand the result. |
| `Related references` | Relevant original reference articles and their full source URLs, identified by reference number where available. |
| `Evidence route` | The actual sequence followed from the designated starting paper to the evidence sources, with a role label and full URL at each step. |
| `Source location` | The source URL and one or a few search terms actually tested in that source, or the permitted scanned-PDF page locator. |

The solvent entries explain the supported contributions to the output workbook cell. For example:

```text
Oxidation: acetonitrile
Reduction: dichloromethane
```

The output workbook cell for that example contains `acetonitrile | dichloromethane`. If both measurements use acetonitrile, list it under each measurement in the review and only once in the original cell.

The corresponding status cell might contain:

```text
Oxidation: Supported
Reduction: Supported
```

These are format examples, not experimental results. Use statuses consistent with the actual solvent entries and evidence. A target with only one assessed measurement needs only that measurement's entry.

If only oxidation is supported and the reduction evidence is unresolved, show `Reduction: —` in the solvent cell and, for example, `Reduction: Unresolved — method applicability unclear` in the status cell. Only the supported oxidation solvent contributes to the output workbook cell.

Do not add embedded pictures, picture links, confidence scores, reviewer fields, or operational-error columns. Do not fill the review with login failures, browser problems, or uncompleted searches. If delivery is partial, include only completed scientific assessments and identify the unfinished IDs/measurements in chat. Do not assign `Not found` merely to complete a row.

## References and tracing routes

Keep full URLs as copyable plain text, so the user can paste them into a library service. Clickable hyperlinks are optional; do not replace the visible URL with a short label or depend on Excel hyperlink formulas.

Use one logical line per source, with its label immediately followed by the URL on that same line. Put the next source on the next line, without a blank line. Normal visual text wrapping is acceptable.

For `Related references`, the format is:

```text
Ref. 12 — Original article: <full article URL>
Ref. 19 — Original article: <full article URL>
```

Reference numbering is local to its parent paper. Add a short parent label when necessary to distinguish identical reference numbers from different parents.

For `Evidence route`, the format is:

```text
1. Starting paper: <full starting-paper URL>
2. Ref. 12 — Original article: <full article URL>
3. Ref. 12 — SI: <full SI URL>
```

List actual tracing order, not a credibility ranking. Include only steps used for the target. If oxidation and reduction follow different routes, prefix the step labels with `Oxidation` or `Reduction`; a shared route need not be duplicated. One direct source needs only one route entry.

Use verified DOI, publisher, SI, or same-work repository URLs as appropriate. An SI locator must lead to that SI or its verified download location; a parent DOI alone does not identify the SI file that was searched. Exclude local filesystem paths, browser-session URLs, and authentication tokens.

## Reliable source location

Point directly to the material needed to check the evidence. Do not repeat the entire route in this column.

For searchable sources, use this form:

```text
SI: <full SI URL>; Search: "keyword one"; "keyword two"
```

If different files are needed, use separate logical lines:

```text
Oxidation — Article: <full article URL>; Search: "keyword one"
Reduction — SI: <full SI URL>; Search: "keyword two"
```

The examples above contain placeholders. In a real review, enter genuine URLs and search terms that meet all of the following:

- Copy a short term or phrase from the actual source, not an agent-written paraphrase.
- Test it using Find in the actual web page or PDF used for evidence. A match only in extracted or separately OCR-processed text does not verify searchability in the user's original source.
- Confirm that the term leads to the evidence or a clear nearby heading. A few matches are acceptable; choose more useful terms if matches are too numerous to locate the passage efficiently.
- Prefer a short, reliable word or heading over a long sentence. A failed long-phrase search alone does not establish that the PDF is unsearchable.
- Supply only the terms needed for quick checking. Do not append a narrative of page, section, table, compound, and method details.

For a scanned PDF whose evidence cannot be located with reliable search terms after an actual attempt, use:

```text
SI: <full SI URL>; PDF page: 12
```

`PDF page` means the file's physical page position, counted from 1, rather than a printed journal or SI page label. Supply multiple page positions only when needed. If a nearby searchable heading reliably locates the image, prefer that tested term. Do not claim that a newly OCR-processed copy proves the publisher's original PDF is searchable.

Searchability does not change scientific support. For a negative or unresolved finding, provide useful genuine locators for relevant inspected material when available; otherwise leave that location empty rather than inventing a keyword or passage.

## Evidence images

Each ID's image group must show the chain from molecular identity to the target ground-state datum and its governing electrochemical solvent. Source labels, structures, captions, footnotes, and cross-references must make the connections visible.

Use one screenshot when it contains the complete chain. Use as many additional screenshots as necessary when the chain spans passages or documents; there is no fixed two-image limit. Keep each image legible and retain the context needed to judge applicability.

Name images `<ID>_01.png`, `<ID>_02.png`, and so on. Use consecutive zero-padded numbers in **human reading order**, not capture time or document page order. Ordinarily the reader should see identity/target evidence before the governing method or solvent. Do not use a separate `__target` naming convention.

Preserve the exact ID in the filename whenever the filesystem permits it. If it cannot be used safely or would collide, resolve the filename mapping with the user rather than silently changing the workbook ID.

Use thin boxes to highlight useful existing content, such as the compound label, target value, solvent statement, or relevant scope wording. Preserve the underlying source pixels, text, numbers, and structures. Do not redraw, replace, obscure, or manufacture evidence, and do not annotate an uncertain link as established. A screenshot only needs to highlight the part of the chain it actually carries.

For `Unresolved`, include useful actual evidence showing the partial chain without implying completeness. For `Not found`, include a screenshot only when it genuinely helps the reviewer; do not create empty images or unrelated solvent captures to satisfy a quota.

Do not use screenshots of search snippets, generated answers, paraphrases, or isolated solvent words. The final image group must be understandable without the agent's private notes or conversation history.
