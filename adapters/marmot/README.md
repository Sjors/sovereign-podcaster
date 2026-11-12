# Private conversation with the podcast agent

## Provider choice

The bridge can run either the existing Codex/Agents API backend or a standalone
PPQ agent. Configure private `llm.json` and use `--llm-config` during setup;
PPQ-only setup needs neither an OpenAI project nor Codex tooling. See the
[provider guide](../../docs/llm-providers.md). Other sections describing OpenAI
keys, executor registration or active-turn steering apply to the Codex path.

Marmot/White Noise carries the encrypted conversation. A fresh connector identity
belongs to the isolated Linux user; it is separate from the public podcast identity.
The same user runs the controller and executor. Keep unrelated bridges, accounts
and private state separate.

Follow the current upstream [agent instructions](https://github.com/marmot-protocol/mdk/blob/master/integrations/AGENTS.md#suggested-agent-chat-instructions),
[quickstart](https://github.com/marmot-protocol/mdk/blob/master/integrations/README.md#get-started-white-noise--agents),
and [connector documentation](https://github.com/marmot-protocol/mdk/blob/master/crates/agent-connector/README.md).
They own the changing setup/protocol/chat guidance. This repository does not vendor
that manual. Check installed help and the matching release when master differs.

## Tested local selection

The adapter pins the tested `wn-agent-v0.14.0` cohort. GitHub marks it as a
pre-release; it is not a claim of stable API.
The [release lock](release.json) pins the reviewed installer and records archive
digests. Setup verifies the installer against that pin and its adjacent checksum,
then delegates to upstream's installer, which verifies its binary downloads.
Review a new release and rerun acceptance checks before changing the pin; do not
automatically follow a nightly. Upstream's MIT notice is retained in
[third_party/marmot](../../third_party/marmot/LICENSE).

For this project's Agents API experiment, `wn-codex` is the conversation/process
harness. Its `WN_CODEX_BIN` points to [marmot-backend.py](../openai-agents/marmot-backend.py),
which speaks its JSONL contract and uses the **Agents API**, not ordinary
API-key-authenticated `codex exec`. Each conversation resumes its managed API
session. Selected repository skills are available through local files. The
executor is the independently installed `codex exec-server` and receives only
the restricted environment key. The application key is read by the controller
from its private file, never exported into the executor environment.

With one Linux UID, executable code can still read that UID's application-key
file. Separate processes/keys do not provide a filesystem boundary. Marmot is
encrypted in transit; the API receives plaintext prompts/tool results for model
processing. Do not confuse encrypted transport with local-only inference.

## Setup and contact output

Complete [Linux isolation](../../docs/setup-linux.md) and
[OpenAI authorization](../openai-agents/authorization.md) first. On the tested
Ubuntu 26.04.1 platform, install the required apt packages:

```sh
sudo apt install --no-install-recommends \
  bash ca-certificates coreutils curl tar python3 systemd dbus-user-session
# Optional developer inspection and skill validation:
sudo apt install --no-install-recommends ripgrep python3-yaml
```

Run as the isolated user. Use its real HOME, a private state directory outside
Git, and no forwarded/shared SSH agent. For services that survive logout, check
`loginctl show-user "$USER" --property=Linger`. Try enabling linger with
`loginctl enable-linger "$USER"`. If policy denies that, the administrator can
enable linger for only this user. Never grant it general sudo. The systemd user bus is `/run/user/UID/bus`.

```sh
umask 077
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/adapters/marmot/setup.py" \
  --trusted-npub YOUR_WHITE_NOISE_PHONE_NPUB \
  --project-id YOUR_OPENAI_PROJECT_ID --allow-timeout-only
```

`--trusted-npub` is required. Use the **phone owner's** public identity. Upstream
validates it and applies it to invitation and message-sender allowlists. The
installer creates a fresh agent identity; it never imports the podcast key or
copies another user's Marmot/ChatGPT state. Keep the phone and connector's relay
settings consistent, following upstream's instructions.

The tested Agents API rejects the documented per-session dollar limit. The flag
explicitly opts into timeout-only model turns, currently 180 seconds each. A
timeout is not a dollar cap. Each trusted incoming prompt may incur model usage;
there is no automatic prompt loop. Credit balance/billed cost must be checked in
the Platform dashboard. This setup does not authorize production publication.

The script prints `agent_npub`, a relay-hinted `agent_nprofile`, and the trusted
contact. Add that new agent as a contact in White Noise, then create a private
group containing you and it. Follow the printed workspace selection and send a
fresh text-only challenge. Setup creates `~/src/podcast` as a symlink to this
checkout, so the phone command is **`/src/podcast`**, regardless of the longer
repository name. It refuses to replace an existing path pointing elsewhere.
The original checkout and synchronization remote retain their paths.
Confirm the answer in that same group. Bootstrap and
service success alone leave **DEVICE VERIFICATION REQUIRED**.

To print the existing contact again without generating/replacing an identity:

```sh
python3 "$SP_REPO/adapters/marmot/setup.py" --contact
```

Configure another state home with `--home`; installer service names belong to this
adapter. Repeating matching setup reuses contact details. It rejects a different
trusted contact/project or an unmanaged nonempty home. Partial setup has a private
intent record; inspect its log and rerun with identical arguments. Other accounts
and services are not migration inputs.

## Operation and recovery

The wrapper's `WN_CODEX_TIMEOUT_SECS` must exceed the backend's longest model
turn plus cleanup. This adapter uses 900 seconds around turns bounded at up to
600 seconds; it continues emitting progress events while a turn runs. A shorter
wrapper could kill the controller before it records a completed publication and
reports its result. The backend rejects that configuration before starting a
model request. Keep spending controls separate from these time limits.

For an existing installation, inspect active work first, back up its service
configuration, and install a same-user drop-in with
`Environment="WN_CODEX_TIMEOUT_SECS=900"`. Reload systemd and restart only the
idle agent service. Existing setup files are not silently rewritten by a private
source push. After an old wrapper timeout, inspect native publication receipts
and the provider's terminal state before reconciling the checkpoint; never
replay a publication to recover its reply.

The two user services are `sovereign-podcaster-marmot.service` and
`sovereign-podcaster-agent.service`. The latter uses the API backend and an
instance-specific harness state path. Ordinary answers/questions return to the
originating group; subsequent user messages resume the same API session. The
upstream guide describes workspace selection/reset and transport recovery.
Do not create a second daemon against this state home.

The harness uses a bounded per-group capacity of four prompts, including the
active prompt. Follow-up corrections can wait while a turn runs; execution
remains serial. A capacity of one rejects ordinary back-and-forth replies during
an active turn. For an existing installation, apply the matching service
environment override and restart only after its active request has settled.

With `followup_steering:true`, ordinary trusted text received during an active API
turn is forwarded to that same session as steering input. The active controller
checks only while running; there is no idle model polling. A private receipt binds
the authenticated message, route, submission ID and owning turn. Its later queued
bridge delivery stays silent and cannot start another model turn. Commands,
attachments and exact publication approvals retain their existing handlers.
The executor stays connected through a completion race until every accepted
follow-up appears in a terminal provider turn. Unknown submissions fail closed.
This follows the official [session continuation and steering contract](https://developers.openai.com/api/docs/guides/agents-api/sessions).

This initial backend is text-first. It rejects native-image/bypass flags rather
than silently ignoring them. Audio/PDF files are not automatically transcribed;
keep the existing Whisper workflow. Automatic artifacts, title editing and
progress reactions are not enabled by installation. Add narrowly scoped features
after checking the current upstream contract.

Private state lives under the selected Marmot home: `bootstrap.json`,
`podcaster-instance.json`, `harness/` and `api-state/`. Each API turn preserves its
request, session/turn IDs, response items, executor outcome and reported usage.
No private message content or credentials belong in Git or service logs. The
0.14 harness retains the first backend session ID, so the adapter uses a fixed
handle bound to that conversation and canonical workspace. Completed results
are saved before output. Earlier experimental rotating cursors are upgraded in
place; their completed work is retained.

This upstream backend contract does **not** provide the inbound message ID. As
a conservative interim rule, an exactly repeated prompt in the same session
returns its cached answer and does not execute another model/tool turn, even
when other prompts intervened. Use fresh wording for a new intentional action
or confirmation; repeated `yes` messages need context such as `yes, use the second
slide design`. Do not use `/retry-last` as a way to repeat a completed action.
A future release/patch exposing the authenticated inbound ID can remove this
limitation. Unknown outcomes block that conversation/workspace for inspection
instead of repeating potentially published effects. Preserve the active record,
inspect saved API history and actual tool effects, then make an explicit recovery
decision. A reset is not evidence that prior work vanished.

For explicitly authorized standalone text/files, the shared
[Marmot skill](../../skills/marmot-whitenoise/SKILL.md) provides `wn_control.py`.
Pass `--home` (or MARMOT_HOME), an owned 0600 manifest with exact account/group,
and a stable idempotency key. `--send-text` accepts account_id_hex, group_id_hex,
text and idempotency_key. Existing `--send-media` additionally validates exact
attachment paths/hashes/MIME beneath private staging. Its durable ledger refuses
changed or uncertain sends. Normal harness replies already send once; do not
also send them manually. Phone visibility requires confirmation.

Setup links the six selected podcast skills into the isolated executor's
`~/.local/share/sovereign-podcaster/codex/skills/`. Existing paths pointing elsewhere
are preserved and require inspection. The shared skill is canonical here and
discovered through per-account symlinks;
keep legacy host-specific notes privately at MARMOT_HOME/operator-notes.md. Never
turn an old group's media grants or liaison authorization into defaults for a
fresh podcast identity.

Offline validation (no model calls or messages):

```sh
python3 -m unittest discover -s adapters/openai-agents -p 'test_*.py' -v
python3 -m unittest discover -s skills/marmot-whitenoise/tests -v
```

For a pre-existing account using `~/skills`, inspect an existing Marmot skill and
preserve its private references and original source outside the public checkout
before replacing it with a link. Keep routing/grants/liaison policy privately in
`MARMOT_HOME/operator-notes.md`; the shared skill consults that file. When the
name is free:

```sh
mkdir -p "$HOME/skills"
ln -s "$SP_REPO/skills/marmot-whitenoise" "$HOME/skills/marmot-whitenoise"
```

The tested dev migration keeps its previous root alias working through that link
and retains a private backup. It changes no legacy service, login or group.

## Encrypted review attachments

To permit user-authorized review clips, repeat matching setup with
`--enable-chat-media`. This adds only `MARMOT_HOME/media-uploads` to the
connector's outbound read roots and restarts only this instance's connector.
The directory must be owned by the isolated user, real (not a symlink), and 0700.
The setup never grants the connector access to a whole home or project tree.
Automatic completion-file exports remain disabled; standalone `wn_control.py
--send-media` uses a private manifest and the existing pending-send ledger.

Send fragments as video attachments in the originating private group, without
creating a separate public draft link. Marmot's attachment implementation itself
uses encrypted Blossom blobs; this is not a promise of avoiding Blossom at the
transport layer. Follow the [current upstream media specification](https://github.com/marmot-protocol/marmot/blob/master/features/encrypted-media.md)
and the installed release's matching behavior, rather than copying protocol
instructions here. Connector acknowledgement and playback on the phone are
separate checks. Do not send a second attachment after an uncertain outcome.

For normal work, use the [episode flow](../../docs/episode-flow.md). Literal
`help`, `episodes` and `podcast new/use/status/episodes/history` messages select fresh/resumed contexts
and inspect local progress without model calls. `--work-root` configures the
private journal/artifact root. Ordinary episode prompts alone invoke the API.
The synthetic five-second encrypted video test passed phone playback with sound
on 2026-11-01, using zero model calls.

## Required incoming-message context support

Before sending production messages, build/install the [pinned bridge patch](message-context.md).
The current API backend verifies incoming message/sender IDs through the connector
timeline and rejects an unpatched bridge. Other existing agent installations are
unchanged. The [production runbook](../../docs/production.md) documents background
completion notices and exact review approvals.
