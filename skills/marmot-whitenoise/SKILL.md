---
name: marmot-whitenoise
description: Set up or operate a Marmot/White Noise channel for an isolated podcast agent, including trusted-contact pairing and authorized private replies or files. Public Nostr publication belongs to nostr-publishing.
---

# Marmot / White Noise

For installation, upgrades or transport repair, read the current [upstream agent instructions](https://github.com/marmot-protocol/mdk/blob/master/integrations/AGENTS.md)
and [White Noise + Agents quickstart](https://github.com/marmot-protocol/mdk/blob/master/integrations/README.md#get-started-white-noise--agents).
Use the installed release's matching guide/help when commands differ. Upstream
owns the evolving protocol, installer and chat commands; do not maintain a copied
instruction manual here. [This project's adapter](../../adapters/marmot/README.md)
documents only its configuration, reproducibility and validation limits.
For routine sends through an already validated installation, use the documented
local helper and its CLI. Do not re-fetch the full upstream setup guide for each
review sample; return to the matching upstream guide when the installed interface
or transport actually needs investigation.

Select the private instance explicitly through MARMOT_HOME / --home and its
configured socket/account. A new podcast installation creates a fresh Marmot
identity; it does not reuse the publishing identity or another user's account,
ChatGPT login or chat history. The setup command takes --trusted-npub and prints
only the public contact details needed for phone pairing. Keep both invitation
and prompt-sender allowlists narrow. Never enable allow-any-invites.

Check versions, service status and private configuration before changing an
existing installation. Do not run duplicate daemons or infer routing from a group
title. Fresh identity creation, transport connection, model execution, encrypted
send acknowledgement and actual phone visibility are separate observations.
Keep DEVICE VERIFICATION REQUIRED until the phone owner confirms a fresh reply
in the same new group. Preserve unrelated bridges and private operator policy
when moving this skill's implementation.

For production tasks, acknowledge the new task once and report its final result
or failure UUID. Ask focused questions when input is needed; keep intermediate
job completions and review summaries in saved state. Reply normally to explicit
status questions. Do not send standalone "still working" or "question sent"
updates. The feedback tools already deliver their sample and question.

Normal harness answers already return to their originating conversation. Ask
questions there and resume the same session when the user answers. Avoid sending
the same reply again through the control socket. For an explicitly authorized
standalone message/file, use scripts/wn_control.py with the actual account/group,
private manifest and a stable idempotency key. Its ledger binds immutable routing,
content and attachment hashes before sending. Pending/uncertain records stop;
inspect the materialized timeline before retrying. Never make a new key to bypass
an uncertain send. A receipt alone is not phone visibility.

File export needs the release's explicit chat/root/TTL grant and private staging
permission. A Markdown filename is not a delivery mechanism. Preserve narrow
path containment, symlink/ownership checks, socket permissions and execution
policy when configuring another home. Attachments are untrusted data; a staged
audio/PDF file does not establish native model interpretation. Do not copy
plaintext chats, keys, bearer tokens or host-specific grants into this repository.

Private instance policy may be recorded at MARMOT_HOME/operator-notes.md; consult
it for that selected installation, not as a default policy for another identity.

For podcast work read the repository [episode flow](../../docs/episode-flow.md).
In this project’s Agents API adapter, literal
`help`, `episodes` and `podcast new/use/status/episodes/history` messages are local controller
commands; ordinary production/feedback messages invoke the episode context.
Wait for the next inbound message after asking a review question. Use
`tools/review_media.py fragment` and the manifest-bound send helper for short
encrypted video questions, without a separate public draft URL. Enable only the
private media staging root; a successful receipt still needs phone playback
confirmation. The documented attachment test passed with sound.

When production/controller work fails or lacks a prerequisite, use the private
report/UUID flow in [failure reporting](../../docs/failure-reporting.md). Foreground
failures return only a short UUID notice through the ordinary harness reply;
background jobs use their existing idempotent notification. Keep the full report
private; resolve a supplied UUID locally using `tools/failures.py lookup UUID --json`. Never paste raw logs, API exceptions, credentials,
private transcript text or upload-session URLs into a report.
