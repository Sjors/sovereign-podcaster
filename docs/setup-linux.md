# Create the isolated agent account on Ubuntu

The default setup has two machines: an **agent machine** prepares media, and a
**podcast host** serves the podcast. Create the new user on the agent machine.
An administrator runs system setup; the agent account receives no sudo access.
The first slide demo needs no hosting credentials or remote access.

## Tested environment

Inspected on **Ubuntu 26.04.1 LTS (Resolute Raccoon), x86-64**, 2026-11-01.
Python 3.14.4 runs the offline slide builder and its three tests successfully.
Other distributions/releases have not been validated here. UID/GID values and
storage roots are host-specific; choose them for your own installation. See the
[account/storage isolation guide](account-isolation.md) for inspection, minimal
permission changes, rollback and limits. Validate sudo policy, group membership
and private-path access before adding credentials.

## 1. Install the base tools

Run from your existing administrator account on the agent machine:

```sh
sudo apt update
sudo apt install --no-install-recommends \
  bash ca-certificates coreutils git libc-bin passwd python3 sudo util-linux \
  openssh-client
```

The command supplies the prerequisites and can install available updates. The
slide tool needs only Python's standard library, without pip or venv.

| Commands used in this guide | Apt package |
| --- | --- |
| `bash` | `bash` |
| `env`, `install`, `chmod`, `id`, `stat`, `df`, `test`, `cat` | `coreutils` |
| `getent` | `libc-bin` |
| `useradd`, `passwd` | `passwd` |
| `sudo` | `sudo` (administrator only) |
| `runuser` if preferred by an administrator | `util-linux` |
| `git` | `git`, plus `ca-certificates` for HTTPS |
| `python3` | `python3` |
| `ssh`, `ssh-keygen`, `ssh-keyscan`, `ssh-copy-id` | `openssh-client` |

An SSH client suffices; no SSH server on the agent machine is required for this
step. For a shared agent/hosting machine, omit `openssh-client` unless otherwise
needed and skip the SSH section below.

## 2. Create the user and private directories

Choose an artifact root on a filesystem with space for original audio, lossless
caches and several video revisions. The portable default is
`/srv/sovereign-podcaster`; change it to a directory on your mounted data disk if
appropriate. Run this complete block from the administrator account. It refuses
existing accounts/groups/destinations rather than taking them over. If it stops
after partially creating the account, inspect that state before continuing.

```sh
SP_ARTIFACT_ROOT=/srv/sovereign-podcaster

sudo env SP_ARTIFACT_ROOT="$SP_ARTIFACT_ROOT" /bin/bash <<'SETUP'
set -eu
SP_USER=podcaster
SP_HOME=/home/podcaster
case "$SP_ARTIFACT_ROOT" in
  /*) ;;
  *) echo 'Artifact root must be absolute' >&2; exit 1 ;;
esac
if getent passwd "$SP_USER" >/dev/null || getent group "$SP_USER" >/dev/null; then
  echo 'Account or group already exists; inspect it before proceeding' >&2
  exit 1
fi
for SP_PATH in "$SP_HOME" "$SP_ARTIFACT_ROOT"; do
  if [ -e "$SP_PATH" ] || [ -L "$SP_PATH" ]; then
    echo "Destination already exists: $SP_PATH" >&2
    exit 1
  fi
done
useradd --create-home --user-group --home-dir "$SP_HOME" \
  --shell /bin/bash -K HOME_MODE=0700 "$SP_USER"
passwd --lock "$SP_USER"
chmod 0700 "$SP_HOME"
install -d -m 0700 -o "$SP_USER" -g "$SP_USER" \
  "$SP_HOME/src" "$SP_HOME/.ssh" "$SP_HOME/.config" \
  "$SP_HOME/.config/sovereign-podcaster" "$SP_HOME/.local" \
  "$SP_HOME/.local/bin" "$SP_HOME/.local/share" \
  "$SP_HOME/.local/share/sovereign-podcaster" "$SP_HOME/capabilities" \
  "$SP_ARTIFACT_ROOT" "$SP_ARTIFACT_ROOT/work" \
  "$SP_ARTIFACT_ROOT/episodes" "$SP_ARTIFACT_ROOT/cache"
id "$SP_USER"
passwd --status "$SP_USER"
stat -c '%a %U:%G %n' "$SP_HOME" "$SP_HOME/.ssh" "$SP_ARTIFACT_ROOT"
df -h "$SP_ARTIFACT_ROOT"
SETUP
```

