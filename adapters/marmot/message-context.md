# Incoming message identity and silent completion bridge patch

Upstream `wn-agent-v0.14.0` passes account/group routing to its backend but omits
the incoming message ID and sender. The small
[`marmot-message-context.patch`](../../patches/marmot-message-context.patch)
adds turn-local `MARMOT_MESSAGE_ID_HEX` and `MARMOT_SENDER_ACCOUNT_ID_HEX` after
the existing sender allowlist and self-message checks. It changes no relay or MLS
protocol. The API adapter verifies these values against `timeline_message_get`
before using an incoming message. It deduplicates by authenticated ID, rather
than treating identical text as the same request forever.

The Codex backend also recognizes `{"type":"adapter.silent"}` as an explicit
request to finish a successful turn without a chat acknowledgement. The API
adapter emits it when a feedback tool has already asked its question or a saved
transcript stage is waiting for a durable job. The bridge still records the
session. It suppresses only the empty-output fallback after exit code zero with
no backend error or delivery failure; ordinary empty output, failed runs and
uncertain deliveries keep their existing notices/recovery. Text and artifacts
are never discarded by this event. Install the rebuilt bridge before enabling
the matching adapter: an older bridge ignores the event and sends its fallback.

Source: [marmot-protocol/mdk](https://github.com/marmot-protocol/mdk), tag
`wn-agent-v0.14.0`, commit `3fb4b4759ac676b0c21c4c3527074866c9fa4c89`.
Upstream is MIT; its notice is retained in [the provenance document](../../docs/provenance.md#marmot-license-notice).
The patch and exact provenance are also in the canonical patch catalog.
Before updating the pinned release, first check upstream for equivalent message
context support. Prefer it when available, test the environment contract and
remove the patch only after that replacement passes. Follow evolving upstream
[agent instructions](https://github.com/marmot-protocol/mdk/blob/master/integrations/AGENTS.md)
for the main installation; this document describes only our adapter delta.

## Reproduce and install

An administrator installs build dependencies; they grant the agent no sudo rights:

```sh
sudo apt install --no-install-recommends \
  git ca-certificates python3 build-essential pkg-config perl cmake clang libssl-dev
# If using the distribution Rust toolchain:
sudo apt install --no-install-recommends cargo rustc
```

The tested build used the existing **Rust/Cargo 1.99.1** toolchain, a locked Cargo
workspace and the upstream dependency pins. Rust 2024 edition support is required.
An operator may instead supply a suitable existing Rust toolchain, following
[official Rust installation guidance](https://www.rust-lang.org/tools/install).
Cargo fetches HTTPS dependencies and builds the pinned source; no GitHub token,
SSH agent, API credential or other user's authentication is required. On the
maintainer host Cargo/Rust are supplied by rustup rather than apt.

After the upstream/Marmot setup, **before sending production messages**, run as
the isolated user (or build in a separate trusted build account and transfer only
the resulting bundle). Keep source/build output outside the repository:

```sh
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/adapters/marmot/build-harness.py" \
  --source "$HOME/.cache/sovereign-podcaster/mdk-message-context" \
  --out "$HOME/.local/share/sovereign-podcaster/harness-build"
python3 "$SP_REPO/adapters/marmot/install-harness.py" \
  --bundle "$HOME/.local/share/sovereign-podcaster/harness-build" \
  --home "$HOME/.marmot-agents/podcast"
```

The builder checks the exact source commit and refuses unrelated dirty changes,
applies the patch with umask 077, runs 149 library tests, 23 process-contract
tests and the `wn-codex` tests (including message context, parallel route isolation
and explicit silent completion), builds `wn-codex` and records patch/binary
hashes/toolchain/source/license in `build.json`. This is a checked source build,
not a bit-for-bit reproducible compiler claim. Retain the build manifest privately.

The installer checks those hashes and active request markers, stops only
`sovereign-podcaster-agent.service`, installs under
`~/.local/lib/sovereign-podcaster/`, and adds a service drop-in overriding only its
executable. It restarts that service. The connector, phone identity, session state,
upstream release binary and other accounts' services remain intact. No key is
printed or copied. A previous custom binary is retained as `wn-codex.previous`.
Inspect an active/unresolved request before any restart; do not delete its marker
to bypass the check. The manifest is local build provenance, not an external
signature/security boundary against a compromised build account.

Rollback requires a compatible backend too: the new backend fails closed when
message identity is absent. Restore the earlier checked repository revision and
service configuration together during a maintenance window; keep the original
release executable. Do not quietly disable authentication/deduplication to keep
an incompatible combination running.

## Validation

The Python tests cover distinct identical-word replies, exact-ID replay, changed
prompt reuse, wrong senders/routes, timeline deletion/truncation, stale review
packets, combined/private/public scope separation and interrupted request guards.
A real phone check can send `help` (zero model calls), then two distinct ordinary
feedback messages. Observe their different saved incoming IDs and requests.
Deliberately replaying a saved ID in a fixture must return its saved result and
must not launch tools. Do not resend real publication messages to test replay.
