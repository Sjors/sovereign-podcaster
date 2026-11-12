# Transcript review decisions

Keep `review.json` beside the selected episode's immutable recognition artifacts.
Use `tools/transcription_packet.py --folder DIR` for a compact summary, then
`--section flags|differences|gaps|cues --offset 0 --limit 20` for bounded pages.
`total`, `more` and the offset make omitted pages explicit. Read the complete
wording in `review.txt` and every final caption; a packet is not editorial review.
Use `transcribe.py inspect --folder DIR --start S --end E` for the indexed words
and both recognizers in a selected interval. Differences/gaps do not prove errors.
For complete final text without repeated JSON keys, use `--section cues --format
text --limit 100`, then offsets 100, 200, etc. Each line keeps the cue number,
millisecond times, complete speaker name and complete text; the header preserves
pagination metadata. Stop only when `more` is false.
For bounded recognition results use `--section evidence --evidence FILE.json`.
This keeps every segment's text and global times while omitting the much larger
raw word metadata. The source hash and pagination stay explicit. Inspect the
original evidence's word timings only where a correction actually needs them.

Minimal `review.json` shape (values below are placeholders):

```json
{
  "publication_ready": false,
  "primary_segments_sha256": "HASH_OF_THIS_EPISODES_PRIMARY_SEGMENTS_JSONL",
  "speaker_mapping": {"0": "IDENTIFIED_PARTICIPANT", "1": "OTHER_PARTICIPANT"},
  "word_corrections": [],
  "speaker_corrections": [],
  "timing_corrections": [],
  "replacement_spans": [],
  "word_insertions": []
}
```

Indices always refer to the original `words-for-review.json`, never indices
shifted by an earlier edit. Supply only reviewed decisions:

- Word edit: `{"word_index":12,"before":" original","after":" corrected","reason":"EVIDENCE"}`.
  `before` must match exactly, including leading spaces. Empty `after` removes
  that recognized word from the derivative without changing raw ASR.
- Speaker override: `{"start_word_index":12,"end_word_index":14,"speaker":"IDENTIFIED_PARTICIPANT","reason":"EVIDENCE"}`.
  End is exclusive; this edits original indices 12 and 13. Names must occur in
  the episode's reviewed mapping. Never inherit a previous episode's clusters.
- Timing edit: `{"word_index":12,"before":[1.2,1.4],"after":[1.25,1.45],"reason":"EVIDENCE"}`.
  Preserve the actual published clock. A recognition/model duration alone does
  not justify truncating or shifting the recording.
- Bounded replacement: `{"start_word_index":12,"end_word_index":14,"replaced_text_sha256":"HASH","words":[]}`.
  The hash binds the concatenated current word text **after word edits** in the
  exclusive span. Replacement words need `word`, `start`, `end`, `speaker`.
- Insertion: `{"word":" recovered","start":1.2,"end":1.5,"speaker":"IDENTIFIED_PARTICIPANT"}`.
  Insert only speech supported by the recording/evidence; do not invent missing
  transitions from what a technical argument ought to say.

The renderer applies word edits, mapping/overrides, timing, replacements and then
insertions. Render a preview while `publication_ready` is false. Review its
complete text, speaker turns, gaps and boundary timing, preserving uncertainty.
Record evidence and limits separately. Once actually ready, render the final
result and bind its exact audio/review/VTT hashes and cue count in
`review-verdict.json` as described in [the runbook](transcription.md). The renderer
and a successful parser check do not grant editorial or publication approval.
