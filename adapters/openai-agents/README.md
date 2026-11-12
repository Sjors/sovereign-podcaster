# Optional Agents API adapter experiment

## Provider alternatives

This directory also contains the shared controller and standalone PPQ provider.
The [provider guide](../../docs/llm-providers.md) documents private settings,
new PPQ-only installations, switching back to Codex, usage and recovery. PPQ
does not call the managed Agents API or require a Codex CLI installation.

Documentation checked 2026-11-01. Session creation and a self-hosted executor
connection and the read-only YouTube identity check have passed with separate
application/environment keys, using `gpt-6.1-sol` on Ubuntu 26.04.1 LTS. Both
controller and executor ran as the isolated user; the helper returned the expected
channel ID with exit status 0 and no YouTube writes. The executor stopped afterward.
Linked credit balance and billing coverage remain unverified; check actual charges
in the Platform dashboard.

Start with [project authorization and secure key storage](authorization.md).
The chosen initial topology runs both controller and executor as the isolated
podcast user. Keep maintainer credentials separate from runtime keys. Codex CLI
`0.166.0-alpha.6` was tested independently;
version/help checks and a live restricted-key executor connection passed.

The [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview)
runs a managed Codex harness with durable sessions. It supports skills, shell,
MCP, steering and resumption. Model/tool usage uses API pricing; local compute
remains yours. US-only data residency and no ZDR apply even with self-hosted
execution. Transcripts/tool results can therefore leave the local machine.

