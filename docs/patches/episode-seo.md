# Episode search appearance

Branch `2026/11/episode-seo` builds on `2026/11/transcript-indexing` and does not
require homepage preview. The source snapshot records prepared and previously
verified published revisions separately, with upstream MR provenance.

## Review and resulting behavior

Episode, transcript and embedded-player checks must preserve their distinct
canonical URLs, transcript links and schema associations.

The patch adds the podcast name after the episode title, retaining the transcript
prefix. It supplies missing Open Graph URL/type, and uses each page's canonical
as its social URL. Descriptions, site names and artist metadata are escaped once;
stored HTML entities are decoded before encoding the plain description. Schema
descriptions use the same plain text, without changing stored shownotes or feeds.

Podcast document language follows the podcast's language, preserving UI/player
localization. The public samples were already English, so the source issue is
tested using French UI requests with English content. Dutch is not enabled as
a website interface locale by this release's default configuration; Google
language preferences do not themselves change the document language.

The embedded player sends `noindex, indexifembedded` in both HTTP and HTML,
including cached responses. Regular episodes and transcripts retain their
indexing behavior. Existing audio/video integration and media remain unchanged.

## Provenance and limits

The five adapted commits retain Progi1984's authorship, original subjects and
individual `Backport of adaures/castopod!N` attribution. The source branch's
`docs/development/episode-seo.md` explains each adaptation. MRs
[!377](https://code.castopod.org/adaures/castopod/-/merge_requests/377),
[!382](https://code.castopod.org/adaures/castopod/-/merge_requests/382),
[!380](https://code.castopod.org/adaures/castopod/-/merge_requests/380),
[!381](https://code.castopod.org/adaures/castopod/-/merge_requests/381) and
[!385](https://code.castopod.org/adaures/castopod/-/merge_requests/385) remained
open when inspected. These are stable-release adaptations, not claims that
the upstream fixes are released. The stable MetaTags library is retained;
develop's HtmlHead service and unrelated SEO helper changes are not imported.

Stored episode titles, shownotes, GUIDs, publication dates, feeds, media and
transcript files are unchanged. Shownote editing is a separate editorial task.
Existing useful descriptions should not be subjected to arbitrary truncation.

## Validation

Standalone unit/render checks passed with **8 tests, 54 assertions**. A detached
integration of current published discovery/video source, the homepage-preview
patch and the final episode changes passed **45 tests, 256 assertions** across
`tests/unit` and `tests/modules/Media`. The final test copy and source trees were
checked after metadata-only history cleanup. The combined tree is pinned in the
source snapshot, and the original maintained topic branches were preserved.

Testing used PHP 8.3.6, PHPUnit 10.5.63 and a disposable loopback MariaDB database.
Rendered HTTP fixtures use synthetic data, explicit HTML requests and mocked
Vite assets; the feature tests reset shared services between cases. No production
configuration, database or media is used. The temporary database is shut down
after each run.

PHPStan, ECS and Rector dry-run passed for changed application/test classes and
the helper. All changed PHP files passed syntax checks. Templates were exercised
by rendered episode/embed tests; no frontend rebuild or production playback
test was performed. Search results and ranking changes were not measured.

Before any separately authorized deployment, inspect current source and active
transcript work, preserve independent video/card changes and prepare a targeted
source rollback. Invalidate affected page caches after installation and compare
fresh crawler HTML, player routes, feeds and transcript associations. Keep
instance-specific evidence private, and do not restore an old database over
completed transcripts or regenerate production media for this code-only change.

## Production verification

After an authorized installation, compare crawler metadata, embedded-player
responses, feeds, enclosure ranges, artwork, sitemaps and robots against private
baselines. Verify desktop/mobile rendering and player controls. Preserve unrelated
settings, audio, transcripts, source changes and publishing controls. Store exact
deployment revisions, inventories, known baseline issues and rollback evidence
privately.
