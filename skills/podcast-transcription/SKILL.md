---
name: podcast-transcription
description: Produce, review or correct timed podcast transcripts from existing conversation audio or narrated source text, including historical backfills, speaker attribution and published-audio alignment. Use castopod-publishing for hosting and read-thread-aloud for generating narration.
---

# Podcast transcription

Produce captions that represent the recording, with useful timing and honest uncertainty.
Keep recognition, source text, review decisions and the publication derivative separate.
Use [review-and-alignment.md](references/review-and-alignment.md) for wording, speakers,
source-text narration and timing checks. Use
[delivery-and-feedback.md](references/delivery-and-feedback.md) for publication and corrections.

For multitrack assembly, noise auditions or editorial cuts, use
[podcast-editing](../podcast-editing/SKILL.md). Keep original word coordinates and
stable IDs, map them through the actual sample-based edits, and propagate later
human corrections to native text, on-screen video text and uploaded captions.

## Resume the actual work

Read the selected episode's private task, source manifest, recognition outputs,
feedback state and publication receipts before starting. Instance-specific paths
and legacy coordination records belong in private configuration, outside this skill.
Current user instructions and verified receipts outrank historical pending labels.
Reuse verified attachments; an analysis exit or READY marker is not approval.
For this repository use [the transcription runbook](../../docs/transcription.md).
For a fresh, explicitly requested episode over Marmot, use
`tools/transcription_intake.py --instance INSTANCE --show SHOW --episode NUMBER`.
The paired instance path is `MARMOT_HOME/podcaster-instance.json`. This uses the
current authenticated message and configured source catalog, enrolling only the
selected cleared episode without sudo. Reuse any registered task/outputs on
resume. Prepare from its returned episode file and launch `transcript-analyze`
through `tools/jobs.py`; return while recognition runs and use its saved job
directory, never a transient tool-session ID. With `transcription_wakeups` enabled,
completed jobs and trusted question reactions resume this existing task
automatically. Do not tell the user to send "continue". On background wake-up,
reuse the saved task; it has no newly received text-message metadata to enroll.
Use the configured transcription venv for Whisper, NumPy and speaker checks;
system Python may provide only the standard library. Use
`tools/transcription_review.py` for clock evidence, bounded recognition and
same-episode speaker comparisons instead of generating one-off worker scripts.
Batch selected windows in one model load, save their evidence, and inspect it
after completion. Long bounded checks must use `tools/jobs.py` kinds
`transcript-recognize` / `transcript-speakers`; a tool's transient exec-session ID
does not survive this adapter stopping its executor at turn completion. Save the
durable job directory and return; inspect its terminal state/evidence before a
new continuation. Never restart an old worker solely to regain context.
Preserve raw full-episode recognition. The ordinary
`transcribe.py verify` checks exact rendered speaker paragraphs as well as cues;
consecutive cues from one speaker intentionally share a paragraph.
Use `tools/transcription_packet.py` for compact, paginated flags, model-difference
intervals, recognition gaps and final cues. Read
[the review schema](../../docs/transcript-review-schema.md) instead of reading the
renderer source to discover field names. Read all proposed/final text; a packet
does not replace that editorial step or justify automatic flag corrections.
Packet page limits are 1–100; use successive offsets to read all final cues.
Use `--section cues --format text` for compact complete cue text and times.
Correct routine read-only CLI argument mistakes locally using help; they are not
missing prerequisites requiring a maintainer. Inspect saved effects first if a
command may have written/published anything. Never change scope, bypass a guard,
or repeat an uncertain external action merely to clear an error.

Keep three controls distinct: a pause on new episode analysis/queuing, a production-write
pause, and an audio-quality hold. Finish already-running work only within the user's current
authorization. Never launch another episode merely because an old callback says to continue
backward. Check current pause markers before preparation, launch and notification side effects.
Do not restart a finished worker to recover context.

Identify the existing show, episode GUID, enclosure and publication date first. Historical
conversation captions and captions for an article read are separate deliverables on their
respective existing episodes. Preserve episode identities across feed migrations; consult
the project's identity record and current canonical feed rather than cached directory copies.
A show-level identity repair is not permission to change any episode GUID or merge copies.

If external-ad cleanup applies, require its reviewed final audio before final transcription.
An offline source audit and an approved deployed cut are different states. Do not caption a
pre-cut recording and later attach those times to the shorter enclosure. Preserve host reads,
and leave audio editing to its existing owner.

