# Rendered caches by web origin

`2026/11/web-cache-origins` is an independent v1.15.6 topic. It requires no other local feature. The machine-readable catalog records prepared documentation updates
separately from previously verified published revisions.

Cached pages, RSS and map-marker output append an origin hash to their existing
keys. Model/query caches retain their shared namespace. Existing key prefixes
are retained, so podcast, episode, comment and page invalidation reaches every
origin. Map-marker invalidation also removes every origin variant.

This topic provides no domain redirects, branding, sitemap, transcript indexing,
video, feed-range support or media changes. It is useful on its own for aliases
and multi-host installations. Configure native request URL generation separately.
The podcast-domains topic uses this as its only prerequisite. No migration,
frontend build or new dependency is required.

Standalone validation passed 5 tests/27 assertions, including two-host RSS output
with stable episode GUIDs, wildcard cache separation and actual episode-model
invalidation. The complete topic combination passed 54 tests/325 assertions.
Checks used synthetic fixtures, isolated dependencies and disposable databases.
Instance deployment state is tracked privately; source validation does not
establish installation.
