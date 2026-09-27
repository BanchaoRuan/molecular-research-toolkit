#!/usr/bin/env python3
"""Copy an XLSX package, replacing only explicitly authored cell values.

The spreadsheet adapter authors the new values. This final packaging step keeps
unrelated workbook ZIP members byte-identical, including charts and formulas.
Only .xlsx, ordinary cells, and an existing sheet are supported.
"""
import argparse
import copy
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
import zipfile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def sheet_path(z, name):
    sheets = ET.fromstring(z.read("xl/workbook.xml"))
    matches = [s for s in sheets.find("s:sheets", NS) if s.get("name") == name]
    if len(matches) != 1:
        raise ValueError("Expected one target sheet")
    rid = matches[0].get(REL)
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    return target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)


def patch_package(original, authored, output, sheet, addresses):
    if output.exists() or original.resolve() == output.resolve():
        raise ValueError("Output already exists or is the input; no overwrite is allowed")
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(authored) as draft:
        target = sheet_path(source, sheet)
        text = source.read(target).decode("utf-8")
        prefix_match = re.search(r"<((?:[A-Za-z_][\w.-]*:)?)sheetData\b", text)
        if not prefix_match or any(n.startswith("_xmlsignatures/") for n in source.namelist()):
            raise ValueError("Unsupported sheet serialization or signed workbook; use the agent's native spreadsheet tools")
        q = prefix_match.group(1)
        original_tree = ET.fromstring(source.read(target))
        original_rows = {r.get('r'): r for r in original_tree.findall('s:sheetData/s:row', NS)}
        template_cells = {c.get('r'): c for c in original_tree.findall('.//s:row[@r="4"]/s:c', NS)}
        tree = ET.fromstring(draft.read(sheet_path(draft, sheet)))
        cells = {c.get("r"): c for c in tree.findall(".//s:sheetData/s:row/s:c", NS)}
        strings = []
        if "xl/sharedStrings.xml" in draft.namelist():
            strings = ["".join(si.itertext()) for si in ET.fromstring(draft.read("xl/sharedStrings.xml"))]
        for address in addresses:
            if not re.fullmatch(r"[B-N][1-9][0-9]*", address):
                raise ValueError(f"Invalid master-table cell: {address}")
            cell = cells.get(address)
            if cell is None or cell.find("s:f", NS) is not None:
                raise ValueError(f"Authored cell {address} missing or contains a formula")
            value = cell.find("s:v", NS)
            kind = cell.get("t", "n")
            if kind in ("s", "inlineStr", "str"):
                raw = strings[int(value.text)] if kind == "s" else ("".join(cell.find("s:is", NS).itertext()) if kind == "inlineStr" else value.text or "")
                payload = f'<{q}is><{q}t xml:space="preserve">' + escape(raw) + f'</{q}t></{q}is>'
                type_attribute = ' t="inlineStr"'
            elif kind in ("n", "b") and value is not None:
                payload = f"<{q}v>" + escape(value.text or "") + f"</{q}v>"
                type_attribute = f' t="{kind}"'
            else:
                raise ValueError(f"Unsupported authored value at {address}")
            pattern = re.compile(r'<' + q + r'c\b(?=[^>]*\br="' + address + r'")[^>]*?(?:/>|>.*?</' + q + r'c>)', re.S)
            old = pattern.search(text)
            if old:
                opening = old.group().split(">", 1)[0].rstrip("/")
                opening = re.sub(r'\s+t="[^"]*"', "", opening)
                replacement = opening + type_attribute + ">" + payload + f"</{q}c>"
                text = text[:old.start()] + replacement + text[old.end():]
            else:
                row_number = int(re.search(r"\d+", address).group())
                row_pattern = re.compile(r'<' + q + r'row\b(?=[^>]*\br="' + str(row_number) + r'")[^>]*?(?:/>|>.*?</' + q + r'row>)', re.S)
                row = row_pattern.search(text)
                style = ''
                template_cell = template_cells.get(address[0] + '4')
                if str(row_number) not in original_rows and template_cell is not None and template_cell.get('s'):
                    style = f' s="{template_cell.get("s")}"'
                replacement = f'<{q}c r="{address}"{style}{type_attribute}>{payload}</{q}c>'
                if row:
                    row_text = row.group()
                    if row_text.endswith("/>"):
                        updated = row_text[:-2] + ">" + replacement + f"</{q}row>"
                    else:
                        later = next((m for m in re.finditer(r'<' + q + r'c\b[^>]*\br="([A-Z]+)\d+"', row_text) if (len(m.group(1)), m.group(1)) > (1, address[0])), None)
                        offset = later.start() if later else row_text.rfind(f"</{q}row>")
                        updated = row_text[:offset] + replacement + row_text[offset:]
                    text = text[:row.start()] + updated + text[row.end():]
                else:
                    sizing = ''
                    if '4' in original_rows:
                        sizing = ''.join(f' {key}="{original_rows["4"].get(key)}"' for key in ('ht','customHeight') if original_rows['4'].get(key))
                    new_row = f'<{q}row r="{row_number}"{sizing}>{replacement}</{q}row>'
                    later = next((m for m in re.finditer(r'<' + q + r'row\b[^>]*\br="(\d+)"', text) if int(m.group(1)) > row_number), None)
                    offset = later.start() if later else text.index(f"</{q}sheetData>")
                    text = text[:offset] + new_row + text[offset:]
        # Extend dimensions only when adding IDs to an empty template.
        dim = re.search(r'<' + q + r'dimension ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', text)
        if dim and addresses:
            last = max(int(re.search(r"\d+", a).group()) for a in addresses)
            if last > int(dim.group(4)):
                text = text[:dim.start(4)] + str(last) + text[dim.end(4):]
        updated_tree = ET.fromstring(text)
        untouched = lambda tree: {c.get('r'): ET.tostring(c) for c in tree.findall('.//s:sheetData/s:row/s:c', NS) if c.get('r') not in addresses}
        if untouched(original_tree) != untouched(updated_tree):
            raise ValueError('Non-target cells changed during packaging; no output written')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle, zipfile.ZipFile(handle, "w") as out:
            for item in source.infolist():
                out.writestr(copy.copy(item), text.encode("utf-8") if item.filename == target else source.read(item.filename))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--authored", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--sheet", required=True)
    p.add_argument("--cells", required=True, help="JSON array of explicitly changed cell addresses")
    a = p.parse_args()
    patch_package(a.original, a.authored, a.output, a.sheet, json.loads(a.cells))


if __name__ == "__main__":
    main()
