# Audio delivery compatibility

The `2026/11/audio-mime-type` topic targets Castopod v1.15.6 and has no required
topic dependency. The owner published its signed commit on 2026-11-04. Its source pin
is in [the source snapshot](../../patches/catalog.json). Deployment state is private.

The audio entity returns `audio/x-m4a` for `.m4a` files whose stored MIME type is
`audio/mp4` or `audio/m4a`. This aligns enclosures and trailers with Apple's
[RSS tag guide](https://help.apple.com/itc/podcasts_connect/en.lproj/itcb54353390.html)
and the HTTP type commonly used by nginx. Extension matching is case insensitive.
Other extensions, unknown types and video types retain their stored values.
The getter leaves database metadata and media bytes unchanged and covers imported
records as well as future uploads.

Eight focused regression cases passed. The exact deployment source also passed
the existing audio-size cases: 13 tests, 36 assertions, PHP syntax, ECS style and
targeted PHPStan analysis. The test dependencies and fixtures were separate from
production configuration, media and databases.

## Companion nginx configuration

Remove `audio/mpeg` from the affected virtual hosts' explicit `gzip_types` lists.
MP3 is already compressed. With gzip enabled for that MIME type, the observed
server returned a compressed full response without Content-Length or Content-Range
when the client requested a byte range. Identity-encoded requests worked already.
The change preserves the existing routes and compression settings for other types.

The complete inspected virtual-host configurations passed isolated syntax and
request checks using synthetic files and stubbed application handling. There were
120 media checks and 20 routing checks across both hosts and before/after states.
These reproduced the compression issue, verified audio HEAD/GET and initial,
suffix and unsatisfiable ranges, and preserved transcript delivery and routing.
These isolated checks do not establish that the production nginx configuration
has been installed or reloaded.

An administrator must install this server configuration change. The prepared
installer checks source hashes, preserves original files, tests the full nginx
configuration and reloads only after validation. The application repair preserves
the existing audio-size patch and invalidates rendered feed caches across origins
and client variants. Private rollback and deployment evidence stay outside Git.

## Deployment verification

After an authorized installation, verify all selected public enclosures with
HEAD, MIME/length and initial/suffix/unsatisfiable ranges, using identity encoding
and a gzip offer. Compare normal and client-specific feeds, transcript hashes,
legacy routes and unrelated source files against private baselines. Preserve
media, database records and episode identity. Keep inventories, exact deployed
revisions, administrator actions and rollback evidence outside Git.

## Upstream and Apple limits

The official upstream main/develop audio entities and matching open/closed issues
and merge requests were checked on 2026-11-04. Merged MR !164 and issue #496 concern
upload validation; closed MR !369 concerns player/media range handling. They do not
provide this MIME getter or repair the local nginx gzip configuration.

Public RSS/audio/transcript checks cannot establish that Apple has ingested each
historical transcript. These repairs do not claim to resolve that separate
ingestion delay, and do not alter transcript contents, episode identities or
Apple Podcasts Connect settings.
