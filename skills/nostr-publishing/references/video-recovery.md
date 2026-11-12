# Native video storage, playback and recovery

## Establish usable destinations before bulk upload

Inspect the configured identity, current controls, relay availability and each
selected storage provider's supported MIME types and per-file limits. An HLS
bundle contains playlists, initialization MP4s, media segments and a separate
fallback; acceptance of a normal MP4 does not imply acceptance of every asset.
Compare limits with the actual largest file, not the average six-second segment.
Use read-only upload/capability checks when supported before a large batch.

On 2026-11-06, blossom.band documented a 20 MiB free-upload limit and rejected
the attempted HLS segment uploads; the approximately 60 MB fallback also exceeded
the free-file limit. Treat that as an observed compatibility problem, not an
evergreen service guarantee. Recheck the provider's current documentation and
terms. Do not evade limits with false MIME types, silently buy access or advertise
an unverified copy. Self-hosted storage was sufficient for that authorized release;
an additional mirror is not intrinsically required by the protocol.

If a configured optional destination is unusable, inspect effects and the actual
authorized scope before selecting a supported subset or alternative. Preserve
failed/uncertain receipts, update the destination/configuration binding honestly,
and honor any user requirement for a particular destination or redundancy level.
Do not silently weaken a required mirror policy or change the NIP-65 relay list
merely because one release relay is temporarily unavailable.

## Keep transport stages resumable

Upload content-addressed leaves first, dependent playlists next and the master
last. Independent leaves can use bounded workers with distinct durable receipts
and a common stage lock; wait for them before advertising playlists. Stop new work
after failure and inspect outcomes. Verify hashes, MIME, CORS for each playback
origin, byte ranges where applicable, the advertised `.m3u8` master URL and the
extensionless URLs resolved by relative child references.

Keep a durable storage checkpoint before attempting relay delivery. A relay
timeout after successful storage verification should resume the exact saved event,
not repeat all uploads or generate a fresh timestamped announcement. Validate the
checkpoint against the current manifest, destination binding, complete per-asset
receipts and public-readback evidence before reuse. If the available publisher
cannot resume a partial stage safely, fix that gap under maintainer authorization
while retaining state; do not manufacture a verified receipt.

Inspect exact signed event IDs on every selected relay after a lost response.
Republish the same ID only where still needed. A longer bounded network timeout
can address a diagnosed connection problem; repeated blind retries are not a
substitute for diagnosis. Record partial acceptance accurately. Preserve a native
video's author/kind/d/first published_at when intentionally updating its address.

If saved events need to change before their first publication (for example an
unsupported storage origin must be removed), establish that neither saved ID was
published before archiving/replacing them. If already published, follow the normal
address-update rules. Keep prior events and bindings as provenance.

## Verify the client and the requested publication order

Test decoded frames and seeking in the actual native-video player and Castopod
embed, not just blob checks or relay OKs. Inspect which source actually plays.
A client may choose the 480p MP4 despite an available 720p HLS source; select the
HLS option and inspect decoded dimensions/frames before claiming its playback.
Nostube labelled that stream “Quality 2” in the observed release. This is a client
display observation, not a stable name to hard-code or proof that HLS is absent.

Native video, Castopod linkage and kind-1 announcement are distinct effects.
When the user requests that order, record verified native media/event readback,
update and verify the existing episode's matching naddr, then publish the short
announcement to that same stable address. Keep the video-event reference and
announcement notification tags explicit. Private/public YouTube follow under
the actual task authorization, not automatically because a Nostr post succeeded.
