#!/usr/bin/env node
// Optional reference adapter. Agents may use their own spreadsheet capability
// under the same table contract; this adapter keeps the existing artifact tool.
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { SKILL_ROOT, parseCli, requireOption, loadArtifactTool, readJson, taskPaths,
  pathExists, textValue, atomicWriteText } from './data_core.mjs';
import { HEADERS, readMaster, isBlank, cell } from './master_schema.mjs';

const HELP = `Master table operations (preview by default; --write creates a new file).
  master_table.mjs init|inspect|smiles|paper|solvent --node-modules DIR
    --project-root DIR --date YYYYMMDD --taskname NAME
    [--master FILE.xlsx] [--sheet NAME] [--report SMILES_REPORT.xlsx]
    [--patch VALUES.json] [--overwrite-cell C4 --overwrite-cell D4 ...]
    [--initialize-ids] [--python PYTHON] [--write]

init copies the empty template to taskname.xlsx; no --master is accepted.
smiles reads the five-field image-to-smiles report. --initialize-ids is only
for a genuinely empty template, after establishing the intended molecules.
paper/solvent use JSON rows: {id, column, value, evidence}.
Existing conflicts are previewed. Pass only explicitly approved cells via
--overwrite-cell; structure pairs are replaced together. Solvent manual cells
are never written. No command overwrites an output or its input.
--python is the task's checked Python, used only to preserve the XLSX package.`;