Expect only the `podcaster` group, a locked password (`L`), and mode `700` owned
by `podcaster:podcaster` on the displayed directories. Do not add the agent to
`sudo`, `docker`, `lxd`, `disk` or your existing user group. Check local sudo policy
for blanket rules before running an agent. Password locking blocks password
authentication; it does not revoke other grants.

From the administrator account, `sudo -l -U podcaster` should report that the new
user is not allowed to run sudo commands. If local policy grants it anything,
inspect that policy before starting the agent.

The home holds source and private configuration; the artifact root holds inputs,
outputs, logs and caches. Keep the existing workflow and access working.

## 3. Enter a clean shell and fetch source

Run from the administrator account:

```sh
sudo -u podcaster env -i \
  HOME=/home/podcaster USER=podcaster LOGNAME=podcaster \
  PATH=/usr/bin:/bin SHELL=/bin/bash \
  /bin/bash --noprofile --norc
```

Run the next block **inside that shell**, using the artifact root you chose:

```sh
umask 077
cd "$HOME"
SP_ARTIFACT_ROOT=/srv/sovereign-podcaster

git -c credential.helper= clone \
  https://github.com/Sjors/sovereign-podcaster.git "$HOME/src/sovereign-podcaster"
git -C "$HOME/src/sovereign-podcaster" remote set-url --push origin disabled://read-only
git -C "$HOME/src/sovereign-podcaster" config --local credential.helper ''
cd "$HOME/src/sovereign-podcaster"
python3 -m unittest discover -s tests -v
python3 tools/slides.py build --transcript examples/transcript.json \
  --plan examples/slides.json --out "$SP_ARTIFACT_ROOT/episodes/synthetic/r001"
python3 tools/slides.py verify "$SP_ARTIFACT_ROOT/episodes/synthetic/r001"
```

Clone after the maintainer has signed and pushed the initial repository, or use
the [private bootstrap and source-sync method](executor-sync.md) while it remains
unpublished. HTTPS
needs no GitHub authentication. The disabled push URL guards against accidents;
withholding write credentials supplies read-only remote access. For filesystem-
read-only source, an administrator can install a reviewed root-owned snapshot.
Keep generated files outside the source tree.

Inspect the synthetic revision's `index.html` using an operator-approved local
copy or existing file-viewing arrangement. On a rerun choose a new revision
directory; the builder preserves old revisions. `exit` returns to the admin shell.

## 4. Check isolation before adding credentials

In the clean shell run `id`, then check environment names without printing values:

```sh
python3 - <<'PY'
import os
for name in ('SSH_AUTH_SOCK', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_HOME',
             'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
    print(name, 'present' if name in os.environ else 'absent')
PY
```

All should be absent at this stage. Check the actual private home, chat/auth and
backup paths using `test -r PATH`, reporting yes/no rather than contents. Check
directory traversal and representative files. Separate users do not hide world-
readable data or ACL grants; audit those before claiming full isolation. Correct
identified exposure or restrict the executor service/container deliberately.
Do not recursively chmod existing shared storage.
Follow the [account/storage isolation guide](account-isolation.md) to protect
private roots while preserving any access that existing services actually need.

Do not copy a home, `.ssh`, `.codex`, shell profile, cloud/Git authentication or
agent socket. Later install a fresh harness runtime and selected reviewed skills;
keep all secrets outside repositories. [Portable layout](setup.md) describes the
separation of code, artifacts and configuration.

## 5. Remote podcast-host access, when needed

Create a fresh key inside the isolated shell; never overwrite an existing key:

```sh
test ! -e "$HOME/.ssh/id_ed25519_podcast" && \
  ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519_podcast" -C sovereign-podcaster
```

Use a passphrase for interactive use. Decide separately how an unattended agent
will unlock its own key; do not share or forward your existing SSH agent. Transfer
only the `.pub` file to the podcast-host administrator. Save this configuration in
`$HOME/.ssh/config`, replacing the address/user with your actual host:

