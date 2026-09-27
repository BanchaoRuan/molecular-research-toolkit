#!/usr/bin/env python3
"""Inspect released requirements, check the selected interpreter, or report upstream updates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
SKILL = Path(__file__).resolve().parent.parent
COMPONENTS = ('molecule-image-prep', 'image-to-smiles', 'literature-solvent-extraction')


def module_root(name):
    # Distribution layout and generic installed layout are both explicit.
    for path in (SKILL.parent / 'modules' / name, SKILL.parent / name):
        if (path / 'SKILL.md').is_file():
            return path
    raise ValueError(f'Module {name} is not installed beside the package entry or under skills/modules')


def requirements(names):
    result = {}
    for name in names:
        file = module_root(name) / 'requirements.txt'
        if not file.exists():
            continue
        for raw in file.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            package, version = line.split('==', 1)
            key = package.lower().replace('_','-')
            if key in result and result[key]['supported'] != version:
                raise ValueError(f'Conflicting component requirements for {package}')
            result.setdefault(key, {'package':package, 'supported':version, 'components':[]})['components'].append(name)
    return list(result.values())


def check(names):
    status = 0
    for name in names:
        if name == 'literature-solvent-extraction':
            print('AGENT CHECK REQUIRED: spreadsheet, PDF/browser, source access, evidence capture; no dedicated Python packages.')
            continue
        command = [sys.executable, str(module_root(name) / 'scripts/validate_setup.py')]
        if name == 'image-to-smiles':
            command.append('--models')
        result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
        if result.returncode != 0:
            # A subprocess terminated by a signal has a negative return code.
            # It must not be discarded by max(0, returncode).
            print(f'STOP: {name} dependency check exited with {result.returncode}', file=sys.stderr)
            status = 1
    return status


def check_install_python(names):
    """Reject incompatible interpreters before pip changes the environment."""
    try:
        from packaging.specifiers import SpecifierSet
    except ImportError:
        # A new environment may have pip but not yet have standalone packaging.
        # Use pip's bundled parser for bootstrap only; no install happens here.
        from pip._vendor.packaging.specifiers import SpecifierSet
    version = '.'.join(str(part) for part in sys.version_info[:3])
    for name in names:
        declaration = module_root(name) / 'dependencies.json'
        if not declaration.is_file():
            if name == 'literature-solvent-extraction':
                continue
            raise ValueError(f'Missing dependency declaration: {declaration}')
        required = json.loads(declaration.read_text())['python']
        if not SpecifierSet(required).contains(version):
            raise ValueError(f'{name} requires Python {required}; this interpreter is {version}. Select a compatible environment first.')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check','requirements','install','updates'])
    p.add_argument('--component', choices=['all',*COMPONENTS], default='all')
    p.add_argument('--apply', action='store_true', help='Install into this interpreter only after user authorization')
    p.add_argument('--output', type=Path, help='Save upstream report; refuses an existing path')
    a = p.parse_args(argv)
    names = COMPONENTS if a.component == 'all' else (a.component,)
    if a.action == 'check':
        return check(names)
    reqs = requirements(names)
    if a.action == 'requirements':
        print('\n'.join(f"{r['package']}=={r['supported']}" for r in reqs))
        return 0
    if a.action == 'install':
        command = [sys.executable, '-m', 'pip', 'install', *[f"{r['package']}=={r['supported']}" for r in reqs]]
        print(json.dumps({'interpreter':sys.executable,'command':command,'system_prerequisites':'Tesseract >=5 for image-to-smiles; see INSTALL.md','apply':a.apply},indent=2))
        if not reqs:
            return check(names)
        if not a.apply:
            return 0
        try:
            check_install_python(names)
        except (ImportError, OSError, ValueError, KeyError) as exc:
            p.error(f'Cannot install into this interpreter: {exc}')
        result = subprocess.run(command)
        return result.returncode or check(names)
    results = []
    for r in reqs:
        try:
            url = f"https://pypi.org/pypi/{r['package']}/json"
            request = urllib.request.Request(url, headers={'User-Agent':'molecular-research-toolkit dependency check'})
            with urllib.request.urlopen(request, timeout=25) as response:
                data = json.load(response)
            latest = data['info']['version']
            results.append({**r, 'latest':latest, 'different_release_available':latest != r['supported'], 'source':url})
        except (OSError, ValueError, KeyError) as exc:
            results.append({**r, 'error':str(exc)})
    report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'policy':'Information only. Validate a component before changing its supported requirements.', 'dependencies':results}
    content = json.dumps(report, indent=2)+'\n'
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open('x') as stream:
            stream.write(content)
    else:
        print(content)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as stream:
            stream.write('## Dependency review\n\n| Package | Supported | Upstream stable |\n|---|---|---|\n')
            for r in results:
                stream.write(f"| {r['package']} | {r['supported']} | {r.get('latest','Check failed')} |\n")
            stream.write('\nNew upstream releases are review candidates, not automatic upgrades. See the JSON artifact for sources and failures.\n')
    return 1 if any('error' in r for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())
