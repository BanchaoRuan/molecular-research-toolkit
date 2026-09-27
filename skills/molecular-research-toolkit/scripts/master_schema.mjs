import { textValue } from './data_core.mjs';

export const HEADERS = ['ID', 'SMILES', 'InChIKey', 'Solvent (manual)', 'Solvent (AI-assisted)',
  'λmax (nm)', 'τ (μs)', 'E0,0 (eV)', 'Ered (V vs. SCE)', 'Eox (V vs. SCE)',
  '*Ered (V vs. SCE)', '*Eox (V vs. SCE)', 'Refs.'];

export function readMaster(workbook, sheetName) {
  const sheet = sheetName ? workbook.worksheets.getItem(sheetName) : workbook.worksheets.getItemAt(0);
  const headers = sheet.getRange('B3:N3').values[0];
  if (HEADERS.some((h, i) => headers[i] !== h) || sheet.getRange('B2').values[0][0] !== 'fixed'
      || sheet.getRange('G2').values[0][0] !== 'data from paper') {
    throw new Error('Master must use the supplied template: fixed at B2:E2, data from paper at G2:N2, exact B3:N3 headers. Ask about a nonconforming workbook; do not guess a mapping.');
  }
  const used = sheet.getUsedRange();
  const end = Number(String(used.address).split(':').at(-1).match(/\d+$/)[0]);
  const rows = [];
  const ids = new Set();
  if (end >= 4) {
    const values = sheet.getRange(`B4:N${end}`).values;
    const formulas = sheet.getRange(`B4:N${end}`).formulas;
    values.forEach((value, i) => {
      if (value.every(v => v === null || v === '') && formulas[i].every(v => !v)) return;
      const id = textValue(value[0]);
      if (!/^[A-Za-z0-9_-]+$/.test(id) || ids.has(id)) throw new Error(`Invalid or duplicate ID at row ${i+4}: ${id}`);
      ids.add(id);
      rows.push({ id, row: i+4, values: value, formulas: formulas[i] });
    });
  }
  return { sheet, rows };
}

export function isBlank(row, index) {
  return !row.formulas[index] && (row.values[index] === null || row.values[index] === undefined || row.values[index] === '');
}

export const cell = (row, index) => `${String.fromCharCode(66 + index)}${row}`;
