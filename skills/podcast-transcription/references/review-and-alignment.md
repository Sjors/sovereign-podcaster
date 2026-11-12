# Wording, speakers and timing

## Conversation evidence

Keep original recognition immutable. Store the episode's shownotes/roster, source checksum,
recognizer/model/settings and reviewed derivative with an explicit source timebase. Existing
local models are often sufficient; model downloads, repeated full recognition and additional
parallel jobs should solve a specific gap rather than duplicate completed work.

Compare suspect passages with enough surrounding dialogue to recover the turn and meaning.
An apparent technical error may be a real historical assertion. Preserve uncertainty and the
speaker's repairs (including an incorrect number followed by a correction) rather than
substituting a current explanation. Normalize spelling when the intended token is supported;
keep modern documentation used for name spelling separate from evidence of what was said.

Recognition can omit a quiet interjection or a complete source passage. Read all final cues
and inspect long recognition gaps, speaker changes inside coarse segments, tiny turns and
changed-cue neighbors. Cropped or slowed recognition can repeat boundary words; compare with
the full-context recording before adding a word, API name or extra restart. A low-energy or
no-recognition interval is not proof that speech is absent.

Use speaker models as episode-specific support. Build references from clear, uncontaminated
turns; check the question/response sequence and overlapping speakers, not just the nearest
embedding. Do not transfer cluster IDs, guests or numeric similarity thresholds across
recordings. Document brief-turn estimates as revisable instead of claiming phonetic certainty.

## Original-wording narration

Recover the actual script/source revision, preferably one preceding publication. If the
available merged article is newer, inspect draft/PR history or saved narration inputs. Keep
current-source differences explicit; do not assume a current page is the historical script.

Align complete source paragraphs to the final audio, investigating unmatched words, parenthetic
asides, headings, credits and long gaps. Compare alternative timing evidence where one pass
omits a passage; neither an ASR omission nor a low-energy gap authorizes dropping original text
or moving a paragraph after its first spoken word. Verify intro variants, date ordering and
AI disclosure against this recording instead of regenerating them from today's adapter.

Retain canonical spelling for intended technical terms despite synthetic pronunciation.
Preserve source mathematics and stateful/stateless distinctions; do not silently improve the
source while creating captions. Record genuinely unspoken or substituted material separately.

## Published clock

With separate host tracks, establish actual channel/speaker identity and shared
clock before merging recognition. Close microphones can still contain PA/other
speaker bleed; low energy or a muted final track does not prove an interjection
was absent from the original. Inspect room channels for contextually missing
questions/replies and use an honest off-mic label when attribution is unestablished.

For editorial cuts, retain original word IDs/times plus a piecewise source-to-final
sample map. Include music preroll, measured filter latency and the overlap length
of crossfades. Map from source coordinates, or compose successive revision maps;
do not repeatedly subtract approximate seconds from already retimed cues. Review
words intersecting a cut locally. Regenerate canonical chapters and video timing
from the same final clock. The editing skill documents this assembly workflow.

Distinguish the analysis derivative's rate/offset from the native recording's decoded sample
count. Cropped recognition times need their source offset added exactly once. Track assembly
padding, ad removals and gapless metadata explicitly; verify them against the final enclosure.
A JSON duration estimate is not an encoder-delay measurement or permission to remove EOF.

Check words at the opening, final spoken turn and original ending, around each cut/assembly
join, and at uncertain paragraph/turn boundaries. Use additional bounded checks where the
source and alignment disagree; avoid blanket retesting after evidence has already passed.
Preserve original full ending/metadata when the transcript operation changes text only.
