# Nostr operations

## Runtime and identity storage

Use a private Python environment outside the skill/repository. On Ubuntu:

```sh
# Administrator prerequisites on Ubuntu:
sudo apt install --no-install-recommends python3 python3-venv ca-certificates
# Isolated user; select your checkout explicitly.
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/tools/setup_nostr_runtime.py"
SP_NOSTR_PY="$HOME/.local/share/sovereign-podcaster/nostr-venv/bin/python"
SP_PUBLISH="$SP_REPO/skills/nostr-publishing/scripts/nostr_publish.py"
```

This gives the account its own CPython 3.11.17 and the pinned signing libraries.
System Python 3.14 is used only for bootstrap; coincurve 21.0.0's source build
fails there. See the [runtime explanation](../../../docs/nostr-setup.md#runtime).

Substitute the actual skill script path in the commands below. No global package or relay
installation is necessary. The script uses coincurve/libsecp256k1 for key generation and
Schnorr signatures, bech32 for NIP-19 encoding and websocket-client for WSS connections.

```sh
"$SP_NOSTR_PY" "$SP_PUBLISH" init \
  --directory ~/.config/nostr-publishing/identities/ACCOUNT --name 'Display Name' \
  --relay wss://RELAY-ONE --relay wss://RELAY-TWO
```

Creates an owner-only `secret.hex` and `identity.json` in a 0700 directory; refuses to replace
an identity. `identity.json` contains public metadata, relay URLs and the relative key path.
The `public` action returns only name, hex public key, `npub` and relay list. Signing rejects
symlinked, foreign-owned or broadly readable key files and a key/config public-key mismatch.
The private key is the account's control credential; preserve it securely when moving machines.
Runtime directories and keys do not belong in Git. Do not generate a replacement key just
because an account cannot yet write to its desired relay.

## Resolve and read

```sh
"$SP_NOSTR_PY" "$SP_PUBLISH" resolve --nip05 NAME@DOMAIN --output resolution.json
"$SP_NOSTR_PY" "$SP_PUBLISH" query --relay wss://RELAY \
  --filter '{"authors":["HEX-PUBKEY"],"kinds":[0,3,10002],"limit":10}' \
  --output existing-events.json
```

With `--identity /absolute/identity.json`, query/publish use its relay list unless explicit
`--relay` arguments override it. Query verifies received event IDs/signatures and records
whether end-of-stored-events was reached. Treat failed/incomplete relay reads as uncertainty
when updating an existing replaceable event, not evidence that its fields/list are empty.
Filter received data by expected author and kind when selecting an event; choose the latest
timestamp, breaking timestamp ties by lowest event ID as specified in NIP-01.

## Prepare, sign and publish setup events

Prepare reviewed unsigned JSON containing `kind`, `tags` and `content`:

- Profile (kind 0): `content` is a JSON-encoded object, e.g. `name`, `display_name`, `about`,
  `website`. Set `nip05` only after the new account's own mapping is configured.
- Follow list (kind 3): empty `content`; tags such as
  `["p", "FOLLOWED-HEX-PUBKEY", "wss://RELAY-HINT", "Petname"]`. Include the **complete**
  intended list, retaining existing follows on an established account.
- Relay list (kind 10002): empty `content`; `["r", "wss://RELAY"]` for read+write, or a third
  `"read"`/`"write"` marker for one direction. Prefer 2–4 relays in each direction.

```sh
"$SP_NOSTR_PY" "$SP_PUBLISH" sign --identity /absolute/identity.json \
  --input reviewed-event.json --output signed-event.json
"$SP_NOSTR_PY" "$SP_PUBLISH" publish --identity /absolute/identity.json \
  --input signed-event.json
"$SP_NOSTR_PY" "$SP_PUBLISH" publish --identity /absolute/identity.json \
  --input signed-event.json --apply --output publication-results.json
```

Sign defaults missing `created_at` to current Unix time and sets the selected pubkey. It
validates fields and strips unrelated keys. Signed events contain only public data and may
be saved in the working project's provenance. `publish` needs no private key: it verifies
the already-signed event and, when an identity is selected, checks its author matches.
The offline publication plan makes no network requests. The script does not pay, solve
proof-of-work or auto-authenticate with NIP-42. A relay requiring those is reported as such
or as a failed acknowledgement/timeout; use another authorized relay or resolve its policy.

Each result distinguishes `accepted` from `retrieved`. Check the result file instead of
treating the CLI's successful reporting as proof all relays accepted the event. On an
ambiguous send, query the saved event ID, then resend the exact saved signed event if needed.
No automatic new event or article edit is created by publication retries.

## Long-form articles

```sh
"$SP_NOSTR_PY" "$SP_PUBLISH" article --input article-for-nostr.md \
  --title 'Article title' --slug stable-article-id --summary 'Short description.' \
  --published-at UNIX-FIRST-PUBLICATION-TIME --source-url https://BLOG/ARTICLE \
  --output article.unsigned.json
```

This creates unsigned kind-30023 JSON offline. Review the exact Markdown and tags, then
sign and publish as above when authorized. The helper rejects HTML; it does not rewrite
paragraphs, remove duplicate headings or invent source URLs/summary/first publication time.
For an edit reuse the saved `d` and first `published_at` with a later `created_at`; do not
derive a new identifier from a changed title. Do not carry the old signed event's signature
into a changed event. Save identity+kind+`d` as the article address and each revision's ID.

To create an `naddr` with the installed bech32 encoder: TLV type 0 is the UTF-8 `d` value,
type 2 is the author's 32-byte pubkey, type 3 is the 4-byte big-endian kind. Optional repeated
type 1 values are relay hints. Encode the concatenated TLV bytes with HRP `naddr` using
bech32 (not bech32m). Use client links supporting NIP-23; successful profile rendering does
not establish that a client can render long-form content.

## Validation and primary references

```sh
"$SP_NOSTR_PY" -m unittest discover -s "$SP_REPO/skills/nostr-publishing/tests" -v
```

Tests cover signing/tampering, key permissions and identity mismatch, NIP-19 reference
encoding, public outputs, long-form tags/HTML rejection, and acknowledgement/readback
distinction. Live relay behavior still needs checking for the selected account. The existing
`fetch-nostr-events` skill provides an independent standard-library signature verifier.

Protocol sources inspected 2026-10-22:

- [NIP-01 events and relay protocol](https://github.com/nostr-protocol/nips/blob/master/01.md)
- [NIP-02 replaceable follow lists](https://github.com/nostr-protocol/nips/blob/master/02.md)
- [NIP-05 identifiers](https://github.com/nostr-protocol/nips/blob/master/05.md)
- [NIP-19 identifiers and address TLVs](https://github.com/nostr-protocol/nips/blob/master/19.md)
- [NIP-23 long-form articles](https://github.com/nostr-protocol/nips/blob/master/23.md)
- [NIP-65 relay metadata](https://github.com/nostr-protocol/nips/blob/master/65.md)
- [coincurve signing API](https://ofek.dev/coincurve/api/)
