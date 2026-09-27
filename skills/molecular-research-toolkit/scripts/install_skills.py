#!/usr/bin/env python3
"""Copy four discoverable skill folders to an agent-selected directory. Preview is the default."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

SKILL = Path(__file__).resolve().parent.parent
NAMES = ('molecular-research-toolkit','molecule-image-prep','image-to-smiles','literature-solvent-extraction')
IGNORED_NAMES = {'.git', '.DS_Store', 'Thumbs.db', '__pycache__'}


def source_files(directory):
    """Compare maintained files without treating local caches as obsolete code."""
    return [file for file in directory.rglob('*') if file.is_file()
            and not any(part in IGNORED_NAMES for part in file.relative_to(directory).parts)
            and file.suffix not in {'.pyc', '.pyo'}]


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skills-dir', type=Path, required=True, help="Agent's confirmed discovery directory")
    p.add_argument('--write', action='store_true')
    p.add_argument('--update', action='store_true', help='Explicitly replace previously installed files; no files are deleted')
    a = p.parse_args()
    target = a.skills_dir.expanduser().resolve()
    sources = {name:SKILL if name == NAMES[0] else SKILL.parent/'modules'/name for name in NAMES}
    plans = []
    for name, source in sources.items():
        if not (source/'SKILL.md').is_file():
            p.error(f'Missing packaged component: {source}')
        destination = target/name
        if destination == source.resolve() or source.resolve() in destination.parents or destination in source.resolve().parents:
            p.error('Installation destination must be separate from the downloaded source tree')
        # All destinations are checked before any copy occurs.
        if destination.exists() and not a.update:
            p.error(f'Destination exists: {destination}; review differences before --update')
        changed, stale = [], []
        if destination.exists():
            changed = [str(f.relative_to(source)) for f in source_files(source) if not (destination/f.relative_to(source)).is_file() or digest(f) != digest(destination/f.relative_to(source))]
            stale = [str(f.relative_to(destination)) for f in source_files(destination) if not (source/f.relative_to(destination)).exists()]
        if stale:
            p.error(f'Obsolete installed files in {destination}: {stale}. Ask the user about removal or use a fresh discovery directory; this installer does not delete files.')
        plans.append({'source':str(source),'destination':str(destination),'changed_files':changed})
    print(json.dumps({'write':a.write,'plan':plans,'next':'Have the agent confirm that all four SKILL.md entries are discovered; use each module directly.'},indent=2))
    if a.write:
        target.mkdir(parents=True, exist_ok=True)
        for item in plans:
            shutil.copytree(item['source'],item['destination'],dirs_exist_ok=a.update,
                            ignore=shutil.ignore_patterns(*IGNORED_NAMES, '*.pyc', '*.pyo'))


if __name__ == '__main__':
    main()
