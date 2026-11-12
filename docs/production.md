# Produce, review and publish an episode video

## Explicit video assignments and back catalogue publication

Both [PPQ and Codex](llm-providers.md) can execute a selected episode task.
**Announcement policy is independent of the provider**: either backend can
publish with or without an announcement, according to the episode request. An
operator may enroll an explicit existing-episode request with
`adapters/openai-agents/video_tasks.py enroll --instance PRIVATE_INSTANCE
--show SHOW --episode NUMBER --authorization PRIVATE_REQUEST`. The private request
must truthfully record `source: "explicit-maintainer-user-request"`, the actual
`human_request`, `publication_config`, optional `source_references`, and exact
`scope: {"operation":"video","show":"SHOW","episode":"NUMBER","announce":false}`.
Set `announce` to `true` for the normal announcement flow or `false` when the
user explicitly declines one. This does not impersonate an incoming White Noise
message or clear source holds.

Set `video_tasks_enabled: true` in the instance and run the existing `wakeups.py`
service. It invokes the chosen model only for the initial assignment, newly
completed episode jobs or consumed exact-packet approvals. It stays idle between
events. The selected task and original authorization remain in private episode
state. Place all long jobs under `EPISODE_DIRECTORY/jobs`; successful internal
completions stay out of chat. Questions/previews use the verified White Noise
route and encrypted attachments. `WAITING_FOR_JOB` / `WAITING_FOR_REVIEW` are
internal final-answer markers when the relevant tool has already handled delivery.
Human text replies resume the same episode context. Paused/blocked tasks stay
idle, and failed/uncertain jobs require inspection rather than automatic retries.

For an old episode where the user explicitly declines an announcement, include
`"announce": false`, `"announcement": ""`, and `"announcement_mentions": []`
in its registered Nostr metadata. This choice is hashed into the packet and
displayed in the approval offer. The normal `publish.py nostr` phase publishes
only the native video, which Nostube can discover, and records a complete native
receipt with `announcement_skipped:true` and the stable `identifier` (naddr).
It never signs or publishes a kind-1 announcement. An announcement-phase call
for that packet fails. Default packets retain the existing announcement behavior.

When the user's requested approval covers full release, offer
`reviews.py --scope nostr --include-youtube-public ... --send`. This explicitly
includes the native video, the following private YouTube upload and public
release of that same verified ID. The video task offer also includes adding the
native video to the existing Castopod episode. After actual authenticated approval,
the public publisher binds that grant to the private upload receipt, rechecks
the exact captions/thumbnail/metadata/channel and changes that same ID's visibility.
There is no redundant approval for an ID created after full release was already
approved. A changed revision/destination still requires a new offer. The existing
`--include-youtube-private` and separate exact-ID public review remain available.

Use the installed Castopod `episodes:video` interface only after native storage
and event readback. Preserve audio, native transcript, GUID, publication date,
unrelated notes and existing identity; verify the public video tab/iframe.
Save `castopod-link.json` beside `video-task.json`, binding `verified:true`,
`manifest_sha256`, `video_event_id`, `identifier`, `episode_url` and before/after
identity evidence. Its identifiers must match the native receipt. After native,
Castopod and public YouTube verification, `video_tasks.py finish --instance ...
--show ... --episode ...` checks the matching receipts before marking completion.
Keep deployment evidence, source-specific controls and rollback copies private.

The sections below describe the general workflow, including the default
announcement and separate YouTube public-review path. Explicit reviewed packet
choices above control the corresponding back catalogue/full-release exceptions.

This toolkit starts with **explicitly selected final audio and a full reviewed
transcript**. Adding video to an existing hosted episode and editing a new raw
recording remain distinct intake paths. [Local Whisper transcription and native
transcript attachment](transcription.md) have a separate runbook. Raw editing and
hosting-side video linking remain tracked in TODO. Nothing here selects
an old episode, creates a hosted episode or adds a transcription service.

The working episode renderer/layout and AV1 packaging have been adapted into
`tools/produce.py` and `tools/video/`. Publication uses `tools/publish.py`, the
existing Blossom/Nostr signer, and the verified-channel YouTube SDK context.
`tools/jobs.py` runs bounded stages and reports completion through Marmot;
`tools/reviews.py` offers exact packets for authenticated approval. Harness-specific
incoming identity verification lives in `adapters/marmot/messages.py`.

## Dependencies and tested environment

