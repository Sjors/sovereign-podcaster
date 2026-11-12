# Discovery patches replayed with episode video

This historical integration was prepared on 2026-11-02 for Castopod v1.15.6.
The `2026/11/transcript-discovery-integration` branch combines episode-video with
audio-file-size, feed-artwork, RSS byte ranges, sitemap and transcript indexing.
The individual topics remain the publication units; integration refs are retained
for deployment provenance and excluded from further Mac publication.

The source snapshot records exact versions and replay inputs for reproducibility.
Unchanged replays retained both UTC timestamps. Human-facing documentation uses
branch names and release versions rather than embedding commit hashes.

Both overlapping files merged cleanly: `app/Config/Routes.php` and
`app/Controllers/EpisodeController.php`. Range comparisons show the sitemap and
transcript patches are equivalent to their published sources. The video controller,
navigation, iframe templates and paused-audio JavaScript retain the video topic's
behavior; the transcript controller uses its own canonical metadata. Video, Audio
and Comments still use episode metadata. The sitemap includes the canonical episode
URL and any attached transcript, without creating duplicate Audio/Comments entries.

Validation uses a disposable source/dependency copy with the locked v1.15.6
dependencies and a temporary loopback MariaDB database. No production configuration,
database, media or cache is used. PHP is 8.3.6 and PHPUnit is 10.5.63.

The combined `tests/unit` and `tests/modules/Media` run passed: **35 tests,
193 assertions**. PHP syntax checks passed for application controllers, config
and episode templates. PHPStan passed on the discovery controllers/helper/tests.
ECS and Rector dry-run passed on the sitemap routes/controller, SEO helper and
discovery tests. Full-controller checks also report pre-existing video formatting
and an unused `RedirectResponse` import; both checks reproduce on the unchanged
video controller baseline. ECS crashes in its line-length fixer on the unchanged
transcript template. These findings prevent claiming a clean whole-file style
run; the replay leaves those source topics unchanged. This run does not cover
the complete application database/API suite or a new browser playback test.

## Deployment requirements

The video topic requires its matching frontend build, static player, route and
persisted contextual settings. Preserve independent deployed changes. After an
authorized installation, verify sitemap/robots discovery, distinct episode and
transcript canonicals, feeds and unchanged media/transcripts, plus video decoding,
seeking, controls, mobile layout and channel restriction. Keep deployment source,
inventories, backup locations and operational records private.
