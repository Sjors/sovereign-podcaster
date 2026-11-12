# Episode operations and installation

The Python client and five PHP helpers are shipped together. Python needs only
its standard library. The PHP scripts use the configured installation's models
and callbacks; they are not a replacement HTTP API or a Castopod distribution.
They originated with the owner's working Castopod 1.15.x integration. Recheck
installed model/parser interfaces after upgrades instead of upgrading a live
application merely to get API access.

## Native chapters and conditional description updates

The [autonomous chapter workflow](../../../docs/chapters.md) uses the native
`Episode::setChapters(File)` interface inspected in the local Castopod 1.15.6
source. Its RSS helper emits `<podcast:chapters>` with the JSON media URL and
`application/json+chapters`. No application/schema patch is needed. Live helper
installation and acceptance require the operator's instance-specific authorization.

The matching CLI cohort advertises `chapters` and `conditional-update` in
`inspect.features`, and returns original `description_markdown`, `chapters_id`
and `chapters_url`. Chapter updates accept `--chapters canonical.json` plus
`--notes derived.md`; `--expected-state inspected-episode.json` compares the
complete inspected episode snapshot under the server episode lock before any
media mutation. The client also checks it before staging. An intervening edit
stops the update. Keep all these files and the operation receipt private.

Helpers advertising `episode-number` also allow `update --number N` with an
exact `--expected-state` snapshot. It is a separate number-only operation; other
metadata/media changes are rejected. Native readback checks every other inspected
field, including the GUID, slug and enclosure. Verify the RSS number and unchanged
GUID/publication/enclosure afterward. This corrects a missing episode number
without creating a replacement episode or changing its UUID.

Native chapter attachment and description update happen in one helper invocation,
preserving audio, transcript, status and identity. The chapter workflow performs
public JSON/RSS/description/source verification before reporting completion.
Do not infer success or retry an uncertain mutation from a model's final answer.
The chapter task needs no human approval step; preserve maintenance pauses,
source checks and receipts. It does not authorize audio/video/Nostr/YouTube work.

## Dependencies and private configuration

Tested client environment: Ubuntu 26.04.1, Python 3.14; code requires Python 3.11+
for streamed SHA-256. PHP helper syntax was checked with PHP 8.3.6/POSIX.
The helper/model baseline was used with Castopod 1.15.5/1.15.6. Automated transport
checks use fixtures; they do not prove a new release or production mutation.

Agent dependencies:

```sh
sudo apt install --no-install-recommends python3 openssh-client ca-certificates coreutils
```

The hosting machine needs its Castopod-compatible PHP CLI and extensions,
including POSIX for the service-user lock check. For example, on Ubuntu with
PHP 8.3 the CLI components come from `php8.3-cli` and `php8.3-common`. Install
**only after checking the host's release requirements**:

```sh
sudo apt install --no-install-recommends php8.3-cli php8.3-common coreutils
```

Do not change a different server's PHP version to match this example. PHP,
Composer, database and frontend dependencies otherwise follow that installation's
own requirements. No PHP runtime is required on a separate agent using SSH;
for local transport run PHP in the already provisioned hosting environment.

Copy [the example](../../../examples/castopod-publishing.json) into a private
owner-owned 0700 configuration directory, with the file 0600. The default client
path is `~/.config/castopod-publishing/config.json`; `--config FILE` selects another
instance. Set SSH alias/config, application path, application audit user,
`incoming` staging root, `cli` helper directory, `php_bin`, `state_dir` and
`maintenance_pause`. No show is selected by default. A successful user lookup
establishes audit identity; it does not turn service-account SSH into a restricted
application role. The hosting service account can write application media/data.
Use a forced-command boundary or narrower account if that access is too broad.

Use a fresh isolated-user SSH identity and verified host key, with no forwarding
or shared agent; see [Linux setup](../../../docs/setup-linux.md). The client forces
strict host checking and disables agent/port forwarding and multiplexed sessions.
For intentional same-machine execution use `"transport":"local"` and omit `ssh`;
commands run as the current account without sudo or an automatic account switch.
The account must already have the intended app/media/database access. No application
credentials or `.env` contents are copied to the agent.

## Install a matching server helper cohort

