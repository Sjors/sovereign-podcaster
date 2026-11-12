# Local transcription and native transcript publication

## Request from White Noise

In the paired podcast group, select the configured podcast workspace if needed,
then send `transcribe SHOW NUMBER`. This selects/creates
the local episode context and requests local Whisper transcription, review,
focused voice-sample feedback when needed, and publication/verification of the
native transcript. Original audio and unrelated hosting fields are preserved.
Repeat the command to resume saved work; it does not create another copy or
silently authorize other episodes. The backend verifies and records the trusted
incoming message before enrolling the selected source. No video/Nostr/YouTube
publication is implied. No full-transcript human approval is required: the agent
reviews the complete text, asks focused questions only if needed, then publishes,
verifies and sends the link. `publication_ready` is its editorial verdict, not
human sign-off. The equivalent longer new/use-plus-instructions flow
still works for users who want to vary the task.

Replace SHOW and NUMBER with your configured show and selected episode. No episode starts merely because a source is listed as cleared.
The configured private `source_catalog` supplies audited GUID/audio hashes and
feed metadata. Other operators import their own source clearances; credentials
and private audit/chat histories do not belong in that catalog or Git.

For a new selected transcript task, the agent runs `tools/transcription_intake.py
--instance INSTANCE --show SHOW --episode NUMBER`. It verifies the actual current
trusted Marmot message and selected episode, records that authorization, enrolls
only the selected cleared source in user-maintained configuration, and registers
the episode's transcript directory/task. It grants no unrelated publication.
Use its returned episode JSON with `transcribe.py prepare`, then a durable
`transcript-analyze` job with string parameters `config`, `folder`, `clusters`.
That job uses the configured local venv and low CPU priority. Return while it
runs; successful internal job completions stay in saved state. Enable the handoff watcher below so
completed jobs resume review automatically. No manual `continue` is needed with
that service enabled. Normal feedback replies resume automatically.

## Chat notifications

With automatic handoffs enabled, a new `transcribe SHOW NUMBER` task gets one
short acknowledgement, focused voice questions only when input is needed, and a
final result after native publication has been verified (including the configured
cost estimate). A blocked task sends its private-report UUID. Successful Whisper,
wording and speaker jobs and intermediate resumed model turns send no progress
messages. Their outputs and full model answers remain in local state for diagnosis.
Use `podcast status` for an explicit progress request; idle waiting uses no model.
A feedback tool sends its own sample/question, so do not add another standalone
"question sent" update. Replies to ordinary user questions still work normally.
Successful turns that need no separate reply emit the bridge's explicit silent
completion event; keep the adapter and [patched bridge](../adapters/marmot/message-context.md)
compatible. A genuinely missing backend reply still produces a diagnostic.
Ordinary follow-ups during active review steer that API turn when
`followup_steering` is enabled. A quick correction need not wait for another model
turn, and the bridge suppresses its duplicate queued delivery. Replies arriving
after work has finished still use the normal continuation path.
The completion gate checks the receipt's source GUID and exact VTT hash; a model
claiming to be done cannot pass it by itself. Existing pending/uncertain transport
intents remain immutable and require inspection rather than silent replacement.
Standalone jobs without automatic transcript handoffs retain their completion
notifications. No production work is rerun merely to change notification policy.

## Completion tracking and queue ownership

The isolated account owns the authoritative episode journal, job states, review
verdicts, transport receipts and public-verification records. Successful
`transcribe.py publish` / `verify` writes `publication/verification.json` itself,
binding the episode GUID and exact VTT hash. No maintainer action or chat message
is needed to mark that transcript completed. `episodes` and `podcast status` read
these local records; repeating `transcribe SHOW NUMBER` for a verified transcript
returns its publication link without another model call, recognition or upload.
A missing or inconsistent receipt requires inspection rather than guessing or
silently repeating a publication.

Keep legacy migration queues paused unless separately authorized. Before
resuming an older harness, reconcile its remaining targets against authoritative
publication receipts or current native attachments. Do not maintain two live
queues or grant access to another user's directories for synchronization.

## Automatic job and thumbs-up handoffs

Administrator dependencies:

```sh
sudo apt install --no-install-recommends python3 systemd
```

After configuring transcription, run as the isolated user from this checkout:

