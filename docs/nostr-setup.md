# Nostr identity, relays and Blossom

The agent prepares and signs publications as the isolated Linux user. A relay
stores events; a Blossom server stores media. **Working access to both is a
prerequisite for video publication.** The default topology has a separate agent
machine and hosting machine. Signing, WSS and HTTPS need no hosting SSH credential.
Use SSH only for separately authorized server administration or private transfer.

Keep the identity, destination configuration, signed events, upload receipts and
verification/deletion records outside this repository. The public key/npub is
public; `secret.hex` controls the account. Do not paste it into chat, prompts,
arguments, shell history, logs or a skill. OpenAI keys are unrelated to Nostr keys.

## Hosting prerequisites

Self-hosting both services gives you a destination whose policy and retention you
control. Use dedicated service accounts on the hosting machine, not the agent's
account. Keep server administration and database credentials off the agent.

For a relay, [strfry](https://github.com/hoytech/strfry) is an option; its
[write-policy plugin interface](https://github.com/hoytech/strfry/blob/master/docs/plugins.md)
supports author allowlists. Add the show's **public** key to the existing write
allowlist without removing existing entries. Keep public reads available if the
podcast is public. Verify handling of kinds 0, 1, 5, 10002, 10063 and 34235, including
exact-ID reads and NIP-09 deletion. npub is the human-facing form; convert to hex
if the server's configuration requires it. Never put the secret on the server.

For media, [Route96](https://github.com/v0l/route96) supports Blossom uploads,
whitelists, quotas and byte ranges. Follow the selected release's upstream setup
and backup instructions; do not assume allowlist syntax across releases. Whitelist
the same npub/hex identity for authenticated uploads and test deletion access.
Use HTTPS, public GET/HEAD, correct MIME, CORS for your player/website, and MP4
byte ranges. Verify upload limits, persistent storage, monitoring and backups.
Neither this guide nor the smoke check installs/upgrades hosting services.

Also select independent relays. Examples include `wss://nos.lol` and
`wss://relay.primal.net`; `wss://relay.damus.io` or a video client's relay may be
useful after checking their policies. Keep per-destination acceptance/readback
records: public services can reject, require authentication/payment, or disappear.
Do not bypass policy or silently pay. Metadata-only relays are not general video
or kind-1 destinations. For an existing account preserve its relay-list event;
using an extra test relay does not authorize replacing that list.

Additional Blossom servers can hold identical bytes as mirrors. Choose them
explicitly, check quotas/access/deletion terms, and verify every copy. A second
quality rendition is a different blob, not a same-hash mirror. This setup tests
the existing self-hosted storage and multiple event relays; it does not promise
another operator's storage or universally reliable erasure. For example,
[blossom.band](https://blossom.band/) currently documents free video uploads up to
20 MiB and authenticated deletion; verify its current limits/terms before use.

## Runtime

Tested on **Ubuntu 26.04.1 LTS, x86-64**. System Python 3.14.4 still runs the offline
slide tool. The Nostr runtime uses an independent **CPython 3.11.17**, uv **0.13.1**,
coincurve **21.0.0**, websocket-client **1.9.2**, bech32 **1.2.0** and FFmpeg
**8.0.1-3ubuntu2**. Do not point the isolated user at the operator's Python or venv.

Administrator prerequisites:

```sh
sudo apt install --no-install-recommends \
  python3 python3-venv ca-certificates ffmpeg git coreutils bash openssh-client tar
# Optional source inspection used during maintenance:
sudo apt install --no-install-recommends ripgrep python3-yaml
```

FFmpeg includes ffprobe; coreutils supplies install/chmod/stat/sha256sum/ln/date.
SSH/tar are for cross-account or cross-machine migration; skip them when unnecessary.
uv is installed as a pinned PyPI wheel in a private bootstrap venv, rather than an
unavailable apt package. It downloads the account's own
[python-build-standalone runtime](https://docs.astral.sh/uv/guides/install-python/).
No sudo, shared SSH agent or existing authentication directory is needed.

As the isolated user, from a clean shell with the previously documented private
home/artifact permissions:

```sh
umask 077
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/tools/setup_nostr_runtime.py"
SP_NOSTR_PY="$HOME/.local/share/sovereign-podcaster/nostr-venv/bin/python"
SP_PUBLISH="$SP_REPO/skills/nostr-publishing/scripts/nostr_publish.py"
"$SP_NOSTR_PY" -m unittest discover -s "$SP_REPO/skills/nostr-publishing/tests" -v
```

The setup command installs only wheels, pins the interpreter/libraries, writes a
private runtime lock, and checks rather than replaces an existing Nostr venv.
An incompatible existing environment stops setup for inspection. Paths can be
changed with `--root`; update SP_NOSTR_PY accordingly. The libraries carry their
own licenses; see [provenance](provenance.md).

Direct installation of coincurve 21.0.0 into Python 3.14 failed with an upstream
CFFI license-location build error, tracked in
[coincurve #219](https://github.com/ofek/coincurve/issues/219). The tested 3.11 wheel
avoids that build; no custom cryptographic source patch is installed. Preserve
this compatibility note and reassess upstream support before changing the pin.

## Fresh identity or existing identity

For a **new** show, choose a private directory outside every Git checkout:

```sh
SP_IDENTITY="$HOME/.config/nostr-publishing/identities/my-show/identity.json"
"$SP_NOSTR_PY" "$SP_PUBLISH" init \
  --directory "${SP_IDENTITY%/identity.json}" --name 'My Podcast' \
  --relay wss://relay.example.org --relay wss://nos.lol
"$SP_NOSTR_PY" "$SP_PUBLISH" public --identity "$SP_IDENTITY"
```

This creates a CSPRNG-generated identity in a 0700 directory with 0600 files. It
refuses existing keys, symlink destinations and Git directories. It prints only
the public identity. Back up the secret securely using your normal secret-manager
procedure; verify recovery without exposing it. Whitelist the returned public key
on the selected relay and Blossom service before uploading/publishing. Creation
is local and does not publish profile/follows/relay/storage metadata.

For an **existing** show, reuse its identity. Transfer only `identity.json` and
`secret.hex` through an authenticated encrypted connection, with independently
verified SSH host keys and agent forwarding disabled. Confirm the config uses
the relative `key_file` value `secret.hex` before copying. Do not transfer a home,
chat history, unrelated identities or service-administration credentials.

Example from the old account, after setting up a dedicated SSH alias as in the
[Linux setup guide](setup-linux.md). Replace account/show paths deliberately:

```sh
set -o pipefail
SP_OLD_IDENTITY="$HOME/.config/nostr-publishing/identities/my-show"
tar -C "$SP_OLD_IDENTITY" -cf - identity.json secret.hex | \
  ssh -o IdentityAgent=none -o ForwardAgent=no -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes agent-account \
    'umask 077; set -eu
     target="$HOME/.config/nostr-publishing/identities/my-show"
     test ! -e "$target" && test ! -L "$target"
     mkdir -p "${target%/my-show}"
     mkdir -m 700 "$target"
     tar --no-same-owner --no-same-permissions -xf - -C "$target"
     chmod 600 "$target/identity.json" "$target/secret.hex"'
```

Inspect a partial destination before retrying; do not overwrite it automatically.
On the new account compare `public` output with the existing npub/hex key, and
sign a local event to prove the private key derives that exact public key. Validate
relay/storage access before proposing retirement of old access. Keep old access
working until replacement has passed. A copied secret leaves both accounts able
to sign; deleting a local copy later does not rotate the identity. Keep an encrypted
recovery backup and retire only the selected old show identity after authorization.
After retirement, leave a nonsecret `MIGRATED.json` in the old identity directory,
recording the replacement account/path and verified public key. The shared signer
and initializer refuse that directory so a stale workflow cannot reuse or
silently regenerate the retired identity. Keep other identities working.

Store paths and selected destinations in a 0600 private instance file, conventionally
`$HOME/.config/sovereign-podcaster/nostr.json`; adapt
[the example](../examples/nostr-config.json). Never put the secret itself there.
Use the expected public key for every mutation, not just the first connection.

## One canonical skill copy

Both skills live in this repository: `skills/nostr-publishing` and
`skills/fetch-nostr-events`. For an account whose discovery root is `$HOME/skills`,
add links when those names are free (existing links require inspection first):

```sh
mkdir -p "$HOME/skills"
ln -s "$SP_REPO/skills/nostr-publishing" "$HOME/skills/nostr-publishing"
ln -s "$SP_REPO/skills/fetch-nostr-events" "$HOME/skills/fetch-nostr-events"
```

Use the harness adapter's capability directory instead if applicable. Keep
host-specific article/show defaults in private source-workflow configuration.
There should be one maintained implementation, not separately edited dev/executor
copies. The executor's checkout follows the [private source-sync procedure](executor-sync.md);
another operator can clone the published repository read-only. Configure each
machine's links to its own checkout, including when syncing to a Mac with different paths.

## Temporary five-second publication check

Run these as the isolated user **only when this exact post/upload/delete check is
authorized**. This is a real public test under the selected identity. The initial
setup grants no standing publication permission. Keep all output in a new private
run directory under your artifact root, and record the source file's path/hash,
selected offset, exact FFmpeg command and authorization in that run.

Set SP_SOURCE to an explicitly selected existing video, SP_RUN to a fresh private
run, SP_SERVER/SP_RELAY to approved destinations, SP_PUBKEY to the configured hex
key and SP_IDENTITY to its private config. For example:

```sh
umask 077
SP_ARTIFACT_ROOT=/srv/sovereign-podcaster
SP_TEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
SP_RUN="$SP_ARTIFACT_ROOT/work/nostr-test-$SP_TEST_ID"
mkdir -m 700 "$SP_RUN"
# Set these to your source and approved destinations before continuing.
SP_SOURCE=/absolute/path/to/selected-episode.mp4
SP_SERVER=https://media.example.org
SP_RELAY=wss://relay.example.org
SP_PUBKEY=REPLACE_WITH_HEX_PUBLIC_KEY
SP_ORIGIN=https://podcast.example.org

ffmpeg -nostdin -n -ss 200 -i "$SP_SOURCE" -t 5 \
  -map 0:v:0 -map 0:a:0 -map_metadata -1 -map_chapters -1 \
  -c:v libsvtav1 -preset 10 -crf 32 \
  -svtav1-params lp=2 -pix_fmt yuv420p -r 15 -c:a aac -b:a 64k -ac 1 \
  -movflags +faststart -metadata comment="temporary access check $SP_TEST_ID" "$SP_RUN/clip.mp4"
ffmpeg -nostdin -v error -i "$SP_RUN/clip.mp4" -f null -
sha256sum "$SP_SOURCE" "$SP_RUN/clip.mp4"

"$SP_NOSTR_PY" "$SP_REPO/tools/nostr_test_events.py" prepare \
  --file "$SP_RUN/clip.mp4" --pubkey "$SP_PUBKEY" --server "$SP_SERVER" \
  --source-label 'Selected episode' --out "$SP_RUN/events"
```

The encoder touches only the excerpt. The event builder requires an AV1/AAC MP4
of five seconds, gives the native kind-34235 video a unique test address and
creates a separate kind-1 announcement with matching media metadata. It leaves
production video addresses, profile/relay/storage lists and host mentions alone.
Review both unsigned JSON files before signing. Use `--source-url` for the canonical
episode page if desired; prose precedes the final URL block. Repeat `--server` only
for explicitly selected identical-byte mirrors, and upload/verify every one.

First plan the upload, then apply after reviewing its bytes, identity and destination:

```sh
"$SP_NOSTR_PY" "$SP_REPO/tools/blossom.py" upload \
  --file "$SP_RUN/clip.mp4" --server "$SP_SERVER" --origin "$SP_ORIGIN" \
  --identity "$SP_IDENTITY" --expected-pubkey "$SP_PUBKEY" \
  --receipt "$SP_RUN/upload.json"
# Repeat the same command with --apply to upload and save its receipt.
```

Upload plans are offline and do not read the key. Applied uploads sign short-lived
kind-24242 authorization scoped to the server, exact hash and action. Authenticated
requests and mutations never follow redirects. A public CDN read requires an
explicit `--read-redirect-origin https://cdn.example.org`; only unauthenticated
GET/HEAD can follow that HTTPS origin, with a short redirect limit. Hash, MIME,
CORS and ranges must still verify at the final destination. The initial public
mirror required `--read-redirect-origin https://video.nostr.build`. Current BUD-11
uses unpadded base64url; `--auth-encoding standard` is
an explicit compatibility option for older deployments. Never log either header.
The receipt records the pre-upload existence check, acknowledgement, hash/MIME,
full public readback, CORS and MP4 byte-range checks. Reuse it for a retry of the
same bytes/destination; mismatched bindings stop the command.

```sh
"$SP_NOSTR_PY" "$SP_REPO/tools/nostr_test_events.py" sign \
  --bundle "$SP_RUN/events" --identity "$SP_IDENTITY"
for SP_STEM in video note; do
  "$SP_NOSTR_PY" "$SP_PUBLISH" publish --identity "$SP_IDENTITY" \
    --relay "$SP_RELAY" --input "$SP_RUN/events/$SP_STEM.signed.json"
  # Repeat with --apply --output UNIQUE-RECEIPT.json after reviewing the plan.
done
```

Use explicit repeatable --relay arguments for all selected destinations; save
separate receipts for both events and retries. Verify each signed ID/author using
an independent exact-ID query; the companion fetcher also verifies BIP-340 with a
separate standard-library implementation. An ACK is not verified storage. Download
the public MP4, compare its full hash/size, fully decode video/audio, and inspect a
decoded frame. This demonstrates media transport, not every client's rendering or
mobile AV1 support. A thumbnail is not required for this temporary check.

## Cleanup and recovery

After sanity-checking the result, prepare/sign the deletion request:

```sh
"$SP_NOSTR_PY" "$SP_REPO/tools/nostr_test_events.py" deletion --bundle "$SP_RUN/events"
"$SP_NOSTR_PY" "$SP_REPO/tools/nostr_test_events.py" sign \
  --bundle "$SP_RUN/events" --identity "$SP_IDENTITY"
"$SP_NOSTR_PY" "$SP_PUBLISH" publish --identity "$SP_IDENTITY" \
  --relay "$SP_RELAY" --input "$SP_RUN/events/deletion.signed.json"
# Repeat with --apply and an output receipt for every contacted relay.

"$SP_NOSTR_PY" "$SP_REPO/tools/blossom.py" delete \
  --server "$SP_SERVER" --identity "$SP_IDENTITY" --expected-pubkey "$SP_PUBKEY" \
  --receipt "$SP_RUN/upload.json"
# Repeat with --apply to delete only this receipt's newly uploaded blob.
```

The event tool rejects substituted production events and targets only its bound
test IDs, kinds and unique address. It preserves already-signed events across
retries. Query **every contacted relay** afterward: require completed reads,
verified retrieval of the deletion event, absence of both original IDs and
absence of the exact native address. Then independently check the blob's bare
hash and `.mp4` alias for HTTP 404/410 on every server. A 403, failed connection or
timeout is not evidence of deletion. The deletion request itself remains public.

Some providers return a missing-media placeholder with HTTP 200 or redirects for
GET, even after an acknowledged deletion. The first public-mirror test encountered
this on blossom.band: DELETE returned 204, both origin HEADs returned 404, the
authenticated upload list was empty, and GET redirected to a generic 404 video
whose bytes differed from the test. The strict delete command deliberately did
not label that as ordinary GET-404 success. Preserve that distinction.

Use the read-only status command to collect the origin's HEAD responses and a
paginated authenticated list without exposing its authorization header:

```sh
"$SP_NOSTR_PY" "$SP_REPO/tools/blossom.py" removal-status \
  --server "$SP_SERVER" --identity "$SP_IDENTITY" --expected-pubkey "$SP_PUBKEY" \
  --receipt "$SP_RUN/upload.json"
```

It reports origin-removal evidence separately from GET absence. A complete list
without the hash, 404/410 HEADs and a saved delete acknowledgement supply the
origin evidence; unavailable/incomplete lists and 403s remain uncertain. This does
not mutate the receipt or upgrade a placeholder to strict GET-404 verification.
Retain an explicit reviewed cleanup record with these facts and cache limitations.

Blossom cleanup refuses pre-existing/reused blobs or unacknowledged uploads, and
binds server/key/hash to the private receipt. After an ambiguous upload, inspect
public bytes and retry the same upload to obtain a matching acknowledgement;
never delete another publication's shared content hash to clean up a test. Once
a receipt enters deletion, it cannot be used to re-upload. Keep local media,
signed events, source/command hashes and all receipts as evidence; remove only
the public test objects. Report partial cleanup and continue from saved state.

Neither [NIP-09](https://github.com/nostr-protocol/nips/blob/master/09.md) nor
[Blossom deletion](https://github.com/hzrd149/blossom/blob/master/buds/12.md)
can guarantee erasure of copies held by other relays, clients or caches.
Protocol references: [NIP-71](https://github.com/nostr-protocol/nips/blob/master/71.md),
[NIP-92](https://github.com/nostr-protocol/nips/blob/master/92.md),
[BUD-02](https://github.com/hzrd149/blossom/blob/master/buds/02.md),
[BUD-11](https://github.com/hzrd149/blossom/blob/master/buds/11.md).

## Instance validation records

Keep contacted relay/storage inventories, signed events, hashes, commands,
authorizations, receipt states and cleanup evidence in private run records.
Verify public bytes, signatures, MIME/CORS/ranges and decoded media, then record
event and blob cleanup separately. Tests do not establish arbitrary client
rendering or erasure of copies retained by other parties.
