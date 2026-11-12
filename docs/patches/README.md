# Castopod, Nostube and Marmot patches

This is the canonical patch catalog for
[sovereign-podcaster](https://github.com/Sjors/sovereign-podcaster).
It supersedes the [original gist](https://gist.github.com/Sjors/edd59acfb4ea1a83978f5d22e630e92c).
Patch implementation remains in the upstream projects and maintained forks;
no production backups, credentials or private deployment records are stored here.
See [maintenance and reproduction](maintenance.md) for pinned source, licensing,
upgrade protections and the transition from the gist.

These branches support a self-hosted podcast with audio, transcripts and Nostr video.
They are maintained in [Sjors/castopod](https://github.com/Sjors/castopod) and
[Sjors/nostube](https://github.com/Sjors/nostube). Links follow branch names to
track maintained versions.

## Castopod

All topics target Castopod v1.15.6. Choose the features needed for an instance;
only the two dependencies listed below are required. Homepage preview and sitemap
optionally use the domain configuration when present, without requiring it.
Castopod contributions belong on its [official GitLab](https://code.castopod.org/adaures/castopod);
the GitHub fork shares these maintained topics.

| Branch | Purpose | Required topic |
| --- | --- | --- |
| [2026/10/audio-file-size](https://github.com/Sjors/castopod/commits/2026/10/audio-file-size) | Read the actual size of local audio, retaining stored-size fallback for missing files and other storage backends. | None |
| [2026/11/audio-mime-type](https://github.com/Sjors/castopod/commits/2026/11/audio-mime-type) | Normalize known M4A audio MIME aliases to `audio/x-m4a`, matching Apple's RSS guide and common HTTP servers, while preserving stored metadata. | None |
| [2026/10/feed-artwork](https://github.com/Sjors/castopod/commits/2026/10/feed-artwork) | Encode feed artwork in the advertised format, without transparency, preserving originals and other derivatives. | None |
| [2026/10/rss-byte-ranges](https://github.com/Sjors/castopod/commits/2026/10/rss-byte-ranges) | Serve byte ranges of generated RSS with correct lengths, UTF-8 offsets and unsatisfiable-range handling. | None |
| [2026/11/sitemap](https://github.com/Sjors/castopod/commits/2026/11/sitemap) | List public pages, shows, episodes and available transcripts. Cache by origin; optionally apply domain selection. Includes adapted upstream [MR !375](https://code.castopod.org/adaures/castopod/-/merge_requests/375) with its authorship. | None |
| [2026/11/transcript-indexing](https://github.com/Sjors/castopod/commits/2026/11/transcript-indexing) | Give real transcript pages their own canonical, title, description and WebPage metadata while retaining their PodcastEpisode association. | None |
| [2026/11/episode-video](https://github.com/Sjors/castopod/commits/2026/11/episode-video) | Add optional contextual Nostr video metadata and Video / Audio / Comments tabs, retaining the normal player for other episodes. Includes paused-audio behavior and admin/CLI controls. | None |
| [2026/11/homepage-preview](https://github.com/Sjors/castopod/commits/2026/11/homepage-preview) | Configure homepage title, alternate name, visible introduction and WebSite identity. Optionally use the domain topic's hub identity. | None |
| [2026/11/episode-seo](https://github.com/Sjors/castopod/commits/2026/11/episode-seo) | Backport episode/transcript title, escaping, Open Graph, document-language and embed indexing fixes. | `2026/11/transcript-indexing` |
| [2026/11/web-cache-origins](https://github.com/Sjors/castopod/commits/2026/11/web-cache-origins) | Separate rendered pages, RSS and map-marker caches by origin while retaining shared model caches and cross-origin invalidation. | None |
| [2026/11/podcast-domains](https://github.com/Sjors/castopod/commits/2026/11/podcast-domains) | Configure a hub identity and optional per-show web domains alongside nginx routing, preserving stored federation identity. | `2026/11/web-cache-origins` |

The [source snapshot](../../patches/catalog.json) records prepared and previously
verified published revisions separately. Documentation-only updates awaiting
publication are marked as prepared. See the [subset-validation record](topic-publication.md)
for dependency combinations and reproducible source checks.

Integration branches are not publication units. Deployment state, instance
configuration, inventories, approvals and rollback evidence stay in private
maintenance records. Preparing or publishing a topic does not deploy it.

The video topic requires matching rebuilt frontend assets, a static player and
its route. Preserve these when installing compatible topics. The
[audio delivery notes](audio-delivery.md) cover MIME and compression compatibility.

## Nostube

| Branch | Purpose | Dependency |
| --- | --- | --- |
| [2026/11/embed-event-verification](https://github.com/Sjors/nostube/commits/2026/11/embed-event-verification) | Verify a fetched video's signature and requested event ID/address instead of trusting a relay to obey its filter. Includes forged-event and wrong-identifier cases. | Upstream main |
| [2026/11/embed-channel-player](https://github.com/Sjors/nostube/commits/2026/11/embed-channel-player) | Build a standalone static player for hosting under a path such as `/video/`, with an optional build-time author allowlist and fixed relays. Reject a foreign address before contacting relays; URL parameters cannot override deployment policy. | Event verification |
| [2026/11/embed-return-link](https://github.com/Sjors/nostube/commits/2026/11/embed-return-link) | Add an optional same-origin HTTP(S) return link. Keep the validated absolute URL so a path beginning `//` cannot turn into navigation to another host. | Upstream main |
| [2026/11/ios-av1-capability](https://github.com/Sjors/nostube/commits/2026/11/ios-av1-capability) | Check the actual AV1 MIME/codec configuration with browser capability detection instead of rejecting AV1 on all iOS devices. Retain other compatibility checks and let the playback engine evaluate parameterized HLS MIME types. | Upstream main |

The channel-player branch includes the event-verification prerequisite. Apply that
prerequisite once; when it lands upstream, rebase the channel topic accordingly.
The return-link and AV1 topics are parallel. An AV1 capability check does not establish
that every Safari/iOS device supports the codec. Test playback on the intended devices.

## Maintaining the canonical catalog

When a topic is added, renamed, merged upstream, replaced or retired, update this
file and [the published source snapshot](../../patches/catalog.json) together.
This repository is the canonical catalog; the original gist is a legacy entry point. Keep links based on branch names and
describe behavior, dependencies and any release-specific requirements. Recheck upstream
issues, open/closed contributions and actual code before dropping a patch.

Detailed validation, exact deployed revisions, backups and rollback records are kept
in the instance's maintenance records. This catalog is a guide to the maintained topics,
not a deployment manifest. Preparing or publishing branches does not deploy them.

## Marmot incoming message identity

The local [bridge patch](../../patches/marmot-message-context.patch) adds incoming
message/sender IDs to turn-local backend environment context for
`marmot-protocol/mdk` tag `wn-agent-v0.14.0` (MIT). It supports authenticated
reply deduplication and exact review approval. It also recognizes the backend's
explicit `adapter.silent` event so successful internal turns do not generate a
"produced no text output" reply. Empty output without that event, backend errors
and uncertain deliveries retain their existing handling. The [build/install guide](../../adapters/marmot/message-context.md)
records dependencies, tests, source pin and rollback requirements. The source
snapshot above records its SHA-256. Check upstream for this functionality before
updating/removing the patch; other accounts' installed bridges are not replaced.