This is an explicit server installation/deployment step, separate from copying
this repository. Inspect the installed runtime, old helpers and available disk/
permissions first. Preserve existing scripts and all unrelated deployed changes.
Use a new versioned helper directory outside the web root, owned by the hosting
service account; do not overwrite an older cohort while another workflow uses it.

For a new installation, the hosting administrator/service account creates the
configured incoming root and a new private helper directory. On that host,
adapt the paths below; both must be deliberately selected. Stop on any error.

```sh
# Only when these selected destinations are absent:
test ! -e /home/podcast/bin/castopod-publishing-v1
install -d -m 700 /home/podcast/bin/castopod-publishing-v1
# Provision an incoming root too if this instance does not already have one.
```

After installation is authorized, from the agent machine:

```sh
SP_CP="$SP_REPO/skills/castopod-publishing"
# Syntax checking over stdin does not install or execute the application helpers.
for SP_HELPER in "$SP_CP"/scripts/castopod/*.php; do
  ssh -o BatchMode=yes -o IdentityAgent=none -o ForwardAgent=no \
    -o StrictHostKeyChecking=yes podcast-host 'php -l' < "$SP_HELPER" || break
done

# Install the entire reviewed cohort into the newly prepared directory.
scp -o BatchMode=yes -o IdentityAgent=none -o ForwardAgent=no \
  -o StrictHostKeyChecking=yes "$SP_CP"/scripts/castopod/*.php \
  podcast-host:/home/podcast/bin/castopod-publishing-v1/
ssh -o BatchMode=yes -o IdentityAgent=none -o ForwardAgent=no \
  -o StrictHostKeyChecking=yes podcast-host \
  'chmod 600 /home/podcast/bin/castopod-publishing-v1/*.php'
```

Run the copy block only after every syntax check passes.
Use the actual `php_bin` if it differs from `php`. Compare all installed SHA-256
hashes with the reviewed files (`sha256sum` from coreutils), and lint the installed
copies. Set `cli` to this reviewed directory only after the cohort is complete.
The read-only inspector reports `helper_api:1`; new-client mutations require that
marker. Older helpers may still be inspected read-only. Do not mix old/new writers
concurrently: the older helpers do not acquire the new server-side episode lock.

The helper creates its private episode lock directory beneath the selected
application's `writable/` only during an authorized mutation. It must be owned by
the service user and mode 0700. Locks are nonblocking and shared by the new PHP
cohort across cooperating clients/machines. Local clients also hold an episode
lock beneath `state_dir` through preflight, mutation and readback.

## Maintenance state in the single-user runtime

`maintenance_pause` names a private JSON file with an explicit boolean
`"paused":false` for authorized writes. Missing, unreadable, malformed or paused
state stops mutations. Read it before staging and immediately before mutation.
The `podcaster` user is both operator and executor, so this state is user-owned
and needs no sudo approval per episode. It is an operational pause, not a security
boundary within one UID. Honor the user's pause/resume instructions; do not alter
it to bypass a hold. Keep ordinary episode identity checks, locks, receipts and
inspect-before-retry protections. See [backstops](../../../docs/backstops.md) for
required operator-provided recovery and budget arrangements.

## CLI and receipts

All following commands use explicit instance configuration. `list` and `inspect`
make read requests; creation/update/publication plans are offline without `--apply`:

```sh
python3 "$SP_CP/scripts/publish.py" --config PRIVATE_CONFIG list
python3 "$SP_CP/scripts/publish.py" --config PRIVATE_CONFIG inspect \
  --podcast SHOW --slug EPISODE
python3 "$SP_CP/scripts/publish.py" --config PRIVATE_CONFIG create \
  --podcast SHOW --slug EPISODE --title 'Episode title' \
  --audio /private/final.mp3 --notes /private/show-notes.md
python3 "$SP_CP/scripts/publish.py" --config PRIVATE_CONFIG update \
  --podcast SHOW --slug EPISODE --transcript /private/final.vtt
python3 "$SP_CP/scripts/publish.py" --config PRIVATE_CONFIG publish \
  --podcast SHOW --slug EPISODE
```

