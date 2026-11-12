# TODO

These are placeholders for later work. Reuse the existing operator workflows,
then port only the needed tools/skills after checking provenance, licenses and
private configuration. Keep the implementation small and preserve existing
operational guards. See [episode flow](docs/episode-flow.md) for what is already
implemented.

## Existing episodes and the two entry paths

- [ ] Make intake explicit: **add video to an existing hosted episode**, or
  **produce a new episode from raw recordings**. Both eventually use the same
  video workflow. Keep local project creation distinct from creating a hosted
  podcast episode; the current `podcast new` command only creates a local project.
- [ ] Import/inspect an existing episode using explicit show/provider identity.
  Record its stable ID/slug, RSS GUID, canonical audio/transcript references,
  source hashes and any existing Nostr/YouTube video IDs. Populate the local
  episode list without creating duplicates or silently selecting source media.
  Reuse an existing reviewed transcript; use the local Whisper workflow if
  transcription or revision is needed.
- [ ] Attach approved video references to that **same existing podcast episode**
  and verify the hosting page/player/links. Preserve its audio enclosure, GUID,
  publication date, transcript and unrelated metadata. Define the same handoff
  for newly published podcast episodes after the raw-audio/transcript stages.

## Portable video production and publication tools

- [x] Port the complete renderer/layout, configurable private assets, measured
  captions, chapters, explicit edited clocks, immutable feedback revisions and QA.
- [x] Port verified AV1 ladder/independent fallback, stream-copy HLS, content
  addressing, MIME/codec metadata and production signed video/announcement receipts.
- [x] Add resumable private YouTube upload, thumbnail/metadata/caption handling,
  processing/readback checks, private packet corrections and reviewed-ID public release.
- [x] Require exact authenticated artifact/destination approvals and protected
  maintenance checks for production writes. See [production](docs/production.md).
- [ ] Configure user-maintained production controls and actual per-show destinations
  for the separately authorized live test; keep writes closed during setup.

## Resumption, review replies and completion notifications

- [x] Add bounded background stage workers with durable terminal results and
  Marmot completion/failure notifications. Notification recovery cannot repeat
  production; no idle model polling or automatic paid inference resume.
- [x] Pass incoming Marmot message/sender IDs through a pinned, tested upstream
  bridge patch; verify against its authenticated timeline. Separate identical-text
  replies are distinct turns, exact-ID replays cannot repeat effects, and approvals
  bind the reviewed packet/route/destination/private video ID.
- [ ] Verify the updated bridge/help/approval and completion-notice paths from the
  phone in the real-episode test. Synthetic/fake transport tests passed; they do
  not claim an independent human or full live provider validation.

## First complete video workflow validation

- [x] Port the video-stage production components needed for existing final
  audio/transcript input. Synthetic rendering/packaging and transport recovery
  fixtures are available. Raw-recording and hosting intake work stays separate.
- [ ] With the next operator-selected video episode, test the complete Marmot
  request/revision flow, draft upload, focused encrypted review clips, Nostr
  publication/announcement, private YouTube review, explicit public approval
  and protected draft cleanup. Recheck resume/recovery and exact artifact
  records. Keep this pending until the episode and source material are supplied;
  no idle model polling or scheduled test is needed while waiting.

## Editing a new episode from raw audio

- [ ] Add an intake/editing workflow for a new recording, preferably using
  separate speaker tracks. Preserve original files, supplied speaker identities,
  synchronization offsets and source hashes; support a mixed recording when
  separate tracks are unavailable.
- [ ] Reuse existing editing/mixing tools for cleanup, cuts, levels and the final
  podcast mix. Keep versioned edit decisions and a raw-to-edited timeline map;
  preserve aligned per-speaker edited tracks for transcription when available.
- [ ] Review focused audio/video excerpts through Marmot, record feedback and
  approve the exact finished audio. Verify synchronization, complete decoding,
  clipping/loudness and intended cuts before handing off to transcription.

## Transcript production and Marmot feedback

