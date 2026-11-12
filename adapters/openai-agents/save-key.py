#!/usr/bin/env python3
"""Save a key using hidden terminal input; never accept the secret as an argument."""
import argparse
import getpass
import os
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('path', type=Path)
    args = p.parse_args()
    os.umask(0o077)
    if not sys.stdin.isatty():
        p.exit(1, 'Run interactively in a terminal; do not pipe or paste a key into chat.\n')
    args.path = args.path.expanduser().absolute()
    markers = [parent / '.git' for parent in args.path.parents]
    if any(marker.is_file() or (marker / 'HEAD').is_file() for marker in markers):
        p.exit(1, 'Store credentials outside Git repositories.\n')
    parent = args.path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or parent.stat().st_uid != os.getuid():
        p.exit(1, 'Secret directory must belong to this user and must not be a symlink.\n')
    parent.chmod(0o700)
    if args.path.exists() or args.path.is_symlink():
        p.exit(1, 'Destination exists; refusing to overwrite a key.\n')
    secret = getpass.getpass('Paste the key (hidden): ').strip()
    if not secret or any(c.isspace() for c in secret):
        p.exit(1, 'Expected one nonempty credential without whitespace.\n')
    fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(secret + '\n')
        f.flush()
        os.fsync(f.fileno())
    print('Key saved with owner-only permissions; value not displayed.')


if __name__ == '__main__':
    main()