```sh
python3 adapters/openai-agents/install-wakeups.py \
  --instance "$MARMOT_HOME/podcaster-instance.json"
systemctl --user status sovereign-podcaster-wakeups.service
```

This starts a separate same-user service; it does not stop or restart the existing
agent, connector or recognition workers. Its five-second loop reads local job and
question state. With no pending question it makes no connector queries; no OpenAI
credential is read and no model call is made until a new eligible event exists.
Completed transcript jobs and trusted thumbs-up reactions resume the original
episode's existing API session. Job-triggered continuation waits for that episode's
queued/running transcript checks to settle and coalesces their completions, so
fast speaker checks do not generate repeated model turns while wording checks run.
The response returns to the original paired group without changing the selected
episode. Current transcript questions block job-triggered review until answered.

Reactions are checked against the connector's materialized target, actor and event
ID. A thumbs-up answers that exact transcript question, not video publication
approval. A withdrawn queued reaction is suppressed; send a text correction if
work has already started. A newer processed human reply supersedes an older
reaction. Untrusted reactions and reactions to other messages do not wake a model.

Durable `state_root/wakeups/batch-*.json` records bind events, session, prompt and
delivery. Replays cannot resubmit completed input. Busy sessions defer; uncertain
input or delivery stops that batch with a private UUID report for inspection.
Jobs for verified published transcripts never reopen production. Use
`wakeups.py --instance INSTANCE --once` for a bounded processing pass (it can run
eligible work); inspect private receipts/service status for read-only diagnostics.
Custom job roots can be listed in `transcription_job_roots`; normal roots are
`work_root/jobs`, the episode's `jobs` directory and its transcript's `jobs`.

Use the final served audio of an explicitly selected existing episode. This port
reuses the working local faster-whisper primary/secondary and sherpa-onnx anonymous
diarization workflow. It adds no OpenAI transcription service. External-ad cleanup
is a prerequisite when applicable, not an operation implemented here. A clearance
must bind the exact final served audio hash; held/pre-cut recordings cannot be
published with final-audio timestamps. Keep the legacy queue paused while testing
a separately authorized limited episode set.

The reusable `podcast-transcription` skill contains wording, speaker, clock and
feedback lessons from the working backfill. Read it before review. Preserve literal
historical assertions, corrections, uncertainty, all source audio and existing
GUID/pubDate/enclosure/notes/video. Recognition, review decisions and final captions
are separate artifacts. Raw ASR and READY markers are never publication approval.
Use [the review packet and decision schema](transcript-review-schema.md) to avoid
dumping full metadata files or reverse-engineering renderer internals per episode.

## Isolated runtime and model access

Tested on Ubuntu 26.04.1 with the existing Python **3.11.17** runtime. Administrator
packages:

```sh
sudo apt install --no-install-recommends \
  python3 python3-venv ffmpeg libsndfile1 libgomp1 openssh-client \
  ca-certificates coreutils util-linux
```

Create a dedicated venv under the isolated account and install
`skills/podcast-transcription/requirements.txt`. Use an account-owned Python
installation without another user's venv or shared SSH agent. Models may be copied as explicitly selected, checksum-verified
nonsecret files, or downloaded under their original licenses into that account.
Do not grant access to the maintainer's home, chat/auth history or model cache.
Whisper model code/weights, converted models and sherpa/pyannote/TitaNet retain
upstream licensing; no model weights are distributed in this repository.
Record source repositories/revisions and file hashes privately.
The [tested model catalog](transcription-models.json) records public source
revisions, deployed hashes and upstream model-card licenses separately from code.
The turbo conversion's former Mobius Labs URL now redirects to Dropbox's model
repository; its pinned revision and deployed files were checked against that
public source. Preserve the converted segmentation package's MIT notice and the
upstream NVIDIA TitaNet attribution under CC-BY-4.0. No weights are included.

For fresh Whisper downloads use `huggingface_hub.snapshot_download` from the
transcription venv, an explicit catalog `repo_id` and `revision`, `token=False`,
and a private `local_dir`. Allow only the catalog's model/config/tokenizer files
and retain upstream notices/model cards. Fetch converted segmentation and
`nemo_en_titanet_large.onnx` through the linked sherpa-onnx release instructions;
check their recorded SHA256 values and retain the package license. Release tags
can change: a matching filename is not evidence of matching model bytes. Access
to the original gated pyannote repository follows that upstream's own terms;
do not copy another account's Hugging Face credentials.

