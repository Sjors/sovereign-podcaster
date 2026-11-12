# Cost reports for substantial tasks

The Agents adapter supports a private cost scope for a transcript, video or other
substantial task. It spans model turns, background-job handoffs and feedback waits.
The harness instructions start the scope before work and request its report only
when the requested task is done. The backend then observes usage and appends a
short estimate to the ordinary reply **after the final model turn**, so that turn
is included. No extra model call or standalone chat send is made. Transcript and
video publication authorization, maintenance guards and failure notices still apply.
Chat notices round estimates to cents, for example `Estimated model cost: US$0.61.`
Full precision and accounting limitations remain in the private report and this runbook.
Enable this by installing the code in the operator's checkout and configuring the
private price table below. The controller supplies accounting instructions on
each subsequent model turn, including resumed sessions. Deployment itself makes
no model call and starts no production task. Existing tasks can start a scope on
their next continuation; it measures work from that turn, not earlier history.

Copy [the price template](../examples/cost-pricing.json) outside Git. Replace the
model placeholder with the exact configured model ID and each null with your
applicable **USD per million tokens** rate (`input`, `cached_input`, `output`).
Retain the pricing source and UTC verification date; review them when rates or
service tiers change. Set `cost_pricing` in the private instance JSON to that
absolute filename. The task saves its own price snapshot so later edits cannot
silently reprice earlier work. Missing model pricing produces an unavailable
amount, never a zero charge. Invalid prices produce a private failure UUID.
No Admin/billing key is needed: usage reads use the existing application key.

Within the selected executor turn, run:

```sh
python3 tools/task_costs.py begin --id transcript-18 --kind transcript
# Do the selected task, returning while background jobs or feedback are pending.
# Reuse the scope across continuations. For a video use --kind video.
python3 tools/task_costs.py finish --id transcript-18
```

`SP_COST_CONTEXT` is supplied by the adapter, identifying that turn's session and
pre-turn baseline. Beginning includes the whole current turn, even work performed
before the command. Use one task at a time in an episode context, with a new stable
ID for each task. Repeating begin for the active ID is safe; IDs cannot be rebound
to another kind/session or reused after closure. Do not combine separate tasks
within one turn. Waiting does not finish a scope. Start the video scope after
closing the transcript scope in a prior turn to keep their costs separate.

Private reports live under the episode API state directory's `task-costs/ID.json`,
with mode 0600. Each turn refreshes observed usage for the active scope, including
failed/cancelled work. The finish command marks it closing; only a successful
model turn closes it and adds the notice. A replay uses the saved reply and cannot
repeat the production work or send another separate report. A telemetry error
retains production success and appends a failure UUID for local inspection; inspect
the report and pending scope before recovery. No background job is restarted.
A process crash before observation may leave a scope pending; reconcile the
provider checkpoint before continuing in that same scope.

For delayed usage, refresh a **closed** report without inference:

```sh
python3 adapters/openai-agents/cost-report.py --instance PRIVATE_INSTANCE.json \
  --report EPISODE_API_STATE/task-costs/transcript-18.json
```

This refreshes only turn IDs already attributed to that task, not later tasks.
It prints a compact estimate for local inspection and sends no chat message.

The calculation is `(input - cached) * input_rate + cached * cached_rate +
output * output_rate`, divided by one million. Reasoning is already in output.
Turn IDs are deduplicated; session totals are never added to turn totals. Missing
usage, missing cache counts and empty observations remain incomplete, with any
priced subtotal labelled partial. Delegation is disabled by this adapter; any
unexpected delegated turns returned by the session turn endpoint remain visible.
The ledger does not claim to discover separately listed subagent histories.

These are best-effort model token estimates, not invoice amounts, net credit
balances or spending caps. Compute for local Whisper/rendering, hosting/storage,
tool charges, third-party services and any separate cache-write charges are
excluded. They are not assumed free. The ledger does not currently meter them.
Custom model overrides, tiered/long-context pricing and provider-specific discounts
need a matching rate policy before these simple rates can estimate them reliably.
See the official [usage and accounting limitations](https://developers.openai.com/api/docs/guides/agents-api/observability)
and the [existing billing-access boundaries](../adapters/openai-agents/authorization.md#usage-visibility-and-independent-spending-controls).
