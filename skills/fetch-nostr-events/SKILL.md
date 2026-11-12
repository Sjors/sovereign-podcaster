---
name: fetch-nostr-events
description: Fetch, decode, and verify public Nostr events from note1, nevent1, or naddr1 identifiers and Nostr client URLs. Use when a user links a Primal, njump, nostr.eu, or other Nostr post; asks for the exact text or raw event JSON; needs relay-hinted retrieval; or wants the event ID and BIP-340 signature checked before analysis.
---

# Fetch Nostr Events

Retrieve the signed event itself before relying on client-rendered text, previews, screenshots, or search snippets.

## Workflow

1. Extract the `note1`, `nevent1`, or `naddr1` identifier from the user input.
2. Run the bundled fetcher:

   ```bash
   python3 scripts/fetch_nostr_event.py '<identifier-or-url>'
   ```

   Resolve `scripts/` relative to this `SKILL.md`, not the current workspace.
3. Read the verification status written to stderr. Treat the JSON on stdout as authoritative only when both the NIP-01 event ID and BIP-340 signature verify.
4. Use `--content-only` when only the exact event body is needed. Use the default JSON output when author, timestamp, kind, tags, reply context, or signature matters.
5. Follow referenced `e`, `a`, or `q` tags separately when the request requires conversation context. Do not mistake reactions or client-generated previews for part of the signed event.

## Retrieval strategy

The fetcher prefers `nak fetch` when `nak` is installed because `nevent` and `naddr` relay hints can be queried directly. Otherwise it retrieves the raw Event JSON embedded by a public njump gateway and verifies it locally with only Python's standard library.

If both routes fail:

- Try `--gateway https://nostr.eu`, `https://nostr.com`, or another trusted njump deployment.
- Install [`nak`](https://github.com/fiatjaf/nak) only with user approval, for example `brew install nak` or the project's documented installer.
- For a bare 64-character event ID without relay hints, use `nak req -i <id> <relay...>` and verify the returned event with `nak verify`.

## Integrity rules

- Distinguish retrieval from verification. A gateway returning text does not authenticate it.
- Verify the canonical NIP-01 event hash and Schnorr signature before attributing content to a pubkey.
- Report the hexadecimal `pubkey`; resolve profile metadata separately and treat display names as unsigned-by-reference, mutable metadata.
- Preserve the exact `content`, `tags`, `created_at`, and `kind` when quoting or reconstructing threads.
- Never publish, react, zap, or send events unless the user explicitly requests that state-changing action.

## Common commands

```bash
# Verified event JSON
python3 scripts/fetch_nostr_event.py 'https://primal.net/e/nevent1...'

# Exact signed content only
python3 scripts/fetch_nostr_event.py 'note1...' --content-only

# Force gateway retrieval even if nak is installed
python3 scripts/fetch_nostr_event.py 'naddr1...' --no-nak
```

For authorized identity setup or long-form publication, use the companion
[nostr-publishing skill](../nostr-publishing/SKILL.md). This fetcher remains read-only.
