# Independent Castopod topics

The source targets v1.15.6. The table describes topic behavior and dependencies.
The catalog distinguishes prepared documentation updates from previously
verified published source. Signing-only history differences do not change
source behavior.

| Branch | Change | Required Castopod topic |
| --- | --- | --- |
| `2026/11/web-cache-origins` | Extract the general multi-origin rendered-cache fix into one independent commit. | None |
| `2026/11/podcast-domains` | Publish hub identity and optional per-show web-domain configuration without the former full-integration ancestry. | `2026/11/web-cache-origins` |
| `2026/11/homepage-preview` | Add an optional identity-provider hook while preserving standalone homepage settings/schema behavior. | None |
| `2026/11/sitemap` | Add origin-separated sitemap caching and optional domain selection to the published sitemap topic. | None |

The other six Castopod feature implementations are unchanged: audio-file-size, feed-artwork,
rss-byte-ranges, transcript-indexing, episode-video and episode-seo. Signing-only differences in local preparations do not require feature resyncs.
Episode SEO continues to require transcript-indexing; the other original topics
have no Castopod prerequisite.

Each topic retains a focused feature history. Documentation cleanups preserve
application behavior and upstream sitemap/SEO attribution.

## Documentation policy

Branch docs cover behavior/configuration and link here for dependencies. Commit
hashes remain in the machine-readable catalog and private records. Application
and test files are unchanged by this cleanup.

The source snapshot labels unverified documentation-only revisions as prepared
and retains the previously verified published source separately.

## Optional features and combinations

The domain topic works without homepage preview, sitemap, video or transcript/
episode SEO. Its hub name/description affect the existing site presentation.
Homepage preview optionally adds the descriptive title, alternate name, visible
introduction and WebSite schema. Sitemap optionally selects the shows served on
each host. When the domain provider is absent, both topics retain their standalone
behavior. Sitemap performs its own origin-aware caching without requiring the
rendered-cache topic.

Features touching the same metadata helper need deliberate merging. In the
validated full combination, two overlaps in `app/Helpers/seo_helper.php` were
resolved by retaining episode SEO's canonical/Open Graph behavior and using the
domain site's name, and retaining homepage preview's WebSite metadata with its
optional identity hook. Do not replace the episode canonical or homepage schema
with their older upstream forms when resolving those overlaps.

## Validation

Tests ran against isolated source/dependency copies and disposable loopback
MariaDB databases, without production credentials or media.

| Selected topics | Tests | Assertions | Notes |
| --- | ---: | ---: | --- |
| Cache only | 5 | 27 | Includes core health checks. |
| Domain plus its cache prerequisite | 9 | 45 | No sitemap/homepage/video/SEO prerequisites. |
| Homepage preview only | 8 | 27 | Existing escaping and schema cases retained. |
| Sitemap only | 11 | 38 | One optional-domain integration case skips when that provider is absent. |
| Full combination | 54 | 325 | Optional-domain sitemap case runs; no skips. |

The new subset tests cover origin isolation, unchanged GUIDs, real model-cache
invalidation, hub identity/manifest selection, standalone sitemaps and optional
domain selection. The full combination retains the existing SEO, transcript,
RSS ranges and media regressions. PHPStan, Rector dry-run, ECS and PHP syntax checks passed on each changed
standalone topic. Exact source pins and private maintenance evidence record the
final inputs. The two combined metadata resolutions retain the inherited video
controller layout; no combined branch is proposed for publication.

## Publication and deployment state

Publish individual topics; keep combination tests in disposable local worktrees.
The source snapshot distinguishes prepared revisions from previously verified
published tips. Deployment state, source bundles, inventories and recovery
records stay private. Publication does not imply installation.

Update `docs/patches/README.md` and `patches/catalog.json` together when changing
these topics. Describe behavior and dependencies using branch names and retain
exact source revision pins in the catalog.
