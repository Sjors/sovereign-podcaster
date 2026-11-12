---
name: podcast-editing
description: Edit selected podcast recordings, balance speakers, audition audio cleanup, assemble intro and room audio, and retime transcripts after cuts. Use for episode audio production and revisions; use podcast-ad-cutting for inserted external ads and publishing skills for hosting.
---

# Podcast editing

Produce the episode the user wants while preserving the original recordings,
natural conversation and a reproducible edit history. For Bitcoin, Explained,
the usual edit is modest: remove pre/post-recording chat and selected logistics,
with occasional distracting overlap or excessive pauses. Do not automatically
remove every hesitation, breath, silence or instance of crosstalk.

## Establish the source and current decisions

Select the episode explicitly. Read its current source hashes, track/channel
map, edit plan, feedback and latest outputs before starting a new revision.
Keep recordings, profiles, media, credentials and session evidence outside Git.
Retain immutable originals and previous approved mixes; render selected copies.
Do not let an older plan overrule a later choice about music, Q&A or wording.

Inspect each track's channels, rate, decoded length, offset and actual speaker.
Separate host microphones make attribution easier but can still contain bleed,
PA pickup and overlapping speech. Verify synchronization and check for drift
before combining recordings from different devices. Retain a stereo ambience
track separately from the centred close microphones.

Use [podcast-transcription](../podcast-transcription/SKILL.md) for transcript
recognition/review. An early source-clock transcript is useful for editing;
label it provisional until it is mapped to the final mix. External-ad removal
has additional codec/source requirements in `podcast-ad-cutting`, when available.

## Process and audition before committing cuts

The normal recording setup is quieter than a conference. Read
[audio-processing.md](references/audio-processing.md) for ordinary speaker
balance, conservative cleanup and meaningful comparison clips. Read the separate
[live-audience.md](references/live-audience.md) only for venue noise, hallway
chatter, PA echo and intentionally audible audience reactions.

Keep processing choices separate from editorial removals. Save per-speaker
settings and the actual audition windows. Use loudness-matched comparisons and
another speech passage before adopting a stronger filter. A measurement can
identify a listening candidate; it does not establish that a sound is objectionable.
Respect a user's judgment that a thump is harmless or an echo trial is inaudible.

Send samples by the user's selected channel. In desktop chat, local audio can
be played inline with an absolute path; do not route it through White Noise
when local playback was requested. When encrypted Marmot delivery is selected,
use that skill's attachment workflow and shared feedback records.

## Assemble the programme and preserve its clock

Store an edit decision list with source sample ranges, destination sample
positions, fades, music offsets and processing latency. Read
[edit-timeline.md](references/edit-timeline.md) before applying or retiming cuts.
Do not repeatedly subtract approximate seconds from an already retimed transcript.

Judge intro timing by the onset of the requested spoken word, alongside the
music, rather than the start of a coarse ASR segment. A request for a longer
quiet music tail changes its bed/fade, not the accepted voice entry. Extend or
loop music only where a clean join is possible; never repeat or stretch dialogue
to lengthen the bed. Intro/outro choices remain episode-specific.

If a reply loses its context, inspect every original track and the current
gain/mute envelopes before cutting it. A quiet interjection may exist on the
room recording even when absent from the close-mic mix. Recover supported speech
locally when requested; otherwise propose the small contextual cut. Do not
attribute an off-mic speaker merely because a host was expected to respond.

## Deliver a reproducible revision

Work from lossless audio and encode the delivery once. Verify the decoded final
sample count, joins, opening/ending, loudness and encoded true peaks. Compensate
measured filter/limiter latency, preserve speech releases and check the encoded
result rather than only the PCM illustration. Keep lossless masters and an
exact source-to-final clock map alongside the delivery file and its hash.

Retime words, speaker turns and canonical chapters using that map. Propagate
later human wording corrections to the native transcript, burned-in video text
and YouTube captions; text-only changes need no invented audio offset. Fetch
the current native transcript if another chat or the user has edited it.

Audio-editing authorization does not itself publish a replacement. Hand finished
audio and its reviewed timed transcript to
[castopod-publishing](../castopod-publishing/SKILL.md), and video work to the
available video-production workflow, under the user's actual publication scope.
