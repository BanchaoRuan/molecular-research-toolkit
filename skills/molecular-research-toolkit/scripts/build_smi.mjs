#!/usr/bin/env node

import path from "node:path";
import {
  SKILL_ROOT,
  atomicWriteText,
  findUniqueHeader,
  isInside,
  loadArtifactTool,
  loadSolventMapping,
  normalizeHeader,
  parseCli,
  parseResolutionOptions,
  parseUsedRange,
  pathExists,
  requireOption,
  resolveGaussianSolvent,
  selectSmiSmiles,
  taskPaths,
  textValue,
  validateDate,
  validateTaskname,
} from "./data_core.mjs";

import { readMaster } from "./master_schema.mjs";

let FileBlob;
let SpreadsheetFile;

const HELP = `
Build one reviewed Gaussian-ready SMI file from the reviewed master.

Usage:
  build_smi.mjs --project-root ROOT --node-modules NODE_MODULES --date YYYYMMDD --taskname NAME \\
    --id ID [--id ID ...] [--ids ID1,ID2] \\
    [--resolve 'RAW=GAUSSIAN_NAME'] --report REPORT.xlsx --reviewed [--sheet NAME]

The output contains exactly three whitespace-separated fields per line:
  SMILES ID gaussian_solvent_keyword

Single-fragment SMILES are preserved. Multi-fragment SMILES are reduced to
their unique explicit net-positive fragment before writing.

--reviewed records that the user has reviewed the selected structures and manual solvents.
Never infer that review from a filename. Existing output files are never overwritten.
`.trim();

function findWorksheet(workbook, name) {
  const match = workbook.worksheets.items.find((sheet) => sheet.name === name);
  if (!match) {
    throw new Error(`Cannot find worksheet ${JSON.stringify(name)}.`);
  }
  return match;
}

function requestedIds(options) {
  const values = [];
  for (const value of options.id ?? []) {
    if (value === true) {
      throw new Error("--id requires a value.");
    }
    values.push(textValue(value));
  }
  if (options.ids !== undefined) {
    if (options.ids === true) {
      throw new Error("--ids requires a comma-separated value.");
    }
    values.push(...String(options.ids).split(",").map((value) => textValue(value)).filter(Boolean));
  }

  if (values.length === 0) {
    throw new Error("At least one explicit --id or --ids value is required; all rows are never selected implicitly.");
  }

  const seen = new Set();
  for (const id of values) {
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      throw new Error(`Invalid requested ID: ${JSON.stringify(id)}.`);
    }
    if (seen.has(id)) {
      throw new Error(`Requested ID is duplicated: ${id}.`);
    }
    seen.add(id);
  }
  return values;
}

async function readReportRows(reportPath, sheetName, selectedIds) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(reportPath));
  const {rows} = readMaster(workbook, sheetName);
  return rows.filter(row => selectedIds.has(row.id)).map(row => {
    if (row.formulas[1] || row.formulas[3]) throw new Error(`Structure and manual solvent must be literal reviewed values: ${row.id}`);
    return {ID:row.id, SMILES:textValue(row.values[1]), solvent:textValue(row.values[3]), report_row:row.row};
  });
}

async function main() {
  const options = parseCli(process.argv.slice(2), new Set(["id", "resolve"]));
  if (options.help) {
    console.log(HELP);
    return;
  }

  if (options.reviewed !== true) throw new Error("Confirm selected structures and manual solvents with the user, then pass --reviewed.");
  if (options.replace) throw new Error("Existing SMI files are never overwritten; agree a different task with the user.");
  const projectRoot = path.resolve(requireOption(options, "project-root"));
  const artifactTool = await loadArtifactTool(requireOption(options, "node-modules"));
  ({ FileBlob, SpreadsheetFile } = artifactTool);
  const date = validateDate(requireOption(options, "date"));
  const taskname = validateTaskname(requireOption(options, "taskname"));
  if (Object.hasOwn(options, "redox")) {
    throw new Error("--redox is no longer supported; one task produces YYYYMMDD_taskname.smi.");
  }

  const ids = requestedIds(options);
  const idSet = new Set(ids);
  const paths = taskPaths(projectRoot, date, taskname);
  const reportPath = path.resolve(requireOption(options, "report"));
  if (!await pathExists(reportPath)) {
    throw new Error(`Reviewed report does not exist: ${reportPath}.`);
  }

  const mappingPath = path.join(SKILL_ROOT, "references", "gaussian_solvent_mapping_G16_C01.json");
  const mapping = await loadSolventMapping(mappingPath);
  const resolutions = parseResolutionOptions(options.resolve ?? []);
  const reportRows = await readReportRows(reportPath, options.sheet, idSet);
  const presentIds = new Set(reportRows.map((row) => row.ID));
  const missingIds = ids.filter((id) => !presentIds.has(id));
  if (missingIds.length > 0) {
    throw new Error(`Requested IDs are missing from the report: ${missingIds.join(", ")}.`);
  }

  const selected = reportRows.filter((row) => idSet.has(row.ID));
  const failures = [];
  const outputRows = [];
  const conversions = [];
  const cationExtractions = [];
  for (const row of selected) {
    const selectedSmiles = selectSmiSmiles(row.SMILES);
    if (!selectedSmiles.ok) {
      failures.push(`${row.ID}: ${selectedSmiles.reason}`);
      continue;
    }

    const resolved = resolveGaussianSolvent(row.solvent, mapping, resolutions);
    if (!resolved.ok) {
      failures.push(`${row.ID}: ${JSON.stringify(row.solvent)} - ${resolved.reason}`);
      continue;
    }
    outputRows.push(`${selectedSmiles.smiles} ${row.ID} ${resolved.keyword}`);
    if (selectedSmiles.method === "unique_cation_fragment") {
      cationExtractions.push({
        ID: row.ID,
        original_smiles: row.SMILES,
        output_smiles: selectedSmiles.smiles,
        removed_fragments: selectedSmiles.removedFragments,
      });
    }
    conversions.push({
      ID: row.ID,
      solvent_manual: row.solvent,
      gaussian_keyword: resolved.keyword,
      match_method: resolved.method,
    });
  }

  if (failures.length > 0) {
    throw new Error(`Cannot build a partial SMI file:\n- ${failures.join("\n- ")}`);
  }
  if (outputRows.length !== ids.length) {
    throw new Error("Internal selection error: output row count does not match requested ID count.");
  }

  const outputPath = path.join(paths.review, `${date}_${taskname}.smi`);
  await atomicWriteText(outputPath, `${outputRows.join("\n")}\n`, {
    replace: false,
  });

  console.log(JSON.stringify({
    stage: "smi_created",
    requested_ids: ids,
    output_order: selected.map((row) => row.ID),
    output: outputPath,
    gaussian_version: mapping.metadata?.gaussian_version ?? "G16 C.01",
    cation_extractions: cationExtractions,
    conversions,
  }, null, 2));
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 2;
});