For a fresh isolated account, from its repository checkout (no sudo):

```sh
umask 077
SP_RUNTIME="$HOME/.local/share/sovereign-podcaster"
python3 -m venv "$SP_RUNTIME/bootstrap-venv"
"$SP_RUNTIME/bootstrap-venv/bin/python" -m pip install 'uv==0.13.1'
export UV_PYTHON_INSTALL_DIR="$SP_RUNTIME/python"
"$SP_RUNTIME/bootstrap-venv/bin/uv" python install 3.11.17
"$SP_RUNTIME/bootstrap-venv/bin/uv" venv --python 3.11.17 \
  "$SP_RUNTIME/transcription-venv"
"$SP_RUNTIME/bootstrap-venv/bin/uv" pip install \
  --python "$SP_RUNTIME/transcription-venv/bin/python" \
  -r skills/podcast-transcription/requirements.txt
TRANSCRIPTION_PYTHON="$SP_RUNTIME/transcription-venv/bin/python"
```

Reuse an existing validated bootstrap/runtime instead of replacing it. The tested
versions above are independent of the system Python; this installs no chat login
or OpenAI transcription client. Supply separately licensed local model files and
fill in [the private configuration example](../examples/transcription.json).

Private configuration supplies `primary_model`, `secondary_model`,
`segmentation_model`, `embedding_model`, `glossary`, `cpu_threads`,
`castopod_config`, `feed`, `show`, `paused:false`, and an `episodes` object keyed by
GUID. Each explicitly authorized episode has `number`, `final_audio_sha256`,
clearance provenance and `force_feedback`. Messaging uses the paired instance's
`marmot_home`, `account_id_hex`, `group_id_hex`, `trusted_hex` and `feedback_root`.
The example paths below are placeholders, not another account's grants.

## One operator/executor account and maintenance state

The supported setup uses the same isolated Linux user for the operator/controller
and executor. The operator follows the user's authorization and directory rules;
it does not seek sudo approval for each show/episode/detail. Configure the
Castopod client's `maintenance_pause` as a private, user-owned JSON file, for
example `~/.config/sovereign-podcaster/maintenance.json` with `{"paused":false}`
when updates have been authorized. Set `paused:true` when the user pauses writes.
Missing/malformed state still stops the helper. This is an operational control,
not a security boundary against code running under that same UID. Do not change
it merely to get past a pause. Target/GUID/source checks, receipts and episode
locks protect against routine mistakes and ambiguous retries.

New users must arrange and verify the [operational backstops](backstops.md):
provider usage/budget controls where supported, hosting-machine system backups,
offline original audio, and recoverable copies of this repository and private
configuration/state. The server-enforced per-task token/spending limit remains a
TODO; local timeouts and a billing estimate do not implement it.

The earlier `/etc/sovereign-podcaster/castopod-transcription-experiment.json`
allowlist was an unnecessary root approval layer. It is no longer the runtime
control or a setup requirement. No sudo installation is needed for ordinary
transcript operation. Initial OS/account provisioning still needs an administrator.

Install the complete reviewed PHP helper cohort in a new versioned directory
over the isolated account's existing SSH access. Lint/check hashes before setting
its Castopod `cli` path. Preserve the active legacy cohort for the other workflow.
This is a helper deployment, not a Castopod application upgrade or audio/identity
edit. Before authorized attachment, recheck the actual parser and final served
audio; verify every public caption, feed and episode identity afterward.

## Resumable stage commands

`tools/transcribe.py --config CONFIG` provides:

- `prepare --episode EPISODE.json --folder NEW_DIR`: checks the canonical feed,
  native episode/GUID and absence of an existing transcript; fetches/hash-checks
  final audio; decodes native PCM and derives 16k recognition audio with saved clocks.
- `analyze --folder DIR --clusters N`: uses local primary/secondary recognition,
  episode-specific anonymous diarization, comparisons/flags and review text.
  Run as a detached bounded process; never restart a failed/finished worker to
  recover its context. Saved markers and locks distinguish waiting/review from approval.
- `inspect --folder DIR --start SECONDS --end SECONDS`: returns bounded primary,
  secondary and indexed word evidence rather than rereading enormous histories.
- `render --folder DIR [--preview]`: applies explicitly reviewed word/speaker/time
  corrections and renders the existing parser-compatible voice-span derivative.
  A preview is not approval. Review all final cues and bind the exact source,
  review JSON and VTT hashes in `review-verdict.json` before publishing.
