# Background noise and a live audience

Use this section for live recordings; it is not the standard quiet-room chain.
Treat foreground voices, distracting distant chatter, intentional audience
atmosphere and PA echo as separate problems.

## Preserve the foreground while reducing chatter

Begin with the close microphones alone, centred and independently levelled.
Keep the room track down during ordinary conversation unless it contains useful
speech. A stereo audience mic is not automatically a usable cancellation reference:
different mic responses, positions, delays and PA speech pickup can damage the
main voice when subtracted or used in a spatial filter. Try it only as a bounded,
matched comparison and retain it only if listening supports an improvement.

Compare moderate, strong and stronger single-channel suppression on identical
speech, then on a second passage with different vowels, level and background.
Include a deliberately stronger stress test only to establish an artifact limit.
Check both hosts independently. Avoid treating a strength name as a portable
preset: it must be tied to the saved algorithm, profile and parameters.

In a reviewed experiment, the preferred suppression strength differed between
speakers. Stronger stress processing distorted the voice;
the stereo-reference experiment performed worse. The lesson is to select the
least aggressive version that achieves the listener's goal, not to apply those
host-specific choices automatically to another recording.

For reproducibility, that single-channel experiment used a 48 kHz STFT with
2048-sample windows, a 512-sample hop, smoothed attenuation and a noise spectrum
learned from inspected quiet intervals. Additional attenuation caps were 8 dB
for medium and 14 dB for strong, on top of a gentle baseline. These are historical
calibration details, not a ready-made filter: the exact estimator, smoothing,
profile and latency compensation also matter. Preserve a working implementation
and its source evidence rather than reconstructing a preset from the cap alone.

Level riding and mic selection can contribute more than heavier denoising.
The successful baseline combined slow per-speaker gain riding, mild 2:1 compression,
an approximately 80 Hz high-pass where suitable, gentle FFT reduction and soft
attenuation of the inactive mic. Its gain riding was bounded rather than lifting
every silence. Judge mic-distance changes across the episode, including any
recording-gain adjustment, without flattening every expressive emphasis.

## Add atmosphere deliberately

Use one explicitly planned room-track envelope for each chosen intro, applause,
outro or topic transition. Preserve stereo audience width while keeping the
hosts centred. Do not repeatedly trigger room fades from pauses, VAD, hesitations
or every return to a topic: this makes background chatter pulse in and out.

For a hesitant transition, fade the atmosphere in before the phrase introducing
the change, keep it through the hesitation, and fade it out once the new topic
has actually begun. If the conversation briefly reverts, do not repeat the same
fade cycle. Also audition a simpler transition so the listener can judge the idea
separately from an unusually hesitant example. Provide the requested context
around the entire envelope, not just the centre of the transition.

Applause may overlap speech. Mix it as an event with enough lead/release and
headroom; its boundary is not automatically an editorial cut. If the audience is
quiet at the start, there is no reason to manufacture opening applause or omit
the normal intro tune. Follow the user's episode-specific choice.

## PA echo and Q&A

Venue wireless mics amplified over speakers can introduce delayed speech into
the close microphones themselves. Muting the stereo room track cannot remove
that echo. Distinguish this from extra bleed introduced by opening another mic.
Compare any gentle dereverberation attempt with a matched untreated sample;
stop when there is no audible benefit or speech texture worsens. Do not sell
an inaudible change as a successful repair.

Inspect the question and follow-up across every track. The room mic may capture
an audience question or off-mic response better than a host mic. Restore that
short passage with local fades and suitable gain rather than raising the room
through the entire Q&A. Attribute an unestablished voice as an off-mic/audience
speaker, or ask a focused identity question when naming them matters.

Keep Q&A according to the user's content/permission decision. If the original
question is clear, redundant host repetition or mic/cable/stage logistics may
be cut when requested. Preserve the question, answer, amplified follow-up and
the context of short replies. Investigate a seemingly missing preceding remark
in the raw room channels before concluding that a reply must be removed.
