# Cuts, joins and transcript clocks

Keep three identities explicit: original recording, approved parent mix and new
delivery. Store stable word/cue IDs and original source coordinates even after
the displayed timestamps change. Use integer sample frames at a stated rate
for edit decisions; source rates and working/delivery rates may differ.

Express the simple mapping below at one common sample rate. If keeping native
coordinates across a resample, include the explicit rate ratio and rounding
policy: `destination_in + (source_position - source_in) * destination_rate /
source_rate`. Keep the original native coordinates as provenance alongside the
working-rate map; never add 96 kHz source frames directly to 48 kHz output frames.

Represent retained spans by `[source_in, source_out)` and `destination_in`.
For material wholly inside one retained span:

```
destination = destination_in + source_position - source_in
```

Apply the same mapping to word starts/ends, turns, chapter starts and slide/source
events. Added music preroll is part of the destination clock. A cropped recognizer
window's source offset must be applied exactly once before this mapping.

Crossfades overlap samples: with a fade of X frames, the following span begins
X frames before the preceding span ends. Removing D frames and adding that
overlap shortens the mix by D + X frames. Do not retime by the nominal removed
duration alone. The actual render/sample count is authoritative. A word touching
the removal or overlap needs local review/alignment, not blind timestamp clipping.

For a cut made to an already edited parent, save the parent-to-new map and compose
it with the original-to-parent map, or explicitly record both. Never mistake an
approximate player timestamp in the user's request for an original recorder
timestamp. Locate the actual words and label both clocks in the proposed edit.

Cut at conversationally appropriate boundaries, preserving consonants, speech
releases and room continuity. A short equal-power crossfade can smooth a join;
40 ms worked on the reviewed logistics cut, but is not a universal speech-splice
length. Audition the join with context and check that the fade does not overlap
unrelated syllables or duplicate a word. Inserted-ad lossless frame splicing has
different requirements; use that workflow rather than applying PCM assumptions.

Processing can shift audio without changing its nominal duration. Measure and
compensate actual denoiser/limiter latency before deriving final timestamps.
For example, one reviewed FFT chain required 25 ms compensation; do not impose
that offset on other chains. Final encoded clocks must account for their actual
encoder skip/discard metadata rather than a generic MP3/AAC delay.

Validate the first spoken words, music entry cue, both sides of each join,
representative middle passages, Q&A and the final spoken turn against the final
decoded delivery. Check for cues accidentally left in removed material, dropped
quiet interjections, duplicated boundary words, non-increasing times and captions
past decoded EOF. Preserve honest localized uncertainty and uncertain attribution.

Human text corrections can leave cue times unchanged when the audio did not
change. Carry them to the authoritative reviewed text and every derived surface:
native VTT/JSON, rendered transcript, burned-in video and uploaded captions. Keep
raw recognition as provenance. If another chat edited the native transcript,
retrieve and compare the latest public text/hash before rendering a video.

Derive final chapters from the edited clock. Castopod Markdown and YouTube plain
text need separate formatting derivatives of the same canonical chapter JSON;
do not maintain independent editorial chapter lists. Check actual rendered
chapter line breaks as well as words and timestamps.
