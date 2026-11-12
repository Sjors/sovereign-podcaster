# Finished episode notes, chapters and video linkage

## Final audio and concise notes

Bind the selected show, episode/GUID, enclosure and final audio hash before
deriving timestamps. Retain one canonical Podcasting 2.0 chapter JSON and derive
the website/description and video versions from it. For Bitcoin, Explained,
follow its maintained chapter policy (normally 3–10 chapters for a full episode).
Verify boundaries against the actual edited recording, including any music preroll,
cuts and crossfades. A source-clock transcript is not yet a final-clock chapter list.

When chapters already enumerate the content, keep the episode introduction brief.
Include the requested release announcement, security-policy post and primary PR
links; use release notes to identify the actual changes discussed, verifying the
links rather than guessing PR numbers from ASR. A supplied source page can be
for display only: respect an explicit “show it, but don't link” instruction in
all public descriptions as well as the video itself.

## Check chapter line breaks in the rendered product

A plain newline between Markdown timestamp rows can become a space in Castopod's
HTML, making the chapters appear as one paragraph. A single observed incident
does not imply that all historical descriptions are broken. Check the selected
episode's actual rendering, especially when notes were assembled outside the
canonical chapter renderer.

Use a supported Markdown hard break between chapter rows, such as two literal
spaces followed by a real newline, and a blank paragraph after the complete
chapter block before the contact/sponsor footer. Keep a blank line after the
heading. The maintained sovereign-podcaster chapter renderer already emits hard
breaks; reuse it where applicable rather than repairing its output by hand.
Do not publish a backslash-n string, escaped HTML comment markers or a block of
internal chapter delimiters as visible notes. Preserve intentional trailing
spaces; indiscriminate whitespace stripping removes Markdown hard breaks.

Inspect both the public page DOM and the RSS description HTML. Check that each
chapter has a rendered break and that the following paragraph/footer is separated.
A whitespace-normalized “all titles occur” check can pass even when every row
has collapsed together. Keep canonical JSON timings unchanged for a formatting-only
repair. YouTube descriptions are a separate plain-text derivative with actual
newlines and complete HTTPS links, not Markdown links or trailing-space markup.

## Reuse current text rather than stale derivatives

Read the current native transcript and description immediately before generating
video metadata/captions or making an update. Another chat may have repaired chapter
formatting or the user may have corrected a pun, proper name or uncertain word.
Keep those edits and propagate the authoritative wording to on-screen text and
YouTube captions. A transcript wording repair does not change audio or its clock.
Preserve stable cue IDs/times unless alignment evidence requires changing them.

Use conditional updates/current snapshots where supported. Compare native fields,
audio identity, transcript, chapters and unrelated notes before/after the scoped
operation. A stale local description must not undo a user's newer correction.

## Link a verified native video

If the user requests native video → Castopod link → kind-1 announcement → YouTube,
keep those external effects separate. Update Castopod only after the native event
and media are verified; announce after the matching Castopod link is verified.
This order is an episode instruction, not a new universal publication policy.

Use the installed episode-video interface when present. On a compatible instance,
`episodes:video --podcast HANDLE --slug SLUG --identifier NADDR` sets a contextual
video identifier without replacing the audio episode. Inspect the installed
command/configuration before using it; do not assume every Castopod has this patch
or change application/schema merely to run an episode task. Preserve and compare
the original identifier and episode fields, including GUID/pubDate/enclosure.

An iframe's slashes and query delimiters may be HTML-entity escaped. Parse the DOM
or decode entities before comparing its native identifier and `/video/` URL;
failure of a raw substring check is not evidence that the database update failed.
Inspect the existing setting before any retry. Verify the public tab/iframe and
actual player playback, not only the CLI response. Record a verified linkage
receipt bound to the same native event, stable address and episode URL.
