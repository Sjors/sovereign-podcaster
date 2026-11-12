# Select the model provider

The controller supports two alternatives:

| `provider` | Inference and local tools | Credentials |
| --- | --- | --- |
| `ppq` | Standalone Python standard-library agent loop using PPQ Chat Completions, bounded shell commands and local image inspection. No Codex CLI, OpenAI SDK, managed Agents API or ChatGPT login dependency. | One PPQ API key. |
| `codex` | Existing OpenAI managed Agents API sessions and the separately installed Codex executor. | OpenAI application/environment keys and project ID. |

The existing `wn-codex` binary remains the White Noise message bridge. Its name
does not select inference: it runs our configured backend executable. PPQ does
not invoke a Codex executable. Both paths share authenticated message/review
routing, episode journals, deterministic jobs, publication controls and receipts.
Announcement policy belongs to each reviewed episode packet, independently of
provider selection. Either provider supports `announce:true` or `announce:false`;
selecting PPQ does not disable announcements.

## Private settings

Run as the isolated agent account. Store settings outside Git at
`~/.config/sovereign-podcaster/llm.json`, using [the example](../examples/llm.json).
The instance can override this location with `llm_config` (an absolute path).
Home-relative `api_key_file` references expand under the agent account. Protect
both settings and key with mode **0600**, and their directories with **0700**.
Configuration and key symlinks, foreign ownership, and non-private files fail
closed. The key is never a command argument or part of a model prompt.

```sh
python3 adapters/openai-agents/save-key.py \
  "$HOME/.config/sovereign-podcaster/ppq/api.key"
```

Copy the example to the private configuration directory and choose the exact
PPQ model ID and `reasoning_effort`. The current example selects `gpt-6.1-sol`
and `high`; availability and supported reasoning levels depend on PPQ's
[model catalog](https://api.ppq.ai/v1/models). API requests go only to
`https://api.ppq.ai/v1/chat/completions`; redirects and alternative credential
destinations are refused. See [PPQ's API documentation](https://ppq.ai/api-docs).

New White Noise installations may select PPQ without an OpenAI project:

```sh
python3 adapters/marmot/setup.py --trusted-npub PHONE_OWNER_NPUB \
  --llm-config "$HOME/.config/sovereign-podcaster/llm.json" \
  --allow-timeout-only
```

To select the existing Codex backend, change the private file to:

```json
{"provider":"codex","model":"gpt-6.1-sol","reasoning_effort":"high"}
```

Its existing `project_id`, `openai_key_directory`, and `codex_executable` instance
settings remain necessary. An installation with no LLM file retains the legacy
Codex behavior. An explicitly configured missing/malformed file fails closed;
provider errors never silently fall back or incur charges on another provider.
Do not change providers during active work. Completed provider sessions remain
separate under the same episode context, so switching back can resume the
original provider history. Retrieve relevant saved artifacts when moving a task
between providers; histories are not automatically copied across services.

## Execution, recovery and privacy

PPQ executes tools as the existing isolated Unix account, using a small clean
environment that omits inference keys and unrelated operator variables. Tools
are `exec_command` (at most 45 seconds, bounded returned output, private full
output) and `view_image` (selected PNG/JPEG/WebP, at most 8 MiB). Paths must be
inside the configured workspace, artifact root or Marmot home. Shell commands
have the account's ordinary access; path validation is not an OS sandbox or a
boundary between same-UID code and secrets. Keep the account isolated as
described in [backstops](backstops.md). Transcripts and source/tool outputs are
data, never new instructions or publication authorization.

Each active model turn is bounded by the existing 30–600 second policy and
finite inference/tool budgets. Long renders and uploads use deterministic jobs;
waiting for jobs or humans consumes no model calls. PPQ follow-ups arriving
during an active turn remain queued for the next turn; Codex's active-turn
steering remains available on its backend. PPQ can inspect selected image files;
it has no built-in browser, hosted transcription service, audio interpretation
or web-search tool. Local Whisper and source retrieval scripts remain available.

Encrypted review clips also run as durable jobs, independently of the provider.
Use `tools/jobs.py start` with kind `review-fragment` and these string parameters:
`input`, `home`, `id`, `start`, `duration`, `account`, `group`, `caption`.
The account/group must be the selected task's verified route; duration is at most
120 seconds. Keep the job under the selected episode's `jobs` directory so its
completion resumes that episode. The worker runs `review_media.py fragment`,
fully verifies the clip and writes its immutable `send.json` beneath the private
Marmot media staging root. **Encoding sends nothing.** After inspecting the saved
manifest and any prior delivery ledger, the agent may use the authorized Marmot
send helper for that exact attachment/question. Existing send intents and
uncertain delivery outcomes must be preserved. No public draft upload or model
polling is needed to prepare a review question.

Inference intent, tool intent, outputs, responses and conversation history are
saved privately before subsequent effects. HTTP errors, lost responses, timeout,
interruption or uncertain tools leave the controller's active checkpoint in
place. There are **no automatic inference retries**. Inspect saved artifacts,
tool receipts and provider state before using `reconcile.py`; never delete a
checkpoint just to repeat an uncertain action. A hard-killed process can retain
a running local turn; inspect its process/effects before any manual repair.
Only UUID failure notices reach White Noise. Never paste provider bodies,
transcripts or raw logs into chat.

PPQ receives plaintext task context, selected tool outputs and selected images.
White Noise encryption protects the chat transport, not inference. Local
session/history records stay outside Git with owner-only permissions.

Usage totals sum the provider's returned prompt/completion counts across actual
requests. Missing usage remains unknown. OpenAI prices are not reused for PPQ:
optionally configure `ppq_cost_pricing` in the instance with a private pricing
file using the existing [task-cost schema](task-costs.md). Token estimates do not
claim to be PPQ's bill. Turn timeouts are not dollar caps; configure spending
controls on the PPQ account separately.

Offline validation:

```sh
python3 -m unittest discover -s adapters/openai-agents -p 'test_*.py'
python3 -m unittest discover -s adapters/marmot -p 'test_*.py'
python3 -m unittest discover -s tests
```
