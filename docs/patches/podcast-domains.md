# Podcast web domains

The publication branch `2026/11/podcast-domains` has one required prerequisite:
`2026/11/web-cache-origins`. It implements hub identity and domain selection over
that cache fix on v1.15.6. The source snapshot distinguishes prepared revisions
from previously verified publication. Instance deployment evidence stays private.

## Behavior and optional topics

Private `PodcastWeb` configuration supplies a hub root URL, optional per-show web
root URLs and hub identity. Unmapped shows stay on the hub. The homepage continues
listing every published show, including shows with dedicated web domains.

The hub name and description select its existing site-name/description metadata,
header and web manifest without overwriting dedicated-site settings. The optional
homepage-preview topic also uses the hub title, alternate name, visible introduction
and WebSite identity. Without homepage preview, those extra presentation features
are absent; basic domain identity still works.

The optional sitemap topic detects this configuration and lists only same-origin
shows, with instance-wide pages on the hub. The sitemap and homepage topics also
work on their own. Neither is a required ancestor of podcast-domains. Video,
audio-size/artwork/range fixes and transcript/episode SEO are independent choices.

nginx handles redirects and access to the shared application/media/player. Keep
native `/@handle` paths. Per-vhost FastCGI base URLs select native URL generation;
a full-class environment fallback serves CLI tasks. Each robots file advertises
its own sitemap. Generic configuration instructions live in Castopod's
`docs/development/podcast-domains.md`; instance-specific values remain private.

The cache prerequisite isolates rendered pages, RSS and map markers by origin,
retaining shared model caches and cross-origin invalidation. The domain feature
preserves stored federation identity and does not change episode GUIDs, feed
relocation fields, media locations, authentication settings or schema. Existing
main-show feed and episode URLs can remain in place. No frontend rebuild or new
dependency is required.

## Publication validation

The domain topic plus its sole cache prerequisite passed 9 tests/45 assertions
without sitemap, homepage, video or transcript/episode SEO. Its tests cover default
policy, mapped/unmapped shows, rejected non-root URLs and hub-only identity/manifest
selection. The complete topic combination passed 54 tests/325 assertions; the
optional homepage identity and domain-filtered sitemap were exercised there.
The standalone cache, homepage and sitemap results are listed in
[the publication record](topic-publication.md).

The full combination requires two deliberate metadata-helper resolutions when
mixing domain changes with episode SEO and homepage preview. Retain those topics'
canonical, escaping, Open Graph and WebSite behavior while selecting the domain's
site name. These resolutions were validated privately; combined source is excluded
from the Mac publication list.

The generic upstream [custom-domain MR !376](https://code.castopod.org/adaures/castopod/-/merge_requests/376)
was reviewed. Its hub-listing and federation-domain policy differs from the
requested behavior; none of that actor migration was imported. Recheck upstream source when maintaining this feature for later releases.

## Deployment checks

For an authorized installation, preserve configuration ownership and symlinks,
episode/feed/federation identities, media and unrelated source changes. Verify
HTTPS routing, hub/show identity, feeds and ranges, transcript canonicals, player
routes, robots and sitemaps. Keep before/after inventories and verified backups
privately. Rollback must preserve newer episode work and media.
