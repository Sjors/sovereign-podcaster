# Setup

Select [PPQ or Codex](llm-providers.md) using the isolated account's private
provider configuration. PPQ uses Python's standard library for its agent loop;
it does not require Codex CLI or OpenAI credentials.

Start with the [Ubuntu account and machine setup guide](setup-linux.md), including
apt dependencies, user creation, isolation checks and a synthetic slide test.
It assumes a separate agent machine and podcast host; it also explains local
execution when both roles share a machine.

## Podcast hosting prerequisites and current support

For hosting operations, provide an existing **Castopod instance or another
podcast hosting service**, an explicitly selected show, and permission for the
isolated agent to perform the requested operations. This includes creating a
podcast episode, attaching transcripts or updating hosting-side video metadata.
Installing or upgrading the hosting service is separate work. The offline
slide/video workflow can instead start from supplied episode audio and a full
transcript without access to the podcast host.

Our existing Castopod integration uses an SSH connection to the hosting service
account, a readable Castopod installation with its required PHP runtime, and
server-side helpers outside the web root. Publishing needs the relevant
application/media/database permissions; a working SSH login alone is not an
integration test. Configure the host, application path, application user,
staging/helper paths and show explicitly, keeping credentials outside source.
Give the isolated agent its own SSH identity using the
[host-access setup](setup-linux.md#5-remote-podcast-host-access-when-needed).
Validate the helpers' read-only list/inspect operations before an authorized
mutation. Keep existing maintenance controls and validate replacement access
before retiring the maintainer's access. For another provider, use its supported
API/transport and scoped credentials; an adapter still needs implementation and
testing. Do not assume Castopod's SSH/PHP helpers work with another provider.

The repository shares the [Castopod publishing skill and Python/PHP tooling](../skills/castopod-publishing/references/operations.md),
[maintenance skill and procedure](../skills/castopod-maintenance/SKILL.md), private
configuration examples and [patch catalog](patches/README.md). A fresh clone can
prepare the integration from these files. The hosting administrator still needs
to install a matching reviewed helper cohort outside the web root and provide
the current user-maintained maintenance decision before enabling writes. Sharing the toolkit
does not deploy helpers, upgrade Castopod or authorize episode mutations.

The original operator's live helpers and private workflow remain in place during
migration. New-client read-only inspection can use the legacy inspector; writes
require the new helper cohort and a configured user-maintained pause. Host-specific
records, article/narration policies and old patch exports are not public defaults.

## Portable layout

Keep code, artifacts and credentials separate:

```
HOME/src/sovereign-podcaster/       source only
ARTIFACT_ROOT/episodes/ID/r001/    full inputs, outputs, logs and provenance
HOME/.config/sovereign-podcaster/  private operator configuration
HOME/.local/share/sovereign-podcaster/  caches and runtime state
```

Use a dedicated unprivileged Linux user with a private home and artifact directory.
Protect the other accounts' homes and data roots using the
[account/storage isolation guide](account-isolation.md).
After the maintainer has signed and pushed the initial repository from the MacBook,
the isolated user can fetch source without a GitHub account or credential:

```sh
git -c credential.helper= clone https://github.com/Sjors/sovereign-podcaster.git "$HOME/src/sovereign-podcaster"
git -C "$HOME/src/sovereign-podcaster" remote set-url --push origin disabled://read-only
git -C "$HOME/src/sovereign-podcaster" config --local credential.helper ''
```

Run this in the isolated user's clean shell after creating its directories. It
does not need the maintainer's GitHub authentication or signing keys. The disabled
push URL prevents accidents; absence of write credentials supplies read-only
remote access. For filesystem-read-only source, have an administrator install a
reviewed root-owned snapshot and keep generated artifacts outside it.

Install a fresh runtime, selected reviewed skill copies and a fresh SSH identity.
Do not copy a complete home, chat history, harness authentication, SSH directory
or agent socket. No sudo/docker/lxd/disk groups for the executor. Use clean
environments when changing users. Separate users isolate private homes but do
not hide world-readable files; audit ACLs and shared storage before live work.

The slide tool needs only Python 3.11+. The later media pipeline needs Pillow,
Fontconfig/approved fonts and FFmpeg with libass, libx264, FFV1, zscale and the
selected AV1 encoder. Chrome/Node are optional for source capture. Freeze actual
versions and font hashes with the first reproducible render. Continue the existing
local Whisper pipeline when needed; do not add hosted transcription.

Example future operator configuration (not yet consumed by the slide CLI):

```json
{
  "artifact_root": "/srv/podcaster/artifacts",
  "ssh_config": "/home/podcaster/.ssh/config",
  "castopod": {"transport": "ssh", "ssh": "podcast-host", "show": "CHOOSE_EXPLICITLY"},
  "blossom_servers": ["https://media.example.org"],
  "nostr": {"expected_pubkey": "CONFIGURE", "identity_file": "/private/identity.json"},
  "youtube": {"expected_channel_id": "CONFIGURE", "credentials_file": "/private/youtube.json"},
  "maintenance_guard": "/home/podcaster/.config/sovereign-podcaster/publication-control.json"
}
```

Enable credentials incrementally: offline slides, local media, verified SSH,
authorized storage/signing, then dedicated YouTube authorization. Validate each
replacement before proposing removal/revocation of old access. Preserve existing
jobs during migration. A host-specific runbook must confirm OS, paths, disk,
ownership, available commands and SSH target before running administrative steps.
