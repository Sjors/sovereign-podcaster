# Reuse and release gate

Production media and private deployment records are not vendored in this repository.
Selected owner-supplied tooling and upstream notices have the provenance described below.
The owner-supplied public patch catalog was adapted from the original gist at
revision `95a38d3727a79205cf7c8dc67278f7c24c2b86fb`; see
[the canonical catalog](patches/README.md) and its source snapshot.
The YouTube helper, tests and pins were initially copied unchanged from the owner's private
`youtube-publishing` skill on 2026-11-01 under the owner's explicit migration
request. A migration-marker guard and its test were then added to prevent old-path
reauthorization. Its generic skill/operations text was adapted; personal instance records
and all credentials remain outside this repository. No license file was present
in that private skill. These owner-supplied files join the pending license review;
their Google dependencies remain external and retain their own licenses.
New code has no public license selected yet. Before public release, choose its
license with the owner and complete the following provenance review. A private
file's availability does not establish permission to open-source it.

| Candidate | Evidence inspected | Proposed handling |
| --- | --- | --- |
| Existing episode demo/full renderer | Python, Pillow/font metrics, FFmpeg, SVG, source capture and QA | Extract small pure functions after authorship/license review; remove episode constants and sibling imports |
| Local Whisper workflow | faster-whisper turbo, sherpa-onnx, word timing/review records and locked environments | Keep current workflow; import finished transcript first; assess model/code licenses separately |
| YouTube helpers | official Google clients, pinned dependencies, channel/scope/endpoint checks and private resumable upload | Port checks with configurable expected identity; separate metadata from external actions |
| Blossom tools | content-addressed HLS, AV1 codec metadata, complete readback, CORS/MIME/ranges | Preserve bottom-up hashing, local path containment and resume verification |
| Private podcast skills | article, Castopod publishing/maintenance, Nostr publishing | No license found in their private skill repository root; review each file and ownership before copying |
| Public skills repository / fact-checker | MIT license files present | Preserve exact notices for any selected files; source verification is useful, not required runtime scaffolding |
| Castopod patches | local upstream clone has AGPLv3 license | Keep patches with upstream base, notices, corresponding source and tests; do not relabel under the seed's eventual license |
| Nostube patches | local upstream clone has MIT license | Keep upstream copyright/license, patch authorship, bases and dependency order |
| Logos, portraits, screenshots, transcripts and audio | existing episode-specific provenance | Obtain/record rights per asset; do not treat the software license as covering media |

Retain patch registers for RSS ranges, real audio sizes, RGB/feed artwork,
independent episode-card edits, video integration, signed-event verification,
restricted channel player, safe same-origin return links and codec detection.
Pin upstream commits and patch SHA-256 values, export/replay in clean checkouts,
record deployed source separately from proposed branches, and refresh upstream
overlap before upgrades. Replace a patch only after the alternative covers the
same tested behavior. Back up code/config/database/media privately; keep rollback
limits and verify public feeds/media after an authorized deployment.

Before release: explicit file allowlist, license/notice review, private-information
and secret scan of files AND Git history, synthetic examples, fresh checkout test,
dependency lock/provenance review, and owner review. Do not publish production records,
session logs, backup bundles or credentials. Public host/account placeholders must
replace private configuration without weakening destination or maintenance guards.


## Nostr skills and delivery tools

The owner authorized copying `nostr-publishing` and `fetch-nostr-events` from the
private skills repository on 2026-11-01. [The import manifest](imports/nostr-skills.json)
records each copied file's hash before adaptation. The
publisher's identity checks, separation of signing/sending and exact-event retries
are preserved. Generic instructions replace private identity/show conventions;
the owner's article-specific rules remain in the private article workflow.
Fresh identity creation additionally rejects repository destinations and symlinks.
The copied files had no accompanying license; public release remains subject to
owner license selection and the existing release gate.

`tools/blossom.py` adapts the owner's existing video workflow's HTTPS-origin
validation, kind-24242 authorization, streamed upload and full public readback.
It adds receipt-bound cleanup, short-lived hash/server/action-scoped tokens,
explicit expected identity and configurable client origins. It does not port the
full HLS encoder or weaken its verification. The source was an owner-supplied private video workflow; the import manifest
retains its source hash without exposing the private directory layout. No production media or deployment records are copied into Git.

External runtime packages remain unvendored: coincurve 21.0.0 (MIT OR Apache-2.0,
including libsecp256k1 notices), websocket-client 1.9.2 (Apache-2.0), bech32 1.2.0
(MIT), and uv 0.13.1 (MIT OR Apache-2.0). CPython 3.11.17 is an independent
python-build-standalone installation, retaining its Python/third-party notices.
Verify installed distribution metadata/notices when updating pins. No coincurve
source patch is required with this tested Python version; the Python 3.14
build incompatibility is documented rather than patched locally.

## Marmot conversation adapter

The owner requested a shared Marmot skill and fresh isolated identity. Only the
owner's `wn_control.py` implementation was copied from the unpublished skill,
then made configurable and extended with guarded text sends. The
[import manifest](imports/marmot-skill.json) records its original hash. Source
files were untracked in the private skills checkout at import time; there was
no source license file. Owner license selection and release review still apply.
Private installation, group/export and transcript-liaison instructions were not
copied into the public repository. They remain private instance notes.