Tested locally on Ubuntu **26.04.1 LTS x86-64**, Python 3.14, FFmpeg **8.0.1**,
Pillow **12.1.1**, Ubuntu Sans from fonts-ubuntu **0.869**, and fontconfig 2.17.1.
An administrator installs system dependencies; the executor receives no sudo:

```sh
sudo apt install --no-install-recommends \
  python3 python3-pil python3-venv ffmpeg fontconfig fonts-ubuntu \
  ca-certificates coreutils git openssh-client util-linux
# Optional development/search tools used in this repository:
sudo apt install --no-install-recommends ripgrep
```

Pillow supplies image/font metrics; FFmpeg must include libx264, libsvtav1,
libass/subtitles, zscale, showwaves, FFV1, AAC and HLS/fMP4. Check `ffmpeg -version`,
`ffmpeg -encoders`, `ffmpeg -filters` and `fc-match 'Ubuntu Sans'` on another system.
Python standard library supplies state, hashes, locks and subprocess management.
Nostr and YouTube continue using their **separate pinned runtimes** from their
setup guides. No API key is needed for production/render tests. Private portraits,
source captures and branding need the operator's own rights and provenance;
no episode-100 media or portraits were copied into this repository. Font files
remain system dependencies under their own notices.

## Run the synthetic local pipeline first

Run as the isolated account, with a private artifact parent outside Git. Change
`SP_WORK` to the chosen data disk. Do not reuse an existing fixture directory.

```sh
umask 077
SP_REPO="$HOME/src/sovereign-podcaster"
SP_WORK="$HOME/.local/share/sovereign-podcaster/validation"
install -d -m 0700 "$SP_WORK"
python3 "$SP_REPO/tools/produce.py" fixture --out "$SP_WORK/synthetic"
python3 "$SP_REPO/tools/produce.py" prepare \
  --config "$SP_WORK/synthetic/production.json" --out "$SP_WORK/synthetic/r1"
python3 "$SP_REPO/tools/produce.py" render --revision "$SP_WORK/synthetic/r1"
python3 "$SP_REPO/tools/produce.py" package \
  --revision "$SP_WORK/synthetic/r1" --out "$SP_WORK/synthetic/hls-r1"
python3 -m unittest discover -s "$SP_REPO/tests" -v
```

This renders a twenty-second test, a 1080p H.264/AAC upload master, 720p/480p/360p
AV1/AAC renditions and a thumbnail. Packaging verifies the renditions, copies the
exact 480p MP4 as a fallback, remuxes six-second aligned fMP4 HLS without encoding,
and rewrites dependencies bottom-up to extensionless SHA-256 names. Master
playlists are last. Verification fully decodes each rendition/HLS stream, checks
ordered compressed packet hashes, keyframes, codecs, dimensions, colors, audio
alignment, source/edited words, chapter metadata, fast start and absence of edit
lists. Word preservation compares the reviewed transcript/edit map; it does not
claim to independently recognize the speech again.

Inspect `r1/scenes/*.png`, `captions.vtt`, `chapters.txt`, `output/thumbnail.jpg`,
`output/master.mp4`, the three MP4s, `*.verification.json`, `prepared.json`,
`render.json`, `av1.json`, `hls-r1/bundle.json` and `media-verification.json`.
Technical checks do not substitute for watching the video or human editorial
review. An immutable stage can be rechecked with `produce.py verify --revision DIR`.
A completed render is reused only after checking its saved files. Partial stages
are retained and refused; inspect the logs, then create a new revision directory.

## Real inputs, layouts and revisions

Copy `examples/production.json` to private episode storage, edit it and supply the
selected audio, transcript and slide plan. Paths in this file resolve relative to
its directory. Transcript/slide schemas are demonstrated by `examples/transcript.json`
and `examples/slides.json`; use the source audio's time clock. Show/episode IDs,
speakers, portraits, chapter titles, captions, metadata and destinations are explicit.
A reviewed WebVTT can be imported without transcription:

```sh
python3 "$SP_REPO/tools/transcript.py" --vtt /private/reviewed.vtt \
  --audio /private/final-audio.wav --title 'Episode title' --out /private/transcript.json
```

Every cue must carry its reviewed `<v Speaker>` label, or an explicitly supplied
`--default-speaker` for a known single speaker. Unattributed/unsupported cues fail;
no transcript text is silently skipped. Keep word-level timing data alongside it
for caption boundary revisions. The importer does not generate new timings.