export async function main(argv = process.argv.slice(2)) {
  const o = parseCli(argv, new Set(['overwrite-cell']));
  if (o.help) { console.log(HELP); return; }
  const action = o._[0];
  if (!['init','inspect','smiles','paper','solvent'].includes(action)) throw new Error(HELP);
  const paths = taskPaths(requireOption(o,'project-root'), requireOption(o,'date'), requireOption(o,'taskname'));
  const name = o.taskname;
  const output = path.join(paths.review, `${name}${action === 'init' ? '' : '_'+action}.xlsx`);
  if (action === 'init') {
    if (o.master) throw new Error('Use the provided master read-only; init is only for tasks without a master.');
    console.log(JSON.stringify({action, output}, null, 2));
    if (o.write) {
      await fs.mkdir(paths.review, {recursive:true});
      await fs.copyFile(path.join(SKILL_ROOT,'assets','master_template.xlsx'), output, fs.constants.COPYFILE_EXCL);
    }
    return;
  }
  const {FileBlob, SpreadsheetFile} = await loadArtifactTool(requireOption(o,'node-modules'));
  const master = path.resolve(requireOption(o,'master'));
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(master));
  const {sheet, rows} = readMaster(workbook, o.sheet);
  if (action === 'inspect') {
    console.log(JSON.stringify({sheet:sheet.name, headers:HEADERS, rows}, null, 2)); return;
  }
  if (await pathExists(output) || output === master) throw new Error(`Output exists or is the input: ${output}`);
  const changes = [], conflicts = [], skipped = [], absent = [];
  const approved = new Set(o['overwrite-cell'] ?? []);
  const byId = new Map(rows.map(r => [r.id, r]));
  const add = (r, index, value, evidence) => changes.push({id:r.id, cell:cell(r.row,index), old:r.values[index] ?? null, value, evidence});
  if (action === 'smiles') {
    const report = await SpreadsheetFile.importXlsx(await FileBlob.load(requireOption(o,'report')));
    const reportSheet = report.worksheets.getItemAt(0);
    const all = reportSheet.getUsedRange().values;
    if (['image_id','smiles','inchikey','status','confidence'].some((v,i) => all[0][i] !== v)) throw new Error('Expected the unchanged five-column image-to-smiles report.');
    const seen = new Set();
    for (const v of all.slice(1)) {
      if (v.every(x => x === null || x === '')) continue;
      const [id, smiles, key, status] = v.map(textValue);
      if (!/^[A-Za-z0-9_-]+$/.test(id) || seen.has(id)) throw new Error(`Invalid or duplicate report ID: ${id}`);
      seen.add(id);
      let r = byId.get(id);
      if (!r && o['initialize-ids'] && rows.length === 0) {
        r = {id,row:4+byId.size,values:Array(13).fill(null),formulas:Array(13).fill(null)};
        byId.set(id,r); add(r,0,id,'Image report identity');
      }
      if (!r) { absent.push(id); continue; }
      if (status !== 'success') { skipped.push({id,reason:'Not source-reviewed success'}); continue; }
      if (!smiles || /\s/.test(smiles) || !/^[A-Z]{14}-[A-Z]{10}-[A-Z]$/.test(key)) throw new Error(`Incomplete structure pair for ${id}`);
      const pair = [[1,smiles],[2,key]];
      const mismatches = pair.filter(([i,value]) => !isBlank(r,i) && (r.formulas[i] || textValue(r.values[i]) !== value));
      const unresolved = mismatches.filter(([i]) => !approved.has(cell(r.row,i)));
      if (unresolved.length) {
        conflicts.push({id, cells:unresolved.map(([i,value]) => ({cell:cell(r.row,i), old:r.formulas[i] || r.values[i], proposed:value})), proposed_pair:{smiles,inchikey:key}});
        continue;
      }
      for (const [i,value] of pair) if (isBlank(r,i) || textValue(r.values[i]) !== value || r.formulas[i]) add(r,i,value,`Source-reviewed report: ${path.basename(o.report)}`);
    }
    if (o['initialize-ids'] && rows.length) throw new Error('--initialize-ids is allowed only for an empty template; report-only IDs require user direction.');
  } else {
    const patch = await readJson(requireOption(o,'patch'));
    if (!Array.isArray(patch)) throw new Error('Patch must be an array.');
    const seen = new Set();
    for (const item of patch) {
      const id = textValue(item.id), r = byId.get(id), index = HEADERS.indexOf(item.column);
      if (seen.has(`${id}:${index}`)) throw new Error('Duplicate patch target');
      seen.add(`${id}:${index}`);
      if (!r) { absent.push(id); continue; }
      if ((action === 'paper' && index < 5) || (action === 'solvent' && index !== 4)) throw new Error(`Column outside ${action} scope: ${item.column}`);
      if (!textValue(r.values[1]) || r.formulas[1] || /\s/.test(textValue(r.values[1]))) { skipped.push({id, reason:'Missing or incomplete SMILES'}); continue; }
      if (!textValue(item.evidence)) throw new Error(`Source evidence required for ${id}/${item.column}`);
      if (!['string','number'].includes(typeof item.value) || item.value === '' || (typeof item.value === 'number' && !Number.isFinite(item.value))) throw new Error('Patch values must be nonempty literal text or finite numbers.');
      if (!isBlank(r,index) && !approved.has(cell(r.row,index))) { skipped.push({id,cell:cell(r.row,index),reason:'Existing value/formula; outside default blank-only scope'}); continue; }
      add(r,index,item.value,item.evidence);
    }
  }
  const plan = {action, input:master, output, sheet:sheet.name, changes, conflicts, skipped, report_only_ids:absent};
  console.log(JSON.stringify(plan,null,2));
  if (conflicts.length || absent.length) {
    if (o.write) throw new Error('Resolve displayed conflicts or report-only IDs with the user before writing.');
    return;
  }
  if (!o.write) return;
  const python = requireOption(o,'python');
  await fs.mkdir(paths.workspace,{recursive:true});
  await fs.mkdir(paths.review,{recursive:true});
  // Cell authorship remains with the existing spreadsheet adapter. Preserve
  // every other package member instead of accepting an import/export rewrite.
  for (const change of changes) sheet.getRange(change.cell).values = [[typeof change.value === 'string' && change.value.startsWith('=') ? "'"+change.value : change.value]];
  workbook.recalculate();
  const draft = path.join(paths.workspace,`${action}-${randomUUID()}.xlsx`);
  await (await SpreadsheetFile.exportXlsx(workbook)).save(draft);
  const result = spawnSync(python,[path.join(SKILL_ROOT,'scripts','preserve_workbook.py'),
    '--original',master,'--authored',draft,'--output',output,'--sheet',sheet.name,
    '--cells',JSON.stringify(changes.map(c=>c.cell))],{encoding:'utf8'});
  if (result.status !== 0) throw new Error(result.stderr || result.error?.message || 'Workbook preservation failed');
  await atomicWriteText(path.join(paths.workspace,`${action}-${randomUUID()}.json`),JSON.stringify(plan,null,2)+'\n');
}

main().catch(error => { console.error(`STOP: ${error.message}`); process.exitCode=2; });
