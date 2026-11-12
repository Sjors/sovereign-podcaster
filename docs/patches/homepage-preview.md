# Homepage search appearance

Branch `2026/11/homepage-preview` is independent on Castopod v1.15.6. It includes
configurable homepage appearance and optional domain-identity support. The
source snapshot distinguishes prepared documentation updates from previously
verified published revisions.

## Behavior

- `App.homeTitle` optionally supplies a descriptive homepage/browser title while
  `App.siteName` remains the short name. Empty titles fall back to the site name.
  Title and alternate name are editable in General settings; older clients that
  omit the added fields preserve their existing values.
- One WebSite JSON-LD node identifies the site name and canonical root. A distinct
  alternate name is optional. Canonical/Open Graph URLs use the root on sorted
  homepage variants; Open Graph type is website.
- The description appears above the podcast list as escaped plain text. Metadata
  is escaped once. Existing site-icon settings provide favicon/mobile/social
  artwork; per-instance artwork and copy are deployment data.
- If the optional `web_site_setting()` provider from podcast-domains is present,
  `site_identity_setting()` selects the hub identity for the homepage metadata
  and visible introduction. Without it, native settings provide the same values
  as before. The domain topic is not required.

No podcast/episode/feed schema, single-podcast redirect, dependency or frontend
build changes are introduced by this topic. Its optional provider does not pull
video, domain configuration, sitemap or transcript/episode SEO into its history.

## Validation

The standalone topic passed 8 tests/27 assertions on PHP 8.3.6 and PHPUnit
10.5.63 with a disposable MariaDB database. Tests retain visible plain-text,
escaping, canonical, WebSite and alternate-name cases with synthetic settings and
a mocked asset service. The complete topic combination passed 54 tests/325
assertions, including the hub identity provider. Exact source pins and check
results are in the source snapshot and publication record.

Deployment records and instance branding remain private. After an authorized
installation, verify hub/show identity and preserve site icons, feeds, audio and
transcripts. Published source alone does not establish deployment.

Upstream alternatives were reviewed during preparation: the current homepage
behavior was not supplied by the SEO MR series. Preserve this behavior and check
current upstream source before carrying or retiring the patch in a later upgrade.
Google chooses its own displayed title/snippet and may take time to recrawl.
