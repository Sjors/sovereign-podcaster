# Workflow and artifacts

Use one directory per episode and immutable revision directories inside it.
Keep these outside source control. The [episode flow](episode-flow.md) implements
local episode/context selection, artifact/approval records, tracked Blossom drafts
and guarded cleanup. The [production tools](production.md) now compose/render revisions, package AV1/HLS
and publish through guarded, authenticated Nostr/YouTube stages. Background workers
notify the originating Marmot group without idle inference. The slide contact sheet
and fallback/clip helper remain usable separately; the first live full-episode
validation is still pending.

| Stage | Reviewable output | Resume evidence |
| --- | --- | --- |
| Intake | original audio, full transcript, source provenance | hashes, episode/show identity, original clock and transcript review status |
| Slides | timed plan, source captures/excerpts, contact sheet | plan/input/tool hashes, feedback and revision parent |
| Video | master, captions, chapters, render logs, QA frames | exact commands/dependencies, timeline mapping, decode/alignment results |
| Draft review | 480p fallback MP4 on selected Blossom servers; focused encrypted Marmot clips | immutable revision hashes, upload/send receipts and feedback |
| Nostr storage | rendition/HLS bundle, offline upload plan | hash-addressed assets, per-destination receipts and public readback |
| Nostr announcement | unsigned preview, then signed event | exact artifact hashes, authorized identity/destinations, event ID, relay ACK and signature-verified retrieval |
| YouTube preparation | thumbnail, title, description, chapters, captions, flags | metadata JSON and hashes; an upload requires its own authorization |
| YouTube review/publication | private video/processing result and final review packet | video ID/channel, master/thumbnail/metadata/captions hashes, human approval, publication/readback receipts |

Storage upload, Nostr announcement, private YouTube upload, and public YouTube
publication are separate external actions. Initial setup authorizes none of them.
Retain authorization evidence with scope, actor, UTC time, destination and exact
artifact manifest hash. Record approval separately from technical QA. Changed
content invalidates approval for affected downstream artifacts. An agent cannot
grant itself approval by writing a JSON status. The production controller enforces
current authorization and digest checks before effects, with saved-byte checks
at stage boundaries and source identity/stat checks during chunked uploads.

Before ambiguous retries, inspect remote state. Never recreate an uploaded video
or a timestamped signed event simply because a request timed out. Keep upload
session URLs private. Persist partial receipts atomically under a per-episode
exclusive lock. Keep originals read-only and preserve previous revisions.

Reuse the established media practices: complete sentences with measured font
metrics, accurate speaker attribution, unchanged reviewed words, common caption/
source/chapter clock, explicit edit maps, no silent clipping. Prefer actual source
pages for technical explanations; simple topic/version cards are fine. Edits such
as sponsor removal are episode-specific decisions, not defaults. Compose smaller
outputs from original artwork/audio; verify full decode, alignment and keyframes.

Publishing configuration must require explicit show, channel, signing identity,
hosts and destinations. Replace hard-coded identities with configurable expected
identities, retaining mismatch rejection. Carry maintenance pause checks into the
new setup before enabling writes. The guard must be supplied by the operator,
private/user-maintained in the single-user runtime and checked before staging
and immediately before mutation. It is an operational pause, not a same-UID
security boundary; see [backstops](backstops.md). Missing/malformed configuration fails closed; a new home directory must
not silently bypass the old guard. Preserve database/media/notes/transcript scope.

Acceptance plan: synthetic revisions and corruption checks first; then ask the
user for an episode, canonical audio, complete reviewed transcript (timed VTT plus
word-level review/timing data if available), source links, portraits/rights and
requested editorial changes. Do not infer permission from previous episodes.
Review a short rendered sample before a full encode. Publishing integration and
real-device playback checks follow only when those stages are requested.

Delete temporary remote drafts only after both Nostr and public YouTube publication
are verified for the approved artifacts. Retain any blob used by a final release or
another active episode, and preserve local revision and review evidence.
