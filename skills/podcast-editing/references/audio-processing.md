# Ordinary audio processing and review

## Quieter recordings are the default

Start by listening and measuring each host on representative quiet/loud turns.
Use the least processing that solves an audible problem. Do not inherit a live
conference's noise profile, gain curve or denoising strength. Clean close-mic
recordings may need only balance, modest dynamics and a final level adjustment.

Distinguish slow changes caused by microphone distance or recording gain from
short peaks. Ride each speaker's gain smoothly over speech; use gentle compression
for remaining dynamics. Avoid raising the noise floor during pauses to meet a
speech target. Check both earlier and later turns when recording gain changed.
In overlap, preserve both people; speech-aware attenuation of an idle mic must
hold through quiet interjections rather than behaving as a hard gate.

Apply rumble filtering only as needed for that voice. Learn any noise profile
from inspected non-speech intervals; ASR gaps alone do not identify silence.
Keep tone, consonants, breath releases and natural room continuity when judging
denoising. Do not automatically declip full-scale samples or delete a measured
transient. Present a candidate for listening when its perceptual impact is uncertain.

Use an episode-wide output calibration. For a speaker-level comparison, retain
the natural quiet/loud difference inside each version and match each whole A/B
sequence; independently normalizing its passages conceals the problem being tested.
Existing show targets take precedence. Around -16 LUFS stereo with encoded
true-peak headroom worked for the reviewed live master; this is an example, not
a required target for every show or format. Recheck the encoded peaks after MP3/AAC.

## Useful samples

When reviewing a complete processing approach, offer the requested opening,
one minute from a representative topic, about 30 seconds spanning middle applause,
and the last roughly 30 seconds plus applause. These are useful starting windows,
not a requirement for an episode without applause. Include original-source and
edited-output positions, actual clip duration, processing variant and what to
listen for. If programme sign-off precedes Q&A, distinguish those two endings.

For a suspected defect, use a short contextual A/B with matched overall loudness.
Keep room fades identical when comparing a host-mic filter; isolate one changed
variable. A “reference” with gain balance or limiting is an audition mix, not
an untouched original. State that distinction. Also audition filter choices in
the programme mix so a good solo result does not mask the other speaker.

When requested, give transition reviews at least 15 seconds before the fade begins
and 15 seconds after it ends. Record clipped/EOF-limited lengths accurately;
do not label a 29-second ending as an actual 30-second decode.

## Render continuity

Run stateful filters continuously or with adequate discarded context. For STFT
processing, align retained blocks to the hop clock and use correct overlap-add
normalization; splitting into arbitrary independent clips can change the noise
texture, latency and level at every block boundary. Measure latency on real
voiced material. Do not reuse one filter's measured delay for another chain.

Keep processing deterministic and bounded. Save settings, input hashes, source
windows, output hashes and measured latency. Use existing maintained tools where
available. Long renders should have durable job state, logs and resumable results;
a lost tool session is not a reason to rerun a finished render.

For a later small edit, compare retained PCM with the approved parent outside
the explicitly changed join/restoration windows. This is strong evidence that
the rest of the episode and its accepted processing were preserved. Decode the
actual delivery and validate its native sample clock, including codec skip/discard.
