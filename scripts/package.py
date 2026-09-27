#!/usr/bin/env python3
"""Verify recorded component snapshots and make independent skill/tool ZIPs."""
import argparse
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
COMPONENT_PATHS = {
    'molecule-image-prep': 'skills/modules/molecule-image-prep',
    'image-to-smiles': 'skills/modules/image-to-smiles',
    'literature-solvent-extraction': 'skills/modules/literature-solvent-extraction',
    'barkla_redox': 'tools/barkla_redox',
}
EXCLUDE = {'.git', '__pycache__', '.ds_store', 'thumbs.db', 'desktop.ini',
           'node_modules', '.venv', '.conda', '.ssh', '.aws', '.azure', '.gcloud'}
ROOT_EXCLUDE = {'workspace', 'review', 'dist'}
PRIVATE_PATTERNS = ('.env', '.env.*', '.netrc', '.npmrc', '.pypirc',
                    '*.pem', '*.key', '*.p12', '*.pfx',
                    'id_rsa*', 'id_dsa*', 'id_ecdsa*', 'id_ed25519*',
                    'credentials*', 'secrets*', 'tokens*', 'cookies*', 'auth.json')


def files(directory):
    # Git ignore rules do not apply to ZIP creation. Keep this filter explicit.
    return sorted(p for p in directory.rglob('*') if p.is_file() and not p.is_symlink() and
                  p.relative_to(directory).parts[0] not in ROOT_EXCLUDE and
                  not any(part.casefold() in EXCLUDE or
                          any(fnmatchcase(part.casefold(), pattern) for pattern in PRIVATE_PATTERNS)
                          for part in p.relative_to(directory).parts) and
                  p.suffix not in {'.pyc', '.pyo', '.pyd'} and
                  not p.name.endswith('.inspect.ndjson'))


def fingerprint(directory):
    return {p.relative_to(directory).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files(directory)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, default=ROOT/'dist')
    p.add_argument('--check', action='store_true', help='Verify snapshots without creating files')
    p.add_argument('--record', action='store_true', help='Record reviewed component file hashes locally; does not synchronize or publish')
    a = p.parse_args()
    if a.record:
        entries = []
        for name, relative in COMPONENT_PATHS.items():
            directory = ROOT/relative
            entries.append({'name':name, 'path':directory.relative_to(ROOT).as_posix(),
                            'revision':None, 'files':fingerprint(directory)})
        record = {'toolkit_version':(ROOT/'VERSION').read_text().strip(),
                  'note':'Local reviewed snapshots. Set real private-repository revisions after maintainer synchronization; no commit is implied by a file hash.',
                  'components':entries}
        (ROOT/'components.json').write_text(json.dumps(record,indent=2)+'\n')
        print('Recorded component hashes; revision fields are null until real revisions are selected')
        return
    manifest = json.loads((ROOT/'components.json').read_text())
    version = (ROOT/'VERSION').read_text().strip()
    if manifest.get('toolkit_version') != version:
        p.error('VERSION and components.json disagree. Update the reviewed release metadata before packaging.')
    components = manifest.get('components', [])
    if (len(components) != len(COMPONENT_PATHS) or
            {item.get('name'):item.get('path') for item in components} != COMPONENT_PATHS):
        p.error('components.json must record all four components at their declared paths.')
    for item in components:
        actual = fingerprint(ROOT/item['path'])
        if actual != item['files']:
            p.error(f"Component snapshot differs from components.json: {item['name']}. Refresh from the tested component source, then record its hashes.")
    if a.check:
        print(f'PASS: toolkit {version}; all four component snapshots match their recorded file hashes')
        return
    out = a.output_dir.resolve()
    packages = {
        'molecular-research-toolkit-skills.zip': files(ROOT/'skills'),
        'barkla-redox.zip': files(ROOT/'tools/barkla_redox'),
        'molecular-research-toolkit-all.zip': files(ROOT),
    }
    for name in [*packages,'SHA256SUMS.txt']:
        if (out/name).exists():
            p.error(f'Output exists: {out/name}; choose a fresh build directory')
    out.mkdir(parents=True, exist_ok=True)
    sums=[]
    for name, entries in packages.items():
        with zipfile.ZipFile(out/name,'x',zipfile.ZIP_DEFLATED) as archive:
            for file in entries:
                # Separate downloads retain useful outer/runtime folder boundaries.
                base = ROOT/'tools' if name == 'barkla-redox.zip' else ROOT
                prefix = '' if name == 'barkla-redox.zip' else 'molecular-research-toolkit/'
                arcname = prefix + file.relative_to(base).as_posix()
                info = zipfile.ZipInfo(arcname, date_time=(2000,1,1,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info,file.read_bytes())
        sums.append(hashlib.sha256((out/name).read_bytes()).hexdigest()+'  '+name)
        print(f'{name}: {len(entries)} files')
    (out/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n')


if __name__ == '__main__':
    main()
