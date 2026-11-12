#!/usr/bin/env python3
"""Install/check an isolated, pinned Nostr runtime without sudo or another user's Python."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

PYTHON = '3.11.17'
UV = '0.13.1'
REPO = Path(__file__).resolve().parents[1]
PINS = {'coincurve': '21.0.0', 'websocket-client': '1.9.2', 'bech32': '1.2.0'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.home()/'.local/share/sovereign-podcaster')
    args = parser.parse_args(); os.umask(0o077)
    root = args.root.expanduser().resolve()
    for parent in (root, *root.parents):
        git = parent/'.git'
        if git.is_file() or (git/'HEAD').is_file():
            raise RuntimeError('Install runtime outside Git repositories')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    s = root.stat()
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
        raise RuntimeError('Runtime root must be owner-owned and mode 0700')
    env = {'HOME': str(Path.home()), 'USER': os.environ['USER'], 'LOGNAME': os.environ['USER'],
           'PATH': '/usr/bin:/bin', 'SHELL': '/bin/bash',
           'UV_PYTHON_INSTALL_DIR': str(root/'python'), 'UV_CACHE_DIR': str(root/'uv-cache')}
    bootstrap, runtime = root/'bootstrap-venv', root/'nostr-venv'
    py = runtime/'bin/python'
    code = 'import sys,importlib.metadata as m,json;print(json.dumps({"python":sys.version.split()[0],"packages":{k:m.version(k) for k in '+repr(list(PINS))+'}}))'
    if runtime.exists():
        # A rerun checks the existing environment instead of replacing it.
        info = json.loads(subprocess.check_output([str(py), '-c', code], env=env, text=True))
        if info != {'python': PYTHON, 'packages': PINS}:
            raise RuntimeError('Existing runtime differs from tested pins; inspect it before replacement')
    else:
        if not bootstrap.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(bootstrap)], env=env, check=True)
        subprocess.run([str(bootstrap/'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--only-binary=:all:', 'uv=='+UV], env=env, check=True)
        uv = str(bootstrap/'bin/uv')
        subprocess.run([uv, 'venv', '--managed-python', '--python', PYTHON, str(runtime)], env=env, check=True)
        subprocess.run([uv, 'pip', 'install', '--python', str(py), '--only-binary', ':all:',
                        '-r', str(REPO/'skills/nostr-publishing/scripts/requirements.txt')], env=env, check=True)
        info = json.loads(subprocess.check_output([str(py), '-c', code], env=env, text=True))
        if info != {'python': PYTHON, 'packages': PINS}: raise RuntimeError('Installed runtime differs from pins')
    (root/'nostr-runtime.lock.txt').write_text('\n'.join(k+'=='+v for k,v in sorted(PINS.items()))+'\n')
    print(json.dumps(dict(info, python_executable=str(py), uv_bootstrap_version=UV), indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error: raise SystemExit(str(error))
