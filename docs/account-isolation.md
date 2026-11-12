# Protect other accounts and private storage

A dedicated agent UID protects only paths whose permissions actually exclude it.
Check private homes, backups, media workspaces and credential directories on every
data disk. A private home does not protect another world-readable directory owned
by that same account. Keep the agent out of privileged or unrelated user groups,
and give it its own private artifact root.

These instructions were checked on Ubuntu 26.04.1 LTS. Install inspection tools
as administrator:

```sh
sudo apt install --no-install-recommends coreutils util-linux acl python3
```

`stat`, `chmod`, `mktemp` and `test` come from coreutils; `namei` and `findmnt`
from util-linux; `getfacl` and `setfacl` from acl. Python supplies the isolated-user
access check below. No extra package is needed for it.

## Inspect before changing anything

As the directory owner or administrator, choose one private root and inspect it:

```sh
SP_PRIVATE_ROOT=/srv/private-owner
stat -c '%a %A %U:%G %n' "$SP_PRIVATE_ROOT"
namei -l "$SP_PRIVATE_ROOT"
getfacl -p -n "$SP_PRIVATE_ROOT"
findmnt --target "$SP_PRIVATE_ROOT" --output TARGET,SOURCE,FSTYPE,OPTIONS
```

Inspect actual service/backup access requirements. Decide whether another account
needs to read or traverse this root before removing its permissions. Check ACLs
as well as mode bits: named users/groups and their effective mask may grant access.
Inspect the actual host mount when working through a sandbox; a read-only sandbox
view does not imply that the underlying filesystem is read-only.

## Owner-only storage: change just the root

If only the owner needs access, mode `0700` is the simplest choice. Record its
original ACL first, then run the change as the owner (or administrator):

```sh
umask 077
SP_PERMISSION_BACKUP=$(mktemp)
getfacl -p -n "$SP_PRIVATE_ROOT" > "$SP_PERMISSION_BACKUP"
chmod 0700 "$SP_PRIVATE_ROOT"
stat -c '%a %U:%G %n' "$SP_PRIVATE_ROOT"
getfacl -p -n "$SP_PRIVATE_ROOT"
```

This removes group/other access at one directory boundary and preserves its owner
and descendants. Directory execute permission controls traversal; removing it
blocks opening descendants through that root even when their individual mode is
`0644`. Do not use `chmod -R`: it changes unrelated file permissions and executable
bits and is unnecessary for this boundary. Keep the permission snapshot privately.

Validate that the owner can still read, write and traverse the root, and check any
existing owner-run workflow. Running services as root are not restricted by these
ordinary permissions. If a non-owner service requires access, address that need
explicitly rather than making the root world-readable again.

To restore the recorded permissions, after reviewing for intervening changes:

```sh
setfacl --restore="$SP_PERMISSION_BACKUP"
```

For a directory with only ordinary mode bits, restoring its recorded mode is also
enough. Do not restore an old snapshot over newer intentional permission changes.

## If existing sharing must remain

Prefer an explicit trusted group or selected read/traverse ACL grants. Mode `0750`
protects a private root only if the agent is excluded from its owning group and
other ACL entries. If existing sharing cannot change yet, a targeted named-user
ACL can exclude just the agent while retaining other access:

```sh
setfacl --no-mask -m u:podcaster:--- "$SP_PRIVATE_ROOT"
```

Use this only after checking ownership and the existing ACL. A named-user entry
matches that UID before group/other entries; it does not override the owner's
rights. The agent must not own the protected directory. `--no-mask` avoids
recalculating an existing effective-rights mask and accidentally expanding other
users' access. This behavior was verified on a disposable directory: the agent
lost listing/traversal/file-read access, the owner retained access and group/other
permissions remained unchanged. Choose owner-only mode or an ACL according to
your actual sharing requirements.

## Validate from the agent account

Run this as the isolated agent, setting the same private root:

```sh
SP_PRIVATE_ROOT=/srv/private-owner
python3 - "$SP_PRIVATE_ROOT" <<'PY'
import os, sys
path = sys.argv[1]
assert not os.access(path, os.R_OK | os.W_OK | os.X_OK)
assert not any(os.access(path, bit) for bit in (os.R_OK, os.W_OK, os.X_OK))
try:
    os.listdir(path)
except PermissionError:
    print('Private directory listing denied')
else:
    raise SystemExit('Unexpected directory listing access')
try:
    os.chdir(path)
except PermissionError:
    print('Private directory traversal denied')
else:
    raise SystemExit('Unexpected directory traversal access')
PY
```

Separately verify the agent can still read/write its own workspace. Record checks
without printing private file contents. Verify owner access remains usable and
the agent cannot list, traverse or look up descendants of the protected root.

Permissions govern new pathname access. They do not revoke already-open file
descriptors, a process's existing working directory, or alternate bind mounts/hard
links outside the protected root. Review alternate access paths, and restart any
pre-existing agent sessions/jobs that may have accessed private storage before
adding credentials. A process-metadata scan may be incomplete because of `/proc`
access restrictions; do not treat it as proof that no open handles exist.

This is account/filesystem isolation, not a complete VM boundary. Explicit
executor service/container restrictions can add another boundary later. Keep
application credentials on the controller where supported, migrate only necessary
access, and recheck other accounts' private roots before introducing credentials.