- `publish --folder DIR [--apply]`: checks review/source/feedback gates, the actual
  installed parser, native identity and final audio, then uses the locked,
  receipt-driven Castopod update. Default is a plan. `verify --folder DIR` checks
  the recorded/public result without attaching again.

`review.json` follows the established word correction/speaker mapping schema;
see `tools/captions.py`. The verdict requires `publication_ready:true`,
`no_unresolved_actual_participant_names:true`, `source_audio_sha256`,
`review_sha256`, `vtt_sha256` and `cue_count`. Keep detailed review evidence and
limits beside it. It records actual editorial work, not independently measured
accuracy or a full manual listen that never occurred.

Use the configured transcription venv for bounded evidence (system Python need
not contain NumPy/Whisper):

```sh
"$TRANSCRIPTION_PYTHON" tools/transcription_review.py --config CONFIG \
  --folder EPISODE_DIR --out NEW_EVIDENCE.json clock
"$TRANSCRIPTION_PYTHON" tools/transcription_review.py --config CONFIG \
  --folder EPISODE_DIR --out NEW_EVIDENCE.json recognize \
  --model secondary --windows WINDOWS.json
"$TRANSCRIPTION_PYTHON" tools/transcription_review.py --config CONFIG \
  --folder EPISODE_DIR --out NEW_EVIDENCE.json speakers \
  --references REFERENCES.json --windows WINDOWS.json
```

`WINDOWS.json` is a list such as `[{"start":12,"end":22,"reason":"brief reply"}]`;
each window is at most 90 seconds and within the final recording. References map
episode-specific names/labels to lists in that same format. Choose clean reference
turns from this recording after identifying the participants. All selected windows
share one model load. Output paths must be new; raw ASR and older evidence survive.
These commands provide supporting evidence, not automatic editorial decisions.
For work that outlives an API turn, use the existing durable job runner:
`jobs.py start --root PRIVATE_JOBS --id STABLE_ID --request REQUEST.json`.
`transcript-recognize` parameters are `config`, `folder`, `out`, `windows`, `model`;
`transcript-speakers` replaces `model` with `references`. Paths are absolute and
the configured transcription Python is used. Optional `notify` supplies the same
private Marmot `home`, `account`, `group` as other jobs. Inspect with
`jobs.py status --job JOB_DIRECTORY`; reusing a job ID never starts a second worker.
The worker detaches from the executor, saves its result/exit status and can send
a token-free completion/failure notice. A harness exec-session ID alone is not a
durable job: this adapter stops that executor when its model turn ends. Continue
only after the saved job is terminal; do not use model calls to poll it.
The clock command explicitly selects the audio stream's first packet, avoiding
attached cover-art packets. Public page verification compares ordered paragraphs
grouped by speaker: a paragraph per cue is not the installed Castopod behavior.

## Voice feedback without idle inference

Create a private question JSON with `start`, optional `duration` (3–30 seconds),
`question`, `provisional`, `minor` and optional `test_required`. Then run:

```sh
python3 tools/transcription_feedback.py --config CONFIG send \
  --folder EPISODE_DIR --question QUESTION.json
```

The helper sends one encrypted AAC voice sample, then its own text question,
registering the exact episode/source/clip hashes, question ID and send receipts.
Do not invent uncertainty for a required transport test: mark it `test_required`
and ask a genuine small wording/attribution check. Pending sends cannot be retried
under a new identity. Only one live question is allowed at a time. Return the agent
turn immediately after asking; do not spend model tokens polling a person.

Incoming authenticated Marmot messages are recorded in the shared question state
as `reply-received`, not automatically `answered`. Read the actual reply before
classifying it. A request for a longer clip, preceding audio or an explanation is
continued conversation, not confirmation or a missing-input failure. Send the
requested context through the existing encrypted attachment helper, preserving
the original question and its receipts; do not ask the original question again.
Classify the exact saved text reply with:

```sh
python3 tools/transcription_feedback.py --config CONFIG classify \
  --question-id QUESTION_ID --reply-id MESSAGE_ID --kind context
```