```sshconfig
Host podcast-host
    HostName podcast.example.org
    User podcast
    Port 22
    IdentityFile ~/.ssh/id_ed25519_podcast
    IdentitiesOnly yes
    IdentityAgent none
    ForwardAgent no
    ClearAllForwardings yes
    ControlMaster no
    ControlPath none
    StrictHostKeyChecking yes
    UserKnownHostsFile ~/.ssh/known_hosts
```

Install the server's host key in `known_hosts` only after independently verifying
its fingerprint through an existing trusted connection or console. `ssh-keyscan`
can collect a candidate key but does not establish authenticity. Set both config
and known_hosts to mode `600`. Do not disable strict host checking.

The host administrator inspects and backs up `authorized_keys`, then adds only
the new public key, preserving old entries and correct permissions. Consider the
`restrict` key option to disable forwarding/PTY/user rc. It still permits arbitrary
commands as the target user; use a forced-command wrapper or narrower staging
account if needed. Do not grant broad sudo to solve access problems.

Test from the isolated shell after host-key verification and key authorization:

```sh
ssh -F "$HOME/.ssh/config" -o BatchMode=yes podcast-host 'id'
```

Confirm the intended remote user, then test reviewed helper read-only interfaces
when available. Verify old access separately before proposing its removal. Record
fingerprints/results privately; never record private-key bytes. A working SSH
connection grants no authorization for uploads, publishing or upgrades.

The isolated account's fresh outbound key was subsequently created and validated
on 2026-11-01. It pins the host's ED25519 key verified through the existing trusted
connection and uses no shared/forwarded agent. The server grant uses `restrict`;
existing maintainer keys remain authorized. This confirms the expected hosting
service UID and SSH access, not installation of the new publishing helpers or
permission to remove the old account. Public-key evidence remains private.

## If agent and podcast host share a machine

Keep the isolated user, private directories and clean environment. Skip SSH and
run the reviewed podcast-side commands locally instead of wrapping them in `ssh`.
Paths, explicit show selection, maintenance guards, destination checks and approval
requirements remain the same.

Local execution still needs deliberate, minimal command/file access to the
hosting account. Do not copy hosting secrets, join a broad hosting group or grant
unrestricted `sudo -u` access. Transport integration is a later stage; the current
slide component works on either topology without hosting access.

## Optional apt dependencies for later stages

Install each group as administrator when its stage needs it:

```sh
# Existing media renderer: FFmpeg/ffprobe, fonts and Pillow.
sudo apt install --no-install-recommends ffmpeg fontconfig fonts-ubuntu python3-pil

# Private virtual environments for future API/publishing libraries.
sudo apt install --no-install-recommends python3-venv

# Optional downloads and file/archive transfer.
sudo apt install --no-install-recommends curl rsync tar

# Optional JavaScript/source-capture or executor-installation tooling.
sudo apt install --no-install-recommends nodejs node-corepack

# Optional persistent executor service management/validation.
sudo apt install --no-install-recommends systemd
```

Corepack is provided by `node-corepack`; it can run `corepack npm`.
Browser installation is deferred until source capture needs it; document its
package/install method when selecting it. Offline source images need no browser.
Record actual package/runtime/font versions with the first reproducible render.
Continue the existing local Whisper workflow when transcription is needed.

Add publishing credentials incrementally after offline slides/video work. Preserve
the operator's maintenance guard when changing paths/users. The
[Nostr setup guide](nostr-setup.md) documents its independent runtime, identity
migration and explicitly authorized post/delete check. The
[Agents API experiment](../adapters/openai-agents/README.md) is a separate stage
requiring its own account/credit verification. Initial setup authorizes no uploads
or publication.

## Before enabling production

The isolated user runs both the operator/controller and executor. Maintenance
state is private and user-owned; ordinary task details do not require sudo
approval. Read [operational backstops](backstops.md) before enabling production.
New operators must supply/test hosting-system backups (including Blossom/relay
where colocated), offline original audio and recoverable source/configuration/
state. A verified provider-enforced per-task token/spending limit remains a TODO;
local timeouts and billing observations do not implement one. An optional two-user
operator/temporary-backup design is future work in TODO.