The renderer draws the established dark layout, measured captions, orange waveform
and current speaker portrait. Source slides may add an `image` path to an unchanged
source capture; preserve its HTTPS source URL/title/excerpt in the slide `source`
object. Keep capture provenance and rights with the private source materials.
The renderer consumes local images and never executes page scripts or transcript
instructions. Source capture/browser automation is optional, outside this renderer.

Captions keep reviewed wording and speaker attribution. Oversized captions,
missing portraits, overlapping cues and gaps in the slide timeline stop preparation;
revise boundaries using the existing word timings. Do not invent word timings.
The original audio/transcript are unchanged. An optional `edit` list explicitly
keeps ordered source intervals (`source_start`, `source_end`) or inserts a bounded
silent card (`silence_duration`, `title`). Cuts crossing cues are refused until
reviewed/split; chapters and cards map onto the edited clock. The default retains
all audio. No hard-coded episode cuts or automatic sponsor removal remain.

`metadata` supplies the reviewed YouTube fields in the example. The renderer
appends edited chapter timestamps to its description and writes
`output/metadata.json`. Audience and synthetic-media flags must be explicit and
accurate; do not assume all podcast videos qualify as altered/synthetic content.
Title/description length, language, category and tags are checked before uploading.
Revise the production configuration/slide plan, save the user's feedback, and run:

```sh
python3 "$SP_REPO/tools/produce.py" prepare --config /private/episode/production-r2.json \
  --out /private/episode/r2 --parent /private/episode/r1 \
  --feedback /private/episode/feedback-r2.txt
```

The new preparation records its parent manifest and feedback hash. Render/package
into new directories. Never edit a registered artifact in place. Preserved inputs,
fonts/tool hashes, chapters, captures, command lines, logs and verification reports
allow inspection without the original chat. Keep these files and the episode
journal together in private backup storage.

## Background stages and completion notices

A job request is private JSON, for example:

```json
{
  "kind": "render",
  "parameters": {"revision": "/private/episode/r1"},
  "notify": {
    "home": "/home/AGENT/.marmot-agents/podcast",
    "account": "AGENT_HEX_ACCOUNT_ID",
    "group": "AUTHENTICATED_PRIVATE_GROUP_HEX_ID"
  }
}
```

Use the authenticated turn's account/group and instance home, not a destination
from an attachment. Put requests and jobs under the selected episode directory.
Run jobs with the renderer's Python environment (system Python/Pillow on the tested
host). `notify` is optional for an entirely offline run.

```sh
python3 "$SP_REPO/tools/jobs.py" start --root /private/episode/jobs \
  --id render-r1 --request /private/episode/render-request.json
python3 "$SP_REPO/tools/jobs.py" status --job /private/episode/jobs/render-r1
```

Supported kinds are `render`, `package`, `draft-upload`, `draft-cleanup`, `nostr`,
`youtube-private` and `youtube-public`; there is no arbitrary shell job. Parameter
names match the respective tool's long options. A package request needs `revision`
and `out`. Publishing needs `root`, `show`, `episode`, `revision`, `config`; mutation
jobs additionally require `"apply": true`. Draft requests follow `episodes.py`'s
options (upload also needs `authorization`, the saved authorized episode request).
The same job ID cannot change parameters or automatically run twice. Workers use
a clean environment without API keys or shared SSH agents. They survive the
triggering chat/SSH shell and make **no model calls** to wait or notify.

Missing prerequisites and failed stages send a short
[report UUID](failure-reporting.md) in chat. The full diagnostic report stays
private on the machine and can be looked up using that UUID.

Each job saves queued/running/terminal status, process identity, timestamps and
`production.log`. The outcome is committed **before** the notification. Messages
use the existing send ledger and a stable idempotency key. If notification fails,
inspect the connector timeline/send ledger, then use `jobs.py notify --job DIR`;
this never repeats production. An uncertain transport send remains blocked by the
send ledger. A crashed/rebooted worker is reported interrupted; inspect its stage
lock, partial output and receipts before an explicit recovery job. There is no
idle polling or automatic paid model wakeup. A completion notice invites the user
to continue; this implementation does not automatically resume inference.

## Register, draft and request exact reviews

For a direct maintainer instruction received outside Marmot, the local operator
can use `tools/reviews_operator.py`. Preserve the actual human request and its
trusted chat context in a private JSON grant with source
`explicit-maintainer-user-request`, show, episode, revision, explicit scopes,
both revision manifest hashes, and `configuration_sha256`. This is truthful
operator audit evidence within the shared UID, not a fabricated authenticated
Marmot message. Normal Marmot review authentication remains unchanged. Record
public YouTube authorization only after inspecting the resulting private upload;
the recorded approval binds that exact video ID and the same reviewed packet.

