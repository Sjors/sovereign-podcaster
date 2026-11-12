---
name: nostr-publishing
description: Create a Nostr identity, sign and publish profile/relay metadata, articles, podcast videos and announcements, or request event deletion. Use for authorized Nostr publication; use fetch-nostr-events for reading existing posts.
---

# Nostr publishing

Use `scripts/nostr_publish.py` with the pinned dependencies in `scripts/requirements.txt`.
Read [references/operations.md](references/operations.md) for setup, commands and protocol
references. The script separates local signing from relay publication; `publish` plans
offline unless given `--apply`. Select an identity explicitly. Keep private keys in an
owner-only directory outside source repositories, never in tool arguments, chat or logs.
Public hex keys and `npub` identifiers are safe to share. Never overwrite an existing key
when resuming account setup; retrieve the saved identity and signed events instead.

Select the show's configured identity and expected public key explicitly. Account paths,
hosts, relays and Blossom servers belong in private instance configuration. Reuse an
established identity during migration; fresh identity creation is a separate choice.
See the repository's [Nostr setup guide](../../docs/nostr-setup.md) for prerequisites,
isolated-user migration, a fresh identity, dependencies and the temporary clip check.

## Identity and follows

Resolve a supplied NIP-05 identifier over HTTPS without following redirects. Fetch and
verify the returned pubkey's kind-0 metadata and check the identifier there before claiming
the profile matches. Follow the resulting **public key**, not the identifier string.
Do not assign somebody else's NIP-05 to the new account or claim a new identifier before
its domain mapping exists.

Profile metadata is kind 0; follows are kind 3; relay metadata is kind 10002. Before changing
an existing follow/profile/relay list, retrieve the latest verified event from its relays
and preserve entries/fields the user did not ask to remove. A new kind-3 event replaces the
whole follow list. Avoid concurrent updates; use a later `created_at` for intentional edits.
Publishing setup metadata does not authorize article publication or activity from another
identity. Respect existing user authorization without asking again for the same action.

Honor the source workflow's editorial review and authorization requirements. Transport
readback, signatures and checksums do not supply independent editorial judgment.

## Articles

Use NIP-23 **kind 30023** with Markdown content, a stable `d` identifier and a `title` tag.
Preserve `d` and the first `published_at` when editing the same article; update `created_at`
and record the new signed event ID. Keep draft text local until publication is authorized.
NIP-23's old kind-30024 draft convention is deprecated.

Prepare a reviewed Markdown edition: no HTML player or arbitrary hard wraps in prose.
Keep subtitle, disclosure, citations and podcast/book links; avoid duplicating the title
heading when it is already supplied by client metadata. Use the hosted article-audio link
when available. Preserve
source hashes and cross-platform edit checks in the article project. The transport helper
does not decide whether an unsettled draft is ready to publish.

## Relay results

Publish the same signed event to the configured write relays. Keep a small NIP-65 relay list
and include the author's relay-list event at new destinations. Track relay acknowledgements
and independently query the exact event ID, verifying its hash and BIP-340 signature.
An `OK` alone does not establish retrieval; report partial acceptance, outages, whitelist or
authentication requirements accurately. Do not bypass relay policy or pay for access without
authorization. After a timeout, retry the **same signed event**, not a newly timestamped copy.
Keep public event JSON and per-relay results in the project for recovery and later syncing.

## Podcast video and cleanup

Read [video-recovery.md](references/video-recovery.md) for storage preflight,
partial relay recovery, playback quality checks and a Castopod step between the
native post and announcement. Do not assume an optional mirror accepts an HLS
bundle merely because it accepts ordinary video files.

Blossom stores bytes; relays store signed events. Upload/readback, native video publication
and kind-1 announcement are distinct stages. Use the existing AV1 delivery policy unless
the operator changes it. Make the native video's description self-contained: introduce the
episode and participants, use verified `nostr:npub…`/`nostr:nprofile…` mentions, and include
the episode/source links visibly in the content. An `r` tag alone is not caption text.
Keep the title readable as plain text and the opening description useful before expansion.
Amethyst's [rich-description fix](https://github.com/vitorpamplona/amethyst/pull/4730)
renders these mentions/links in video feeds, with translation and expandable text, but
without embedded link/quote previews. Other clients may render differently.

Keep a short kind-1 announcement pointing to the native video's stable `nostr:naddr…`
for text-feed discovery. It need not duplicate the complete description. The production
publisher adds that link. A direct-MP4 kind-1 post is a separate compatibility choice:
for inline playback it needs the MP4 URL in its content and matching `imeta` metadata;
keep prose before a final contiguous URL block. The bounded access test uses that form.

In reviewed `nostr-video.json`, `participants` lists verified lowercase hex public keys
for native-video `p` tags. `announcement_mentions` separately selects announcement `p`
tags; do not copy all participants there automatically. Inline mention rendering does
not establish notification delivery, and notifications remain client-dependent. The
approval offer shows both lists. Do not infer identities or notification intent from text.
Preserve an existing native video's kind, author, stable d and original published_at when
editing it. Use a fresh unique d for a temporary test, with no production-address reuse.

The repository's tools/blossom.py plans offline by default and requires --apply for writes.
Keep its receipts and signed events outside source. Inspect public hashes, MIME, CORS,
range responses, actual decoded frames and signature-verified relay readback. Record
partial failures per destination. Do not infer video playback from relay acceptance.

Cleanup sends a same-author kind-5 request targeting only the exact test IDs/address, then
queries every contacted relay to verify absence and retrieval of the deletion event.
Blossom deletion is separate and must use the upload receipt, selected server and expected
public key. Never delete a reused/pre-existing blob. Keep deletion evidence; public copies
and caches elsewhere cannot be guaranteed erased.

The reusable complete video publisher and AV1/HLS packager are documented in the
[production runbook](../../docs/production.md). Use `produce.py package` and guarded
`publish.py nostr` with exact-packet approval from the actual trusted channel:
controller-authenticated Marmot or the documented direct operator path. The
bounded five-second test-event builder is only an access check.