## Choose the source workflow

**Conversation:** transcribe what was actually said. Inspect any supplied separate tracks for
real speaker isolation before preferring them to the published mix, and retain a mapping to
the published timeline. Preserve historical claims, numbers, units, uncertainty, negatives,
self-corrections, jokes and disagreements. Technical knowledge helps detect suspect recognition;
it does not authorize repairing a speaker's argument, grammar or arithmetic.

**Narrated source:** use the actual article/forum/transcript wording, with Whisper or other
alignment evidence used for timing. Prefer saved script, chunk manifests and generation timing
when available. Pin the source URL/revision/hash and compare it with the narration; current
web text or current generator defaults may differ from the recording. Include the spoken
introduction, title, attribution and disclosure. Do not supply source passages that were never read.

Use the configured pronunciation glossary as a spelling/alias aid, not a
reversible substitution dictionary. Review contextual confusions such as music/MuSig, multisig/MuSig,
minor/miner and proper names. Speaker-specific pronunciation corrections require
source evidence and the operator's editorial policy. Apply these judgments to a
reviewed derivative, never overwrite raw ASR or change every matching word automatically.

## Review wording, speakers and time

Read the complete proposed display text. Investigate uncertain wording, missing passages,
long gaps, technical terms, numerical/negative repairs, short interruptions and overlap.
Use bounded checks on the affected recording rather than repeatedly transcribing whole episodes.
A second recognizer can reveal omissions; agreement, embeddings and slowed clips are evidence,
not ground truth. Retain a localized uncertainty marker when recovery is unsupported.

Infer participant names from this episode's notes/opening and the actual voices. Some episodes
have one host and a guest, so do not inherit participant names or a cluster-number mapping from a
neighboring recording. Use clean same-recording references and whole-turn context to review
brief turns. Ask about a genuinely unresolved participant name; distinguish that from a minor
uncertain interjection by an already identified participant.

Align against the final served recording from time zero. Establish the actual decoded native
sample clock and account for true encoder skip/discard, assembly or reviewed cuts. Stored
model duration, ffprobe duration and decoded EOF can differ; do not truncate the ending or
invent a caption offset to make them agree. Check opening, ending, transition boundaries and
representative middle passages, with special attention to gaps and cropped-ASR boundary shifts.

Keep a compact review record binding the final transcript, exact audio, speaker map, source
revision where relevant, timing evidence, corrections and unresolved limits. Record what was
actually reviewed; do not claim a complete manual listen, measured accuracy or a particular
player's uptake from automated checks.

## Deliver the reviewed result

An explicit request to transcribe and publish, including this repository's
`transcribe SHOW NUMBER` command, authorizes native publication after the agent's
editorial/source/timing checks. Do not ask the user to read or approve the whole
final transcript. Ask focused questions only where their input is needed, apply
the answer or permitted minor-wording fallback, then publish, verify and send the
link. Do not confuse the agent's `publication_ready` verdict with human sign-off
or import the separate Nostr/YouTube video approval stages into this task.

Use standard `<v Speaker Name>` voice spans for conversation speaker metadata. Do not insert
“Speaker:” into caption text to compensate for a player that fails to render the speaker field.
For a single-voice article/talk-note narration, group at the source's paragraph boundaries and
omit narrator speaker fields; keep intro/title/credits distinct. Genuine multi-participant
material still needs attribution appropriate to what was read.

Delegate native attachment to [castopod-publishing](../castopod-publishing/SKILL.md), with an
explicit show and the reviewed published-audio timebase. Validate through the actual installed
parser and every final public caption/paragraph, not just the raw VTT or a database success.
Inspect existing state after a failed readback before retrying; avoid duplicate uploads.

For sample feedback, use the user's authorized channel and the current shared question record.
When voice feedback is configured, send one voice memo followed by one clear text
question, identifying episode, timestamp, uncertainty and provisional interpretation, with useful surrounding audio (usually
about ten seconds). Use [marmot-whitenoise](../marmot-whitenoise/SKILL.md) for authorized private
transport; a send receipt does not establish phone visibility or playback.

Use a provisional answer or feedback deadline only when the operator has explicitly
authorized that policy for minor wording or brief attribution questions. Record the
configured deadline after an actual send, accept late corrections, and review them
against the audio. This is not timed approval for unknown identities, dropped content,
changed music or significant audio-quality tradeoffs. Do not repeat an answered
question or add a deadline to feedback on an already published decision unless
requested.
