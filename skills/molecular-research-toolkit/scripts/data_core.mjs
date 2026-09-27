#!/usr/bin/env node

import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const EVIDENCE_HEADERS = [
  "ID",
  "target_column",
  "status",
  "value",
  "raw_value",
  "raw_unit",
  "source_file",
  "source_location",
  "source_compound_id",
  "notes",
];

export const EVIDENCE_STATUSES = new Set([
  "filled",
  "excluded_by_user",
  "not_found",
  "ambiguous",
  "unreadable",
  "source_unavailable",
]);

export const SKILL_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

export function parseCli(argv, repeatable = new Set()) {
  const parsed = { _: [] };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];

    if (!token.startsWith("--")) {
      parsed._.push(token);
      continue;
    }

    const key = token.slice(2);
    const next = argv[index + 1];
    const value = next === undefined || next.startsWith("--") ? true : next;

    if (value !== true) {
      index += 1;
    }

    if (repeatable.has(key)) {
      parsed[key] ??= [];
      parsed[key].push(value);
    } else {
      if (Object.hasOwn(parsed, key)) {
        throw new Error(`Option --${key} was provided more than once.`);
      }
      parsed[key] = value;
    }
  }

  return parsed;
}

export function requireOption(options, key) {
  const value = options[key];
  if (value === undefined || value === true || String(value).trim() === "") {
    throw new Error(`Missing required option --${key}.`);
  }
  return String(value).trim();
}

export async function pathExists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

export async function readJson(target) {
  let parsed;
  try {
    parsed = JSON.parse(await fs.readFile(target, "utf8"));
  } catch (error) {
    throw new Error(`Cannot read JSON ${target}: ${error.message}`);
  }
  return parsed;
}

export async function loadArtifactTool(nodeModulesPath) {
  const nodeModules = path.resolve(nodeModulesPath);
  const packageRoot = path.join(nodeModules, "package.json");
  const resolver = createRequire(packageRoot);
  let entryPoint;
  try {
    entryPoint = resolver.resolve("@oai/artifact-tool");
  } catch (error) {
    throw new Error(`Cannot resolve @oai/artifact-tool from ${nodeModules}: ${error.message}`);
  }
  return import(pathToFileURL(entryPoint).href);
}

export function validateDate(date) {
  if (!/^\d{8}$/.test(date)) {
    throw new Error("Date must use YYYYMMDD.");
  }

  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(4, 6));
  const day = Number(date.slice(6, 8));
  const parsed = new Date(Date.UTC(year, month - 1, day));

  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    throw new Error(`Invalid calendar date: ${date}.`);
  }

  return date;
}

export function validateTaskname(taskname) {
  if (!/^[a-z0-9][a-z0-9_]*$/.test(taskname)) {
    throw new Error(
      "taskname must start with a lowercase letter or digit and contain only lowercase letters, digits, and underscores.",
    );
  }
  return taskname;
}

export function normalizeHeader(value) {
  return String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase();
}

export function textValue(value) {
  return String(value ?? "").normalize("NFKC").trim();
}

export function parseUsedRange(sheet) {
  const used = sheet.getUsedRange();
  if (!used) {
    throw new Error(`Worksheet ${sheet.name} is empty.`);
  }

  const address = String(used.address ?? "A1").split("!").at(-1).replaceAll("$", "");
  const firstCell = address.split(":")[0];
  const match = firstCell.match(/^([A-Za-z]+)(\d+)$/);
  if (!match) {
    throw new Error(`Cannot parse used range address: ${used.address}.`);
  }

  return {
    values: used.values,
    startRow: Number(match[2]),
    startColumn: lettersToColumn(match[1]),
    address: used.address,
  };
}

export function lettersToColumn(letters) {
  let result = 0;
  for (const character of letters.toUpperCase()) {
    result = result * 26 + character.charCodeAt(0) - 64;
  }
  return result;
}

export function columnToLetters(column) {
  let value = column;
  let output = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    output = String.fromCharCode(65 + remainder) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output;
}

export function findUniqueHeader(headerValues, requested) {
  const target = normalizeHeader(requested);
  const matches = [];
  headerValues.forEach((value, index) => {
    if (normalizeHeader(value) === target) {
      matches.push(index);
    }
  });

  if (matches.length === 0) {
    throw new Error(`Cannot find source column ${JSON.stringify(requested)}.`);
  }
  if (matches.length > 1) {
    throw new Error(`Source column ${JSON.stringify(requested)} is duplicated.`);
  }
  return matches[0];
}

export function spreadsheetValue(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const text = String(value);
  // Evidence values are transcriptions, not calculation inputs. Keep them as
  // written so trailing zeros, inequalities, ranges, and uncertainty survive.
  return text.startsWith("=") ? `'${text}` : text;
}

export function sanitizeTsvValue(value) {
  return String(value ?? "").replace(/[\t\r\n]+/g, " ").trim();
}

export function buildTsv(headers, rows) {
  const lines = [headers.join("\t")];
  for (const row of rows) {
    lines.push(headers.map((header) => sanitizeTsvValue(row[header])).join("\t"));
  }
  return `${lines.join("\n")}\n`;
}