The [Agents SDK](https://developers.openai.com/api/docs/guides/agents) runs the
agent loop in your application. Ordinary `codex exec` with an API key runs the
CLI harness locally. Neither is this managed Agents API experiment.

[Credit documentation](https://developers.openai.com/api/docs/guides/chatgpt-api-credits)
currently covers Agents API usage, including hosted sandbox charges, but explicitly
excludes ordinary Codex usage through API keys. Eligible paid Pro/Business plans
must be at least seven days old; the subscription/API organization owners and
email must match. Claim/link the benefit, check its actual grant and expiry in the
correct organization, and confirm project limits. No assumption about this user's
subscription or grant is made. Purchased credits can be spent after free credits
run out. Confirm billing settings before testing.

For [self-hosted execution](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted),
install Codex independently in the isolated account (the docs currently use
`@openai/codex@alpha`). Pin the successfully tested version. The application key
is used by the controller only. With separate controller/executor environments it
can stay outside the executor's filesystem. In the chosen single-UID setup it is
an owner-only file under the isolated account, readable by that UID; omitting it
from the executor environment alone does not create a filesystem boundary.
Application permissions: `api.agents.read`, `api.agents.write`,
`api.responses.write`. Use a separate environment key from the Agents tab, same
organization/project/user or service account, with all other permissions None.
Only that restricted key is passed to the executor as `CODEX_API_KEY`. It is
readable by agent code, so protect and rotate it accordingly. Outbound access is
needed to `api.openai.com` and `codex-cloud-environments.chatgpt.com` (WebSocket).

## Bounded YouTube access check

After completing [YouTube setup](../../docs/youtube-api-setup.md), save the private
instance configuration as `$HOME/.config/sovereign-podcaster/youtube.json`. It
contains the helper/runtime paths, credential directory and expected `channel_id`;
the credentials themselves stay in their private files. Run as the isolated user:

```sh
umask 077
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/adapters/openai-agents/smoke-youtube.py" \
  --project-id "$SP_OPENAI_PROJECT_ID" --model gpt-6.1-sol --timeout 90
```

The command prints its private run directory, session ID and live progress. It
requests a 50-cent server limit by default. The currently tested endpoint rejects
that field before session creation; use `--without-server-spend-limit` only with
explicit authorization for a timeout-only run. That option provides no dollar cap.
One such read-only test was authorized during initial setup, not ongoing runs.

Each run saves the request, submission IDs, session, progress event types and
executor log outside the repository; execution failures also save a sanitized
`failure.json`. API errors include the request ID for support. Completed runs also
save turns, items and a result with session/turn usage. Inspect the actual command
output in `items.json` before accepting a successful model turn as a successful channel check. The controller
stops its executor on completion/failure and attempts cancellation on a timeout.
Event submission can return an empty HTTP 202 response: this confirms acceptance,
not completion. Keep the executor running and poll the turn; do not treat the
empty response as a JSON failure. This behavior has an offline regression test.

Usage can lag behind turn completion. The first successful run initially returned
null usage; a later read of its turns supplied token counts. Reread saved session
and turn resources when inspecting usage; null means unknown. A private review
record preserves the verified command, exit status, parsed channel identity,
source commit/hashes and later usage, independently of the agent's final message.

Offline adapter regression tests (no API calls or credentials):

```sh
python3 -m unittest discover -s adapters/openai-agents -p 'test_*.py' -v
```

For a connection or authorization failure before any turn starts, rerun the same
command with `--resume-run /absolute/path/to/saved/run` and identical options.
It checks server history and reuses the saved submission ID. It refuses to submit
when a turn already exists; inspect that session's history instead. This small
smoke command does not implement general feedback or continuation after a turn;
the manual session interface below supports those operations.

## Manual session interface

Minimal manual controller interface, after eligibility/credential setup: cURL and
JSON files suffice. Keep the controller's credential in an owner-only curl config
outside this repository, or have a controller read the private application-key
file directly. Both processes can run under the same isolated account. For example, an
operator creates a 0600 config containing the Authorization header using their
secret manager, without pasting it into chat, arguments or shell history. The
commands below refer to that file; they contain no credential values. Run on the
controller, with a private current directory and `umask 077`.

```sh
# $AUTH is the private curl config path; $API is https://api.openai.com/v1
# Choose an accessible model explicitly; use only synthetic input first.
# create.json:
# {"agent":{"model":"SELECT_MODEL","instructions":"Offline slides only. No uploads or publishing."},
#  "environment":{"type":"self_hosted","workspace_directory":"/absolute/private/artifacts/work",
#  "capability_directories":["/home/podcaster/capabilities"]}}
curl --fail-with-body --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  -H 'Content-Type: application/json' --data-binary @create.json \
  "$API/agents/sessions" > session.json
```

Save `id`, `environment.id`, and `environment.remote_url` from that result in the
private run record. Transfer only environment ID/URL and the restricted credential
to the executor. On the executor, with a clean environment, fresh HOME/CODEX_HOME,
no SSH agent and the restricted key loaded securely:

```sh
codex exec-server --remote "$REMOTE_URL" --environment-id "$ENVIRONMENT_ID"
```

Reuse the returned URL unchanged. Keep one executor per session. Before sending
work, open progress in a separate controller terminal. `$SESSION` is the saved ID:

```sh
curl --fail-with-body -N --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  -H 'Accept: text/event-stream' "$API/agents/sessions/$SESSION/events?stream=true"
```

[Send tasks and feedback](https://developers.openai.com/api/docs/guides/agents-api/sessions)
using the same saved session. Create `input.json` with
`{"events":[{"type":"agent.session.input.message","input":[{"role":"user","content":[{"type":"input_text","text":"Build the synthetic slide bundle and verify it."}]}]}]}`.
For each distinct submission generate and persist an idempotency key; reuse that
key and identical body on a transport retry:

```sh
curl --fail-with-body --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  -H 'Content-Type: application/json' -H "Idempotency-Key: $SUBMISSION_KEY" \
  --data-binary @input.json "$API/agents/sessions/$SESSION/events"
curl --fail-with-body --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  "$API/agents/sessions/$SESSION" > session-current.json
curl --fail-with-body --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  "$API/agents/sessions/$SESSION/items?order=asc&limit=100" > items.json
curl --fail-with-body --config "$AUTH" -H 'OpenAI-Beta: agents=v1' \
  "$API/agents/sessions/$SESSION/turns?order=asc&limit=100" > turns.json
```

Follow pagination (`has_more`, `last_id` as `after`) for complete history. Progress
streams do not replay missed events: recover saved items/current state after a
disconnect. Inspect turn completion/failure and actual tool results, not just idle.
Restart the executor for the same environment to resume a viable session, and send
feedback to that same session. Preserve local bundles independently. Cancellation
uses an events body `{"events":[{"type":"agent.session.input.cancel"}]}`.

[Usage](https://developers.openai.com/api/docs/guides/agents-api/observability)
is available on sessions/turns and in the Platform dashboard. Sum root and subagent
usage with pagination; missing usage is unknown, not zero. Cached input and
reasoning are subsets of input/output, not additional tokens. Counts are best
effort, not an invoice; include retries, tools and any separately billed resources.
Use the dashboard bill/credit balance for actual cost; record selected model/rate
date for estimates. For the first smoke test disable unnecessary tools/subagents,
use synthetic files only, watch the run, cancel after the bounded task, then
inspect usage. Do not assume a dashboard budget is a hard per-run cap.

This smoke task authorizes only the YouTube helper's read-only identity check.
The helper uses the isolated account's existing OAuth grant; task instructions
alone do not enforce read-only access to credentials or the network. Select skills
individually after review and license checks. Do not point capability directories
at the owner's existing skill or chat trees.