Use `--kind answer` only when that reply actually supplies wording, attribution
or confirmation. Classification is bound to the current authenticated reply;
never classify a stale reply after newer input. These are internal saved IDs,
not strings the user must type. Context classification keeps the question open
and suspends its minor-wording deadline. Supplying context and waiting for the
answer is ordinary feedback, not a reason to emit a failure UUID or close the
task-cost scope. Return quietly after sending the context. Both an unclassified
reply and a context request keep the original suggestion eligible for a later
trusted 👍. That exact reaction confirms the provisional wording directly and
resumes the saved episode once. A later text answer also resumes through the
normal harness and requires `--kind answer` after semantic review. Earlier
replies and classifications remain in private history and cannot be replayed
as answers to another question. Publication remains blocked while a text reply
is unclassified or the question awaits clarification.

`poll` performs a bounded local connector query, with no model call, for operator
inspection/recovery. A quoted reply or question ID identifies its question; an
unquoted reply can address the sole open question on that authenticated route.
New questions show readable episode timestamps and invite a normal reply or
thumbs-up; their routing IDs stay in private state. Older questions containing
an ID still work, and typing that ID is optional for the sole waiting question.
Help/status/episode commands and replies quoting another message do not answer
that question. A message ID already used for feedback cannot answer a later one.
`poll` also accepts a currently materialized thumbs-up reaction from the trusted
contact on the exact question, recording its reaction event ID and target. It is
feedback on that question, not video/publication approval. The text harness itself
does not forward reactions; the independent handoff watcher above validates them
and resumes the saved episode. Without that optional service, `poll` plus an
explicit continuation remains the recovery path. Ordinary authenticated text
replies resume through the text harness.
Minor wording/brief-attribution questions may use the existing fifteen-minute
provisional fallback **after actual sending**, with late explicit corrections
retained. This is not timed approval for unresolved identities, missing content or
an audio-quality tradeoff. Required feedback tests must actually send a sample
and question. Publication blocks while a question is unresolved.

## Operator experiment and session review

`adapters/openai-agents/task.py` submits an explicit private local-operator task
into the paired episode context without manufacturing a Marmot sender/message ID.
It uses the same configured model, restricted executor, bounded timeout, durable
submissions and saved API items/usage. A new episode gets fresh context; ordinary
phone feedback continues that episode. Keep `task.json`, submission UUID, prompts,
turn/item logs and usage outside Git. Use `status`/`log` to inspect saved work.
Use `task.py usage` with the same instance/task/submission arguments to refresh
provider turn usage without inference. It deduplicates turn IDs, includes cancelled
turns and distinguishes cached input; missing usage stays unknown. Its saved
`usage-observed.json` is a token observation, not the billing dashboard's charge.
No token-consuming idle polling, automatic next-episode queue or budget permission
is added. Review episode 18's actual session before 17; repair its demonstrated
confusion. Review 17 for deterministic automation before 16. If feedback code
changes between tests, require another feedback test. Stop after the explicitly
authorized episodes and compare recorded usage with the billing dashboard before
choosing how to finish the remaining backlog.

When migrating from another queue, reconcile verified external completions into
that queue's private ledger before handing it back. Keep its pause and unrelated
holds intact. Copy only the necessary publication/review metadata and hashes;
leave credentials, chat histories and raw production evidence in their selected
account. Record where the authoritative evidence lives so a later harness does
not retranscribe or attach an already verified transcript.

An authenticated transcript-feedback reply uses a ten-minute active review timeout
by default (`transcription_turn_timeout_seconds`, at most 600), matching local
operator tasks. This bounds an active turn; it does not poll an idle chat or cap
spending. Long recognition still runs as a deterministic background job.

After a timeout, inspect the episode's files and provider checkpoint before
continuing. `adapters/openai-agents/reconcile.py --instance INSTANCE --state-root
EPISODE_API_STATE` fetches saved turns/items without inference. It refuses active
or ambiguous work. After inspecting those effects, repeat with
`--acknowledge-terminal` to record a completed/cancelled/failed outcome and clear
only that unresolved checkpoint. It never resends input. Cancelled inputs remain
non-replayable; use a new explicit continuation submission in the same episode.
Provider usage can arrive after completion, so a null initial receipt does not
mean zero cost; retain the refreshed turn usage separately.

For per-task model cost estimates across review turns and handoffs, use the
[task cost reporting workflow](task-costs.md). Begin one scope before substantial
transcript/video work and finish it after the requested outcome; retain it while
waiting for jobs or feedback.