export function parseTsv(text, expectedHeaders) {
  const lines = text.split(/\r?\n/).filter((line) => line !== "");
  if (lines.length === 0) {
    throw new Error("TSV file is empty.");
  }
  const headers = lines[0].split("\t");
  if (headers.length !== expectedHeaders.length || headers.some((value, i) => value !== expectedHeaders[i])) {
    throw new Error(`TSV header must be exactly: ${expectedHeaders.join(" | ")}`);
  }

  return lines.slice(1).map((line, lineIndex) => {
    const fields = line.split("\t");
    if (fields.length !== headers.length) {
      throw new Error(`TSV line ${lineIndex + 2} has ${fields.length} fields; expected ${headers.length}.`);
    }
    return Object.fromEntries(headers.map((header, index) => [header, fields[index]]));
  });
}

export function isInside(parent, child) {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

export function resolveProjectOutput(projectRoot, ...parts) {
  const root = path.resolve(projectRoot);
  const target = path.resolve(root, ...parts);
  if (!isInside(root, target)) {
    throw new Error(`Output path escapes the project root: ${target}.`);
  }
  if (isInside(SKILL_ROOT, target)) {
    throw new Error(`Runtime output must not be written inside the skill source: ${target}.`);
  }
  return target;
}

export function taskPaths(projectRoot, date, taskname) {
  validateDate(date);
  validateTaskname(taskname);
  const taskDirectory = `${date}_${taskname}_data`;
  return {
    workspace: resolveProjectOutput(projectRoot, "workspace", taskDirectory),
    review: resolveProjectOutput(projectRoot, "review", taskDirectory),
    taskDirectory,
  };
}

export async function atomicWriteText(target, content, { replace = false } = {}) {
  if (!replace && await pathExists(target)) {
    throw new Error(`Refusing to overwrite existing file: ${target}.`);
  }

  await fs.mkdir(path.dirname(target), { recursive: true });
  const temporary = `${target}.tmp-${process.pid}-${Date.now()}`;
  await fs.writeFile(temporary, content, "utf8");
  await fs.rename(temporary, target);
}

function bracketFormalCharge(content) {
  const withoutAtomClass = content.replace(/:\d+$/, "");
  const match = withoutAtomClass.match(/([+-]+)(\d*)$/);
  if (!match) {
    if (/[+-]/.test(withoutAtomClass)) {
      throw new Error(`unsupported bracket charge syntax: [${content}]`);
    }
    return 0;
  }

  const signs = match[1];
  const digits = match[2];
  const sign = signs[0];
  if ([...signs].some((character) => character !== sign)) {
    throw new Error(`mixed bracket charge signs: [${content}]`);
  }
  if (digits && signs.length !== 1) {
    throw new Error(`unsupported repeated-and-numbered charge: [${content}]`);
  }

  const magnitude = digits ? Number(digits) : signs.length;
  if (!Number.isSafeInteger(magnitude) || magnitude < 1) {
    throw new Error(`invalid bracket charge magnitude: [${content}]`);
  }
  return sign === "+" ? magnitude : -magnitude;
}

export function fragmentNetFormalCharge(fragment) {
  let charge = 0;
  let cursor = 0;

  while (cursor < fragment.length) {
    const open = fragment.indexOf("[", cursor);
    const closeBeforeOpen = fragment.indexOf("]", cursor);
    if (closeBeforeOpen !== -1 && (open === -1 || closeBeforeOpen < open)) {
      throw new Error(`unmatched closing bracket in fragment ${JSON.stringify(fragment)}`);
    }
    if (open === -1) {
      break;
    }

    const close = fragment.indexOf("]", open + 1);
    if (close === -1) {
      throw new Error(`unmatched opening bracket in fragment ${JSON.stringify(fragment)}`);
    }
    const content = fragment.slice(open + 1, close);
    if (!content || content.includes("[")) {
      throw new Error(`invalid bracket atom in fragment ${JSON.stringify(fragment)}`);
    }
    charge += bracketFormalCharge(content);
    cursor = close + 1;
  }

  return charge;
}

export function selectSmiSmiles(rawValue) {
  const smiles = textValue(rawValue);
  if (!smiles) {
    return { ok: false, reason: "SMILES is blank" };
  }
  if (/\s/.test(smiles)) {
    return { ok: false, reason: "SMILES contains whitespace" };
  }

  const fragments = smiles.split(".");
  if (fragments.length === 1) {
    return {
      ok: true,
      smiles,
      method: "single_fragment_unchanged",
      fragmentCharges: null,
      removedFragments: [],
    };
  }
  if (fragments.some((fragment) => fragment === "")) {
    return { ok: false, reason: "multi-fragment SMILES contains an empty fragment" };
  }

  let fragmentCharges;
  try {
    fragmentCharges = fragments.map((fragment) => ({
      smiles: fragment,
      netFormalCharge: fragmentNetFormalCharge(fragment),
    }));
  } catch (error) {
    return { ok: false, reason: error.message };
  }

  const positive = fragmentCharges.filter((fragment) => fragment.netFormalCharge > 0);
  if (positive.length === 0) {
    return {
      ok: false,
      reason: "multi-fragment SMILES has no explicit net-positive fragment",
    };
  }
  if (positive.length > 1) {
    return {
      ok: false,
      reason: `multi-fragment SMILES has ${positive.length} net-positive fragments`,
    };
  }

  const selected = positive[0];
  return {
    ok: true,
    smiles: selected.smiles,
    method: "unique_cation_fragment",
    fragmentCharges,
    removedFragments: fragmentCharges.filter((fragment) => fragment !== selected),
  };
}

export function normalizeSolvent(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .replace(/[‐‑‒–—−]/g, "-")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export function stripLeadingSolventModifiers(value) {
  let current = normalizeSolvent(value);
  const modifiers = [
    "dry",
    "anhydrous",
    "degassed",
    "deoxygenated",
    "oxygen-free",
    "oxygen free",
    "absolute",
    "hplc-grade",
    "hplc grade",
    "spectroscopic-grade",
    "spectroscopic grade",
  ];

  let changed = true;
  while (changed) {
    changed = false;
    for (const modifier of modifiers) {
      if (current === modifier) {
        current = "";
        changed = true;
        break;
      }
      if (current.startsWith(`${modifier} `) || current.startsWith(`${modifier},`)) {
        current = current.slice(modifier.length).replace(/^[\s,:;]+/, "");
        changed = true;
        break;
      }
    }
  }
  return current;
}

export async function loadSolventMapping(mappingPath) {
  const raw = await readJson(mappingPath);
  const mapping = raw.solvents ?? raw;

  if (!mapping || Array.isArray(mapping) || typeof mapping !== "object") {
    throw new Error("Gaussian solvent mapping must be a JSON object.");
  }

  const entries = Object.entries(mapping).map(([sourceName, keyword]) => {
    if (!sourceName.trim() || typeof keyword !== "string" || !keyword.trim()) {
      throw new Error("Gaussian solvent mapping contains a blank or non-string entry.");
    }
    return {
      sourceName,
      keyword,
      sourceNormalized: normalizeSolvent(sourceName),
      keywordNormalized: normalizeSolvent(keyword),
    };
  });

  const keywords = new Set();
  for (const entry of entries) {
    if (keywords.has(entry.keyword)) {
      throw new Error(`Duplicate Gaussian keyword: ${entry.keyword}.`);
    }
    keywords.add(entry.keyword);
  }

  return { metadata: raw._metadata ?? null, entries };
}

function matchMappingCandidate(candidate, entries) {
  const normalized = normalizeSolvent(candidate);
  const matches = entries.filter(
    (entry) => entry.sourceNormalized === normalized || entry.keywordNormalized === normalized,
  );
  const uniqueKeywords = [...new Set(matches.map((entry) => entry.keyword))];

  if (uniqueKeywords.length > 1) {
    throw new Error(`Ambiguous Gaussian solvent candidate: ${candidate}.`);
  }
  return matches[0] ?? null;
}

export function parseResolutionOptions(values = []) {
  const resolutions = new Map();
  for (const value of values) {
    const separator = String(value).indexOf("=");
    if (separator <= 0 || separator === String(value).length - 1) {
      throw new Error(`Resolution must use RAW=GAUSSIAN_NAME: ${value}.`);
    }
    const rawName = String(value).slice(0, separator).trim();
    const targetName = String(value).slice(separator + 1).trim();
    const key = normalizeSolvent(rawName);
    if (resolutions.has(key)) {
      throw new Error(`Duplicate resolution for ${rawName}.`);
    }
    resolutions.set(key, targetName);
  }
  return resolutions;
}

export function resolveGaussianSolvent(rawValue, mapping, resolutions = new Map()) {
  const raw = textValue(rawValue);
  if (!raw) {
    return { ok: false, reason: "Solvent (manual) is blank" };
  }

  const direct = matchMappingCandidate(raw, mapping.entries);
  if (direct) {
    return { ok: true, keyword: direct.keyword, sourceName: direct.sourceName, method: "exact" };
  }

  const stripped = stripLeadingSolventModifiers(raw);
  if (stripped && stripped !== normalizeSolvent(raw)) {
    const strippedMatch = matchMappingCandidate(stripped, mapping.entries);
    if (strippedMatch) {
      return {
        ok: true,
        keyword: strippedMatch.keyword,
        sourceName: strippedMatch.sourceName,
        method: "modifier_stripped",
      };
    }
  }

  const resolution = resolutions.get(normalizeSolvent(raw));
  if (resolution) {
    const resolvedMatch = matchMappingCandidate(resolution, mapping.entries);
    if (!resolvedMatch) {
      return {
        ok: false,
        reason: `resolved name ${JSON.stringify(resolution)} is not in the Gaussian 16 C.01 mapping`,
      };
    }
    return {
      ok: true,
      keyword: resolvedMatch.keyword,
      sourceName: resolvedMatch.sourceName,
      method: "agent_resolved",
    };
  }

  return { ok: false, reason: "no unique Gaussian 16 C.01 mapping" };
}
