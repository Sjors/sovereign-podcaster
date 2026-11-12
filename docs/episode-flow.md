# Episode work over Marmot

The model backend may be [standalone PPQ or Codex](llm-providers.md). Explicit
video tasks can resume after jobs/approvals without idle model polling; the
[video assignment runbook](production.md#explicit-video-assignments-and-back-catalogue-publication)
documents reviewed no-announcement packets and full-release approvals. Those
explicit choices override the general announcement/separate-public-review
sequence below.

The normal sequence is: request an episode → prepare slides/video → upload a
tracked fallback draft → discuss/revise → approve exact Nostr artifacts → publish
and announce on Nostr → upload privately to YouTube → inspect video, thumbnail,
captions and metadata → approve public YouTube publication → clean up temporary
drafts. Keep original media and local revisions after remote draft cleanup.

## Two entry paths

| Starting point | Before the shared video workflow |
| --- | --- |
| An existing hosted podcast episode | Select the exact show/episode, preserve its hosted identity and original publication, and obtain its canonical audio and reviewed transcript. Publish video as an addition to that same episode. |
| A new raw recording | Edit the recording (prefer separate speaker tracks), complete/review the transcript, then publish the podcast episode. Use its final audio/transcript and hosted identity for the shared video workflow. |

The current `podcast new SHOW EPISODE` command creates a **local video project**;
it does not create or publish an episode on the podcast host. The [production runbook](production.md) supplies the renderer, AV1/HLS packaging,
publication tools, background completion notices and authenticated reviews.
[Local transcription and native transcript attachment](transcription.md) are
available for explicitly selected existing episodes. Automated intake/hosting-side
video linking and raw-recording editing remain in [TODO](../TODO.md); the full
real video workflow validation is still pending.

For chapter tasks, follow the [chapter policy](chapters.md):
Podcasting 2.0 JSON is canonical, description timestamps are derived, and the
editorial target is 3–10 chapters per full-length episode.

For requested episode audio edits, use
[podcast-editing](../skills/podcast-editing/SKILL.md). Its ordinary processing
guidance assumes the usual quieter recording; live-audience noise, room fades
and PA echo have a separate reference. Preserve a sample-based edit map so the
final transcript, chapters and video share the delivered audio clock. The skill
documents editorial work; it does not add a new automatic intake/publication task.

## Start and resume without idle model work

Select `/src/podcast` in the verified private group. These literal messages are
handled locally, without reading API keys or making model calls:

| Message | Result |
| --- | --- |
| `help` or `podcast help` | Show podcast commands and current capabilities. |
| `transcribe SHOW EPISODE` | Select/resume a cleared existing episode, transcribe locally, review, request feedback if needed, and publish/verify its native transcript. |
| `chapters SHOW EPISODE` | Review one existing episode, publish native chapters and derived description timestamps, then return the verified episode link. No manual approval. Requires the chapter workflow to be deployed and configured. |
| `episodes` or `podcast episodes` | List locally tracked episode projects, revisions and publication status. |
| `podcast new SHOW EPISODE` | Create an episode journal and select fresh model context. |
| `podcast use SHOW EPISODE` | Select/resume that episode's saved context. |
| `podcast status` | Show the selected episode's local progress. |
| `podcast history SHOW EPISODE` | Locate earlier saved conversation references without loading them into the current model context. |

`/help` is the upstream White Noise bridge's own help menu; the podcast menu is
the plain `help` message after workspace selection. Local help/status/list commands
also work when model spending is disabled. The episode list covers projects in
the local journal, not a discovery/import of the published YouTube/Nostr back
catalogue. An empty journal returns a readable explanation and the start command.

Use short IDs made from letters, digits, hyphens or underscores. These are plain
messages, not new upstream slash commands. A new episode requires an explicit
show/episode ID; the adapter does not guess an episode from old files. After
selecting one, provide its canonical audio, full transcript and production
instructions in ordinary messages. Use existing Whisper tooling if needed.
The first ordinary message creates the managed API session; follow-ups resume
it. Selecting another episode retains the old session and private local history.
Earlier work can be read selectively as source data, without automatically
inserting whole chats, unrelated authentication or old publication approvals.

The connector/harness remains available for incoming Marmot messages. The API
backend runs only for a received model task and stops its local executor on
completion. There are no idle model prompts, heartbeat agents, API chat polling
jobs or scheduled wakeups. Active-turn status requests are bounded controller
HTTP calls, not additional model prompts. A question is returned as a final
reply and work waits for the user's next message; do not keep a model turn open
while waiting days/weeks for feedback. The upstream [session guide](https://developers.openai.com/api/docs/guides/agents-api/sessions)
describes starting a turn by messaging an idle session. Model usage, tool fees
and hosting costs remain separate; this setup uses its own Linux executor.

Use `podcast new/use` for episode selection. If the upstream harness session was
reset independently, the adapter requires explicit episode selection before
continuing instead of silently recreating work. Unknown prior outcomes block
episode switching until inspected. Install the [pinned message-context bridge patch](../adapters/marmot/message-context.md).
Incoming IDs/senders are checked against the connector timeline: separate replies
saying the same words are distinct turns; replaying one ID cannot repeat its tools.
Publication reviews use `approve REVIEW_ID` or a quoted yes to the exact offer;
ordinary unquoted yes remains new production feedback.

## Deterministic tools

Tested on Ubuntu 26.04.1 LTS with FFmpeg 8.0.1. Dependencies:

```sh
sudo apt install --no-install-recommends python3 ffmpeg ca-certificates
```

The journal/media tools use the Python 3.11+ standard library. Blossom mutations
reuse the separately installed [Nostr runtime](nostr-setup.md); no hosted
transcription service is added. Use a private work root outside Git. Configure
it using Marmot setup's `--work-root`; the generic default is
`~/.local/share/sovereign-podcaster/work`. State is owned by the executor with
mode 0700/0600.

`tools/episodes.py --root ROOT` has `init`, `list`, `status`, `revision`, `approve`,
`record`, `draft-upload` and `draft-cleanup` subcommands; each has `--help`.
The private `episodes.json` journal, evidence snapshots and transport receipts
survive restarts. All cooperating episode operations share a filesystem lock.

A `revision --manifest FILE` takes a JSON object mapping artifact roles to local
file paths. Required roles are `video`, `fallback`, `thumbnail`, `metadata`;
optional roles are `captions`, `slides`, `transcript`, `audio`, `nostr_metadata`
and `nostr_bundle`. The journal records paths, sizes and SHA-256 hashes. Preserve
the files at immutable revision paths; changes require a new revision. Its
`manifest_sha256` binds the review packet for YouTube. Its separate
`nostr_manifest_sha256` binds video/fallback and optional Nostr metadata/bundle,
so a YouTube-only description/thumbnail change does not require reannouncing
unchanged Nostr material.

`approve --scope nostr|youtube-public --evidence FILE` snapshots the exact human
instruction, ideally with authenticated Marmot message ID, sender, group and UTC
time. Public YouTube approval is recorded only after a private upload receipt
and binds that same video ID. These local records are audit evidence: the tool
cannot authenticate a human simply because a file says “approved.” The production
publisher now requires the controller-authenticated review records from `reviews.py`
and rejects this manual evidence alone; see the production runbook. The trusted
controller/operator must establish the actual authorization. An agent cannot
grant itself approval. Initial setup and these instructions do not authorize a
production upload, announcement or publication.

`record --stage nostr|youtube-private|youtube-public --receipt FILE` records
**already verified** external results. It does not publish or independently
verify a provider. Receipts require `verified:true` and `manifest_sha256` matching
the appropriate stage digest. Nostr receipts contain `video_event_id`,
`announcement_event_id` and **all** final `blobs` as `{server,sha256}` entries
using canonical bare HTTPS origins. Preserve raw signed events, relay readback
and storage checks as separate evidence. YouTube receipts contain `video_id`,
`channel_id` and `privacy_status` (`private` or `public`), plus actual processing,
thumbnail/caption/metadata readback evidence. Use the existing channel helper,
shared mutation lock and [YouTube operations](../skills/youtube-publishing/references/operations.md).
Always set private visibility explicitly; publish the existing ID after exact
review instead of creating a replacement. Do not retry ambiguous creates.
These registry commands are not a new automatic Nostr/YouTube publisher.

## Full draft review and cleanup

The established fallback is **854×480 AV1, 15 fps, AAC-LC mono at 48 kHz / 64 kbps**,
SVT-AV1 preset 5 / CRF 32, six-second GOPs. It remains a separate MP4 from the HLS
ladder and YouTube master. Preserve an already verified fallback byte-for-byte;
when needed, this deterministic encoding command creates a new immutable output:

```sh
python3 "$SP_REPO/tools/review_media.py" fallback --input MASTER --out NEW_REVISION_DIRECTORY --background
```

The background option detaches one logged encode process so it survives the
180-second model-turn limit; it drops inherited API credentials. It refuses a
duplicate launch path. Keep the output beneath the episode directory so local
`podcast status` can report its saved render state. After a host reboot, inspect
a running/starting record and partial logs before restarting in a new output
directory; it does not guess whether an interrupted encode finished. The worker
records source/output hashes and commands, checks duration and performs a full
decode. This does not replace editorial, caption alignment, frame/keyframe or
real-device QA. The AV1 policy follows the existing inspected render workflow;
H.264 is not substituted for full drafts. Long render commands run without model
calls; keep the logged process/output for resumption rather than paying a model
to repeatedly ask whether it finished. No render-job scheduler is introduced.

Adapt [draft-config.json](../examples/draft-config.json) into private operator
configuration. Set the runtime, identity, expected public key, draft destinations
and playback origins explicitly. Draft Blossom uploads are publicly retrievable
content-addressed bytes, not access-controlled private videos. Do not upload
confidential footage as a “private” draft. Before applying authorized writes, the operator records the current maintenance
decision in private user-owned state (no sudo approval of task details):

```json
{"schema":1,"allowed":true,"actions":["draft-upload","draft-delete"]}
```

Missing/closed/malformed guards fail closed. This is an operational pause within the shared operator/executor UID, not an
OS boundary. See [backstops](backstops.md) for required recovery arrangements. Preserve existing host maintenance pause
checks when connecting this guard; do not create an always-open substitute to
bypass them. No production guard was installed during this setup.

```sh
python3 "$SP_REPO/tools/episodes.py" --root "$SP_WORK" draft-upload \
  --show SHOW --episode EPISODE --revision REVISION --config PRIVATE_CONFIG
# After episode-specific upload authorization, add:
# --authorization SAVED_HUMAN_REQUEST --apply

python3 "$SP_REPO/tools/episodes.py" --root "$SP_WORK" draft-cleanup \
  --show SHOW --episode EPISODE --config PRIVATE_CONFIG
# Inspect the plan, then use --apply when authorized.
```

Upload intent is saved before network access. Each revision/destination gets an
immutable hash binding and the existing Blossom receipt/resume behavior. Cleanup
waits for verified Nostr video/announcement **and public YouTube** completion of
the current revision. It retains final-release hashes, other active episodes'
draft hashes, pre-existing/reused blobs and uncertain uploads. Reusing a draft
as a final fallback means retaining that blob and treating its role as final.
Only newly acknowledged, unreferenced uploads are deletion candidates; the
low-level helper rechecks receipt/server/identity and verifies absence. Partial
failures retain receipts for inspection. Placeholder responses and foreign caches
are not proof of erasure. Register all episodes using the same shared work root;
references outside this registry cannot be discovered automatically. Never remove
a published Nostr event or canonical YouTube video as draft cleanup.

## Focused review through encrypted chat

Use short H.264/AAC MP4 fragments for phone compatibility; this is separate from
the full AV1 draft policy. `review_media.py fragment` accurately trims/re-encodes
up to 120 seconds, fully decodes it and produces a private immutable send manifest:

```sh
python3 "$SP_REPO/tools/review_media.py" fragment \
  --input REVIEWED_VIDEO --home "$MARMOT_HOME" --id UNIQUE_CLIP_ID \
  --start START_SECONDS --duration DURATION_SECONDS \
  --caption "Specific question about this interval"
# Account/group default to the trusted current-turn Marmot route.
python3 "$SP_REPO/skills/marmot-whitenoise/scripts/wn_control.py" \
  --home "$MARMOT_HOME" --send-media PRINTED_MANIFEST_PATH
```

For an operator outside the current turn, explicitly pass the verified `--account`
and `--group` instead of inferring a route from a title. Enable only the private
media staging root with Marmot setup's `--enable-chat-media`. A standalone send
uses its existing durable ledger; uncertain sends are inspected, not blindly
repeated. Normal text replies still return through the harness once.
The video arrives as an encrypted chat attachment. Its transport uses encrypted
Blossom storage internally, as explicitly accepted by the operator; it does not
create a separate public draft URL or Nostr announcement. Keep the source clip,
exact question and send receipt with the episode's review evidence.

On 2026-11-01 a synthetic five-second video/tone (583,913 bytes) was sent through
the isolated identity to its verified private group. The connector acknowledged
the send, and the phone owner confirmed playback **with sound**. This test used
zero model calls and no episode source material. It validates the selected
release/device path, not all future codecs or arbitrary-sized attachments.

For the complete deterministic command sequence, job notifications and recovery,
see [production](production.md). Rendering/publication tools are ported; real-episode
phone playback and full live publication/deletion validation remain pending.

For per-task model cost estimates across review turns and handoffs, use the
[task cost reporting workflow](task-costs.md). Begin one scope before substantial
transcript/video work and finish it after the requested outcome; retain it while
waiting for jobs or feedback.