The setup delegates to the upstream installer rather than vendoring the changing
Marmot manual. [The release lock](../adapters/marmot/release.json) records the
tested pre-release cohort, installer hash and archive provenance. Downloaded
binaries remain outside Git. Marmot/MDK's MIT notice is retained in
[third_party/marmot/LICENSE](../third_party/marmot/LICENSE); the upstream source
and current agent instructions are linked from the adapter/skill. No cryptographic
Marmot/MLS implementation is copied or replaced by this adapter.

The new Agents API backend reuses this repository's existing private-file/HTTP
transport helper. It does not invoke ordinary API-authenticated Codex inference
or import the maintainer's native login/history. Session requests, pending work,
completed responses and usage remain in the isolated user's private state.

The episode journal and media helper are new repository tools. Established AV1
fallback settings were adapted from the owner’s existing render workflow; see
[episode-media import provenance](imports/episode-media.json). Private episode
records, chat content, credentials and production artifacts were not copied.

## Castopod publishing and maintenance toolkit

The owner explicitly requested reusable copies of the private publishing client,
PHP server helpers and maintenance skill. [The import manifest](imports/castopod-skills.json)
records working-file SHA-256 hashes; some source
files had uncommitted changes, which were preserved without modifying the old
private setup. Only selected code/tests/UI metadata were copied. Generic skill
and operations text replaces private show defaults, machine paths, historical
repairs and deployment/backup records. Private patch exports were not copied;
the maintained public fork/catalog remains the source for application patches.

The new client parameterizes the maintenance pause, adds protected fail-closed
checks, receipt-bound operations, local/shared-server episode locks and optional
local transport, and disables SSH agent/forwarding reuse. PHP helper cohort 1
adds a version marker and server-side lock but retains installed Castopod model
operations. Helpers are application integrations, not an imported Castopod tree.
No license file accompanied the private skills: owner license selection and
review of any Castopod-derived portions remain part of the public-release gate.
Preserve Castopod's AGPLv3 obligations for any derived code/redistributed patches;
the repository's eventual license must not relicense upstream work.

Transport/guard/receipt tests use offline fixtures. PHP helper syntax was checked
with PHP 8.3.6/POSIX. Instance access tests and runtime inventories stay private;
offline results do not establish a production mutation, schema migration, new
release compatibility or deployment of a helper cohort.

## Complete video and publication port (2026-11-01)

The owner explicitly requested these reusable production ports. Exact source
hashes and adapted portions are recorded in [video-production.json](imports/video-production.json).
`tools/video/av1_packaging.py` retains the working AV1 handoff implementation;
`hls.py` extracts its pure content-addressing/validation/tag functions.
`verify_hls.py` retains packet identity/full-decode checks; `verify_mp4.py` adapts
MP4 atom/audio alignment functions. `produce.py` adapts the working dark layout,
Pillow/ASS metrics, waveform/speaker composition, explicit clock edits and master/
rendition settings without importing the episode modules or their side effects.
No private episode media, portraits, transcripts or page captures are distributed.
The owner code had no separate license notice; it remains under this repository's
pending public-release license review. New job/review/publisher code joins that
review. FFmpeg (configured codec-specific licensing), Pillow (HPND), Ubuntu fonts
(Ubuntu Font Licence), Google clients, bech32, coincurve and websocket-client remain
external dependencies with their own notices; do not relabel or bundle them.

The Marmot context patch targets MIT upstream code. Its upstream notice remains
in `third_party/marmot/LICENSE`; commit, patch hash, build instructions and tests
are in the [canonical patch catalog](patches/README.md) and adapter guide.

## Local transcription port (2026-11-02)

The owner requested migration of the current transcription skill and tools after
review of existing episode work. `skills/podcast-transcription` adapts that owner-supplied
skill and references; private queue/task paths remain outside the public copy.
`tools/asr.py` adapts pure recognition, anonymous diarization and review-material
functions from the existing backfill analyzer. `tools/captions.py` adapts its
reviewed word correction and parser-compatible caption renderer. The old queue,
media and ad-cleanup operations are not imported or unpaused. Model weights are
not distributed; the isolated instance reuses explicitly selected local model
files with private provenance. Source code, model weights and package licenses
remain distinct. Owner-supplied code/skills have no separate license notice and
remain subject to the repository's existing public release/license review.

## ngit agent guidance (2026-11-12)

Earlier revisions included unchanged copies of ngit's skill version 1.19 under
`.agents/skills/ngit/` and `.claude/skills/ngit/`, installed with
`ngit skill install` from
[ngit v3.0.5](https://github.com/DanConwayDev/ngit-cli/tree/v3.0.5/skills/ngit),
by DanConwayDev, licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Those copies are no longer vendored. The README and agent instructions point to
the [upstream guidance](https://ngit.dev/agents/); optional local installations in
those directories are ignored by Git. The ngit binaries are also installed
separately.
