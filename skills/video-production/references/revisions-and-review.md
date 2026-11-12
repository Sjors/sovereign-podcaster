# Episode revisions and approved video delivery

## Freeze the correct input revision

Read the selected episode's final audio, edit map, canonical chapters and current
native transcript before making the video packet. Later human transcript edits
and another chat's description-formatting repair outrank stale generated files.
Record their hashes and preserve exact corrections, especially opening/closing
jokes, proper names and resolved uncertainty. Keep the native transcript,
burned-in text and uploaded caption track consistent. Updating VTT alone does
not repair already rendered pixels.

The source, edited audio, video and caption clocks must agree. Retain word/cue IDs
and account for preroll, removed spans, fade overlaps and measured processing
delay. Do not manufacture a global subtitle offset to conceal a missed local cut.
Review opening, representative middle passages, chapter boundaries, Q&A and EOF.

Respect source-display versus source-link instructions separately. For a page the
user wants shown without linking, suppress the displayed URL and public description
link, while retaining the source privately for provenance. Use only screenshots of
existing sources for technical slides. Do not replace a
capture with agent-written explanations, summaries, bullets or diagrams. Preserve
source wording and context; only neutral headings and actual reviewed speech
captions accompany the capture. See the production runbook's source-screenshot
policy, including the episode-99 failure and accepted example.
Match the approved event/location wording across thumbnail and descriptions.

## Revise efficiently without changing approved audio

For text-only changes, keep the audio and unaffected video intact when the format
permits. A GOP-aligned patch can limit re-encoding, but only when keyframe boundaries,
timestamps, codec parameters and joins are verified. Compare compressed audio
packets throughout and video packets outside changed ranges. Fully decode changed
deliveries, inspect the corrected frames and verify MP4/player timing and seeking.
If that cannot be established, use the maintained full render rather than an
unverified concatenation. Do not claim byte preservation from a sampled screenshot.

Keep each revision immutable with a current pointer and a clear receipt of what
changed. Distinguish the 480p AV1 review/fallback, the native HLS ladder and the
1080p YouTube master. Explain a preview's resolution when asked; approval of its
content can cover the corresponding verified master rather than requiring another
identical-content render review solely for a higher resolution.

## Approval and publication handoff

Before the final publication offer, upload the complete registered 480p fallback
as a tracked Blossom draft, using the selected episode authorization and the
`draft-upload` maintenance control. `reviews.py` requires its matching full-byte,
MIME, CORS and range-read receipts and rechecks the `.mp4` link before sending.
The offer starts with the full-preview link and clearly states Nostr/Nostube,
Castopod, YouTube and announcement actions. Keep focused question clips encrypted;
they do not substitute for a full final preview. The temporary preview link is
accessible to anyone who has it. Nostr events and YouTube publication still wait
for the corresponding approval. Keep technical hashes and destination evidence
in saved review state, rather than filling the phone message with them.

Bind the actual approval to the exact selected files and destinations. An explicit
human approval in trusted desktop chat is not an authenticated Marmot message.
In sovereign-podcaster, the local operator path is `tools/reviews_operator.py`;
save the actual human instruction/context and both manifests/configuration digest.
Keep normal Marmot reviews unchanged. Do not fabricate sender/group/message IDs.

When the user already authorized full public release of this approved packet,
inspect the resulting private YouTube ID and bind that same authorization to it.
Do not require another human approval merely because the ID did not exist when
they authorized release. A pending private-video review explicitly requested by
the user is different and must still be honored. Changed editorial content or
destinations need scope review; inspection is not a new blanket authorization.

Follow the requested effect order. Where Castopod must sit between native video
and announcement, use separate native and announcement phases; do not let a
combined publisher announce early. On compatible tooling, `publish.py nostr
--nostr-phase video` saves native readback, then the matching verified Castopod
linkage receipt gates `--nostr-phase announcement --castopod-receipt RECEIPT`.
The complete Nostr receipt precedes private YouTube upload and exact-ID release.

Retain separate storage, relay, Castopod, private inspection and public verification
evidence. Resume the incomplete effect, preserving IDs and earlier receipts.
Keep failure reports private, restore the prior operational control after the
authorized run, and mark current pointers published only after public verification.
Use the Nostr and YouTube publishing skills for transport-specific recovery.