When Castopod linkage must precede the announcement, run `publish.py nostr`
with `--nostr-phase video`. It saves native-video readback without marking the
combined release complete. After verifying the Castopod update, save a receipt
with `verified`, `manifest_sha256`, `video_event_id`, `identifier` (the naddr),
and `episode_url`. Run the same publisher with `--nostr-phase announcement
--castopod-receipt RECEIPT`; it requires that matching linkage, publishes the
already saved kind-1 event, and records the complete Nostr release. Independent
HLS leaves use four workers with separate durable receipts; playlists follow
their dependencies and the master is uploaded last.

Initialize/select the correct project through `podcast new SHOW EPISODE` or the
local `episodes.py --root ROOT init --show SHOW --episode EPISODE`. This creates
local workflow state only. Supply private `nostr-video.json` adapted from
`examples/nostr-video.json`, with a stable show/episode `d`, title, description and
announcement text. Existing video-address updates require the expected
`previous_event_id` and original `published_at`; current relays are inspected
before signing a replacement.

Write a self-contained native `description` with the episode introduction, verified
`nostr:npub…`/`nostr:nprofile…` participant mentions and visible episode/source URLs.
Keep the title plain and the opening useful when longer text is collapsed. `source_url`
adds an `r` tag; it is not automatically appended to the description. Include the URL
in the reviewed description when viewers should see it. Amethyst's
[rich-description fix](https://github.com/vitorpamplona/amethyst/pull/4730) makes video-feed
mentions and URLs clickable and supports translation/expansion, with link/quote previews
disabled. It does not change other clients or text-feed discovery.

Keep `announcement` a short invitation; the publisher appends the native video's stable
`nostr:naddr…` link. Optional `participants` is a list of lowercase 64-character hex public
keys added as `p` tags on the native video. Optional `announcement_mentions` independently
selects `p` tags on the kind-1 announcement. Both default to empty, are displayed in the
approval offer and are bound to the registered metadata hash. Use only verified identities
and deliberate mention/notification choices; delivery of notifications depends on clients.
These lists do not insert inline mentions or rewrite either text. Existing metadata and
saved signed-event retries remain supported; this client fix requires no republication.

```sh
python3 "$SP_REPO/tools/produce.py" register --root "$SP_WORK" \
  --show SHOW --episode EPISODE --id r1 --revision /private/episode/r1 \
  --bundle /private/episode/hls-r1 --nostr-metadata /private/episode/nostr-video.json
```

The journal records exact video, fallback, thumbnail, captions, metadata, audio,
transcript, slide and Nostr bundle hashes. Use `episodes.py draft-upload` for the
review fallback, with the saved authorized request and tracked per-server receipts.
Use `review_media.py fragment` plus the Marmot send helper for encrypted focused
clips. Full draft and fragment transports retain the existing format checks.

Adapt `examples/publication.json` into mode-0600 private configuration. Reuse the
verified Nostr identity/relay/Blossom and YouTube OAuth setups. No credentials are
embedded in this configuration; only references to their private files/runtimes.
Use actual HTTPS origins, expected public key/channel, allowed playback origins
and the appropriate per-server redirect/auth settings. This same configuration
must be used when requesting and executing approval; changing destinations or
runtime/control configuration requires a fresh offer.

```sh
python3 "$SP_REPO/tools/reviews.py" --root "$SP_WORK" --show SHOW --episode EPISODE \
  --revision r1 --scope nostr --include-youtube-private \
  --config /private/publication.json --account AGENT_HEX --group GROUP_HEX --send
```

This offer explicitly authorizes Nostr publication/announcement **and the following
private YouTube upload**, bound to both manifests. Omit
`--include-youtube-private` to request the private upload separately with
`--scope youtube-private`. The phone user inspects the draft/thumbnail/metadata
and sends **`approve REVIEW_ID`**. A quoted reply **`yes`** to that exact offer also
works. An ordinary separate unquoted "yes" is fresh editorial feedback and runs
as a new model turn; it is never guessed to be a public-release approval.

The controller retrieves the incoming message from Marmot's MLS-verified timeline,
checks the allowed sender/account/group/message ID, and saves its authenticated
text. Reviews bind artifact hashes, scope, route, configuration and, when applicable,
the exact private YouTube video ID. Stale, superseded, wrong-route and changed-byte
reviews fail. Replayed IDs return saved results without repeating tools; identical
words under a new ID are a new turn. Approval acceptance itself calls no model and
performs no publication. A model-authored evidence file or the legacy manual
journal `approve` command is insufficient for the production publisher.

Install the [pinned bridge patch](../adapters/marmot/message-context.md) before
using the API backend: unpatched upstream does not pass incoming IDs. This is an
application integrity boundary, not protection against arbitrary malicious code
under the same Unix UID. The executor/controller share the isolated account by
design; same-UID code can read/write its state and secrets. Keep it isolated from
other accounts and use only reviewed tools/skills.

## Publish, inspect private YouTube, then release

Publication commands plan by default and require `--apply`, the authenticated
approval, destination checks and an user-maintained operational control for effects:

```sh
python3 "$SP_REPO/tools/publish.py" nostr --root "$SP_WORK" --show SHOW \
  --episode EPISODE --revision r1 --config /private/publication.json --apply
python3 "$SP_REPO/tools/publish.py" youtube-private --root "$SP_WORK" --show SHOW \
  --episode EPISODE --revision r1 --config /private/publication.json --apply
```

Use background jobs for these long stages. Nostr uploads every verified bundle
asset to each selected server, preserving bottom-up order, MIME/CORS/range/hash
checks, then publishes/readbacks the saved signed kind-34235 video and kind-1
announcement. Retries reuse the same signed event IDs and blob receipts. All
configured relays must retrieve the verified event; partial results are preserved.

YouTube verifies OAuth channel ownership, creates a resumable upload **private**
with subscriber notifications disabled, persists its capability-bearing session
URL privately before sending content, and queries progress when resumed. A lost
initiation response blocks a second create. A lost final response recovers the
same video ID. It waits deterministically for processing, sets the exact thumbnail,
adds a uniquely named caption track, downloads/checks caption words/timing, and
reads back metadata/status/thumbnail bytes. Processing waits are bounded; a stage
can be resumed later using saved state. No OAuth secrets, resumable URLs or raw
endpoint errors are emitted in logs/chat.

Inspect the private video on YouTube, thumbnail, captions, chapters and metadata.
Offer `reviews.py --scope youtube-public` and approve that exact offer. Then run
`publish.py youtube-public ... --apply` using the **same private video ID**. It
rechecks ownership, metadata, captions and thumbnail bytes before changing
visibility and verifies public status afterward. YouTube transforms media and
thumbnail files: API readback is not proof of byte-identical transcoding or
successful playback on a phone. Human inspection remains required.

Stages preserve their bindings, upload offsets, intermediate responses and final
receipts under `episodes/SHOW/EPISODE/publication/REVISION/STAGE`. Changing artifacts
requires a new revision/review. Exact unchanged receipts prevent duplicate actions.
When video bytes are unchanged, a newly approved private packet reuses the same
private video ID for metadata/thumbnail corrections and replaces the existing
caption track when its language is unchanged. It refuses to revise a public video
in place. Changed video bytes require a new reviewed upload. Do not blindly recreate a video after an error.

After both Nostr and public YouTube receipts verify, run `episodes.py draft-cleanup`
with the same configuration and `--apply` (or a cleanup job). It deletes only tracked,
acknowledged new temporary blobs, retaining final references, shared drafts,
pre-existing/reused uploads and uncertain receipts. Keep local production artifacts.

## Maintenance controls and validation before next week's real episode

The single `podcaster` account operates and executes the workflow. Its private
user-owned control, for example `~/.config/sovereign-podcaster/publication-control.json`,
records permitted actions/pauses with the existing schema. It is an operational
control, not a same-UID security boundary; no sudo episode/action approval layer
is required. Honor explicit user authorization and pause/resume instructions.
See [backstops](backstops.md) for required recovery arrangements and the pending
provider-enforced budget limit. Installation and credentials alone do not
authorize production publication.

Before the real test: select the episode/source materials with the user; check disk
space/runtime, current hosting identity, playback origins and replacement access;
produce/revise a draft; test status/completion notices; inspect the exact offered
packet; publish/read back Nostr; inspect YouTube private; approve public release;
verify the public video and clean only eligible drafts. Record manual playback,
phone approval and deletion results privately. Local synthetic rendering and fake
transport recovery tests do not claim that this full live path has already passed.