- [x] Resume transcript review on completed local jobs and authenticated exact-question
  thumbs-up reactions using a separate token-free watcher. Preserve event IDs,
  original episode sessions, task scope, busy/uncertain outcomes and send receipts.
  This does not turn reactions into video publication approval.
- [x] Port the existing Whisper transcription/review workflow. Preserve original
  audio, word/cue timing, speaker attribution, source evidence and immutable raw
  recognition. Keep hosted OpenAI transcription outside this work.
- [ ] Preserve each subsequent transcript editorial revision as an immutable
  snapshot, with its review decisions and publication/correction receipt. The
  current pilot retains raw ASR, final hashes and logs; draft review files can
  still be edited in place.
- [ ] Prefer separate speaker tracks over a mixed recording when available.
  Use tracks reflecting the approved edits, or map raw-track results through the
  recorded edit timeline. Reconcile overlaps and cue timing against the final
  podcast mix; retain supplied speaker identities rather than guessing them.
- [ ] Ask focused review questions in the episode's Marmot group, tied to an exact
  transcript revision and audio/video interval. Accept voice-memo feedback:
  retrieve/decrypt the attachment privately and transcribe it with the existing
  Whisper tooling. Follow current upstream Marmot instructions for media access.
- [ ] Record the question, authenticated reply/voice-memo reference, transcription,
  interpretation and resulting correction. Handle late feedback without applying
  it to the wrong episode/revision. Distinguish received feedback from reviewed
  transcript changes; do not inherit another workflow's timeout/approval policy.

## Transcript uploads

- [x] Wire the transcript workflow to the shared Castopod attachment operations. Keep attaching
  a transcript to an existing episode separate from publishing a narrated article
  or creating a new episode. Require explicit show/episode identity.
- [ ] Preserve reviewed words, edited/original timeline mapping, speaker labels,
  formats and provenance. Record exact uploaded artifact hashes and receipts.
- [x] Verify installed parser/model compatibility and actual public VTT/JSON,
  episode-page and feed delivery. Preserve GUID, publication date, enclosure and
  transcript associations. Inspect existing attachments before ambiguous retries.

## Publishing a newly produced podcast episode

- [ ] Add the new-episode handoff: approved audio edit → completed/reviewed
  transcripts → podcast publication. Stage the audio, transcript, show notes,
  artwork and episode-specific metadata on the same explicitly selected
  Castopod draft, reusing the existing publishing helper.
- [ ] Make the episode public only after transcripts are done and the required
  audio/transcript/metadata review and publication authorization are recorded
  against the exact artifacts. Retain the draft/episode ID across retries.
- [ ] Verify published audio, transcript, episode page and RSS delivery; record
  artifact hashes, episode identity and publication/readback receipts. This
  audio-podcast stage precedes the existing workflow that starts from an
  available episode and its full transcript to produce/distribute video.

## Castopod maintenance and new release tags

- [x] Port the existing `castopod-maintenance` skill with configurable hosts,
  paths, runtime, backup locations and operator-owned maintenance controls. Keep
  instance records, credentials and deployment evidence outside this repository.
- [x] Document a reusable **new-tag procedure**. Always start by checking whether
  each required behavior/fix has already been merged upstream, and whether it is
  actually present in the proposed release tag. A merged contribution on another
  branch or a newer unreleased commit does not establish coverage in that tag.
- [ ] Test upstream equivalents against the existing regression cases before
  deciding which local patches remain necessary. Omit superseded patches only
  after their behavior is validated; retain provenance and recovery material.
- [ ] When carrying patches is no longer a trivial cherry-pick, recommend that
  each operator maintain **their own GitHub fork**. Keep topic/integration branches
  based on explicit upstream tags, preserve authorship/licenses, and record patch
  order, dependencies and tested commits. Treat this repository's
  [patch catalog](docs/patches/README.md) as documentation/provenance, not a
  substitute for maintaining the operator's patched source. Check upstream first
  again at every release rather than indefinitely carrying the old fork diff.
- [ ] Cover live-state inspection, private verified backups, isolated staging,
  required migrations/builds, behavior/feed/media regression checks, authorized
  deployment, public readback and migration-aware rollback. Preserve unrelated
  deployed edits. Use [the existing maintenance notes](docs/patches/maintenance.md)
  as the starting point. Keep validated Git work unpushed for Mac signing/pushing.