For a mutation already authorized by the user add `--apply --receipt NEW_PRIVATE_JSON`.
The receipt parent must be private (0700), owned by the current user and outside
Git. It binds operation/target and source paths, sizes and SHA-256 hashes, records
staging and phase before writes, and preserves verified result/error type. Source
changes while staging stop before the database mutation. Repeating the identical
verified receipt returns cached evidence without network access; it is not a fresh
live-state check. A changed request or unresolved receipt refuses execution.
Never create a fresh receipt merely to bypass an unknown outcome: inspect the
exact target and retained staging, record the recovery decision, then prepare a
new operation only when its effects and authorization are established.

Creates default to draft; `--season` and `--number` are supported only there.
`create --publish` is an explicit transport capability, not a replacement for the
source workflow's review/transcript requirements. For this project's new episodes,
create the draft, attach/check the reviewed transcript, then publish when authorized.
Updates can change only supplied title, notes, audio or transcript and preserve
status. Audio replacement must keep the existing MP3/M4A container and URL.
Publish refuses an episode that is not a draft. Scheduling, slug/episode-number
updates, deletion and podcast-wide settings are not implemented.

After a successful operation the helper removes only its own exact staged files
and directory. A readback/mutation failure preserves staging; cleanup failure after
verified publication is reported separately and must not trigger republication.
Keep receipts with the episode's artifacts, rather than source control.

## Transcript/version behavior and public checks

Attach a transcript to the exact show/episode whose final audio its cues describe.
A conversation and a narrated article have different timelines and speaker policy.
Use supplied participant labels for a conversation; article paragraph/narrator
presentation belongs to the source workflow. Do not inherit another show's names,
licensing or independent-review verdict.

The PHP update uses `Episode::setTranscript()`, clears a stale remote transcript
URL and marks WebSub publication pending, following the native editor behavior.
A replacement must keep its existing SRT/VTT format. Readback verifies attachment
presence while preserving GUID, publication time, audio key/URL/size and unrelated
title/notes. It does not independently validate every parsed cue or download bytes.

The original 1.15.5 parser needed a derivative with one `WEBVTT` header, a blank
line, unnumbered timing blocks and one-line payloads; cue IDs, NOTE blocks and extra
header lines were not handled correctly. For that parser, `<v Speaker>Text` without
a trailing `</v>` avoided literal closing tags in output. Preserve the original
export, reviewed wording and timing map; recheck the actual installed parser after
upgrades rather than assuming this workaround is always necessary. Run its parser
on the candidate and compare cue count, text, speaker and timing before attachment.

After an authorized publication/attachment check public VTT hash, JSON companion,
transcript page presentation and the exact RSS `<podcast:transcript>` item; preserve
GUID, pubDate and enclosure. Check actual HTTP Content-Type as well as feed MIME.
A missing server VTT mapping is a web-server change for the administrator to prepare,
syntax-check and apply deliberately, not an incidental helper operation.
Check page/feed/enclosure availability and actual media playback separately from
metadata readback. No preview getter is invoked by discovery, because creating a
preview link can itself mutate state in the inspected version.

Run offline checks with `python3 -m unittest discover -s "$SP_CP/tests" -v`.
In a checkout with PHP CLI available, also run `php "$SP_CP/tests/test_helpers.php"`;
it exercises only temporary lock fixtures, cleans them up and never boots Castopod.
Syntax lint and fixture tests do not validate arbitrary future Castopod versions.
Use an authorized disposable instance for actual mutation regression tests; do not
create synthetic episodes in a live feed merely to test this integration.

## Migration validation recorded for this toolkit

On 2026-11-01, read-only `list` using this client passed from the isolated account
through its fresh SSH identity against the existing Castopod 1.15.6 installation.
The existing live helper cohort was retained. All five new PHP files passed syntax
lint on PHP 8.3.6/POSIX, the isolated PHP lock fixture passed, and 22 Python
transport/guard/receipt tests passed. No new helper cohort was installed and no
episode/database mutation was performed for this port.

Keep the old private client/skills and their source-specific rules working while
server work continues. After an authorized new-cohort installation and disposable
mutation checks, migrate callers/configuration and any skill-discovery links,
preserving private narration/review rules as operator notes. Update all cooperating
writers deliberately before relying on shared locks. Do not redirect a legacy
client to the new protocol or revoke old access as an incidental source update.