## Other Castopod operations

- [x] Port/adapt the existing `castopod-publishing` skill and its deterministic
  helpers, including the Python SSH client (`scripts/publish.py`) and PHP
  server-side helpers (`scripts/castopod/`). Document their installation,
  runtime/access prerequisites and read-only list/inspect validation. They cover
  inspecting/listing episodes, preparing drafts, creating/updating episodes,
  replacing audio or show notes, attaching transcripts and verifying authorized
  publication. The reusable client, server helper cohort, tests and installation
  guide are now included; the original private/live setup is preserved during migration.
- [x] Parameterize show/account/host/path defaults while preserving explicit
  destination checks, dry-run/apply separation, shared mutation/per-episode locks,
  maintenance pauses, remote-state inspection before retries and publication
  authorization. Keep editorial/audio generation in its source workflow.
- [ ] Roll out the reviewed helper cohort and maintenance state when
  the operator authorizes server installation. Validate a real disposable-instance
  mutation and the installed parser/public-readback path before enabling the new
  client's production writes. Sharing the toolkit and validating SSH/read access
  do not perform that deployment or reopen a maintenance pause.
- [ ] Inventory additional operations separately (for example scheduling,
  podcast-wide settings or deletion). Do not imply that the current episode
  helper supports them; inspect the installed interfaces and define scope before
  adding them.

## Podcast-host access handoff

Before an access handoff, record remaining server work and validate replacement
access and independent recovery. Keep server-side grants, fingerprints, fallback
credentials and cutover evidence private. Remove only the intended grants after
replacement checks pass; deleting a local key does not revoke remote access.
Check indirect routes through executors, SSH agents, jump hosts and source-update
paths. This checklist does not authorize a cutover or revoke credentials.

- [ ] Document remaining work and completion criteria privately.
- [ ] Validate the successor's required helper operations and recovery route.
- [ ] Revoke the old grants only under explicit cutover authorization.
- [ ] Verify old access is closed and the replacement workflow still works.

## Reproduction, release and recovery

- [ ] Choose the repository's license and finish the existing
  [provenance/release review](docs/provenance.md), including copied skills,
  dependency notices, private-information removal and media/template rights.
  Have another person reproduce the supported setup from the repository and
  documented dependencies without the maintainer's private checkout or chats.
- [ ] Document and test backup/restore of episode state, original/reviewed media,
  manifests, approvals, publication receipts and conversation references on a
  replacement machine. Handle private configuration, credentials and Marmot
  state separately using the relevant upstream guidance. Restore without
  automatically repeating uploads, announcements or other completed actions.

## Wishlist

Capability improvements to revisit when supported, separate from the workflow
implementation tasks above:

- [ ] **Verified server-enforced session budgets.** Revisit Agents API
  `spend_control` support: the tested endpoint rejected the documented field as
  unsupported. Require acceptance, returned-limit confirmation and a bounded
  enforcement test before relying on it. See the
  [authorization and spending-control notes](adapters/openai-agents/authorization.md).
- [ ] **Per-request/production-task spending limits within a resumable episode
  session.** Bound a task without discarding conversation history or treating
  every feedback message as a new episode. Keep these limits additional to
  operator-controlled overall caps; neither controller nor executor should gain
  authority to raise/remove those caps. Timeouts and local estimates remain
  distinct from server-enforced dollar limits.
- [ ] **Least-privilege cost reporting.** Let the controller read actual costs for
  its project/tasks without a broad administrative credential or permission to
  change budgets. Distinguish delayed token estimates from billed amounts and
  report unknown usage honestly.

## Future operator/executor separation

- [ ] Explore an optional two-user setup. The operator could hold orchestration
  authority and make temporary pre-operation backups that the executor cannot
  overwrite or delete, protecting against accidental destructive actions. Define
  restoration, retention/cleanup, minimum grants and practical UX before adding
  this mode. The current supported runtime intentionally uses one `podcaster`
  Unix user for both roles; this TODO does not introduce sudo approval per task.
