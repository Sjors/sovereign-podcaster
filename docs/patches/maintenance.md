# Using and maintaining the patches

Work directly on `master` in this currently unpublished repository unless the
owner requests a separate branch. The catalog may lead publication of the
Castopod branches: keep prepared source pins in `topics` with explicit publication
state. Record instance deployment state privately. Catalog preparation does not
authorize publication or deployment.

The [catalog](README.md) describes behavior and dependencies. Human-facing branch
documentation should use branch names and release tags. Keep exact commit hashes
in the [machine-readable source snapshot](../../patches/catalog.json) or private
operational records, rather than duplicating them in prose.
This project is the authoritative dependency map. Castopod branch documentation
should cover feature behavior and configuration, and link here for branch
combinations rather than duplicating their prerequisites or compatibility lists.

Compare source content when reconciling local and published versions. Signing-only
differences are equivalent and do not require a resync or redeployment. Preserve
both UTC timestamps for unchanged replays/signing, and preserve unpushed fixes
when refreshing a branch. Rebased source changes still need appropriate review
and validation.

## Fetch without production credentials

For a new checkout, use public HTTPS. For example:

```sh
git -c credential.helper= clone --no-checkout https://github.com/Sjors/castopod.git castopod
git -C castopod remote set-url --push origin disabled://read-only
git -C castopod checkout --detach origin/2026/10/audio-file-size
git -c credential.helper= clone --no-checkout https://github.com/Sjors/nostube.git nostube
git -C nostube remote set-url --push origin disabled://read-only
git -C nostube checkout --detach origin/2026/11/embed-event-verification
```

These examples select only the audio-file-size and event-verification topics,
respectively. Select the topics needed for the intended release from the catalog.
Use disposable integration checkouts when combining independent topics;
do not merge them into production as an inspection step. The channel-player tip
already includes event verification: apply its prerequisite once. Do not combine
a historical full deployment patch with the contribution series.

No GitHub authentication is needed for public clones. Disabling a push URL is an
accident guard; withholding write credentials is the access boundary. The isolated
executor must receive no maintainer GitHub token, SSH agent or signing key. Its
own podcast-host SSH identity does not grant GitHub access.

## Preserve behavior and operational guards

Before an upgrade, inspect actual deployed source, uncommitted edits, frontend
assets, settings, media paths and publishing interfaces. Back up database,
configuration, source and affected media privately and verify recovery artifacts.
Keep exact deployment provenance separate from this maintained source snapshot.

Retain audio-size fallbacks, accurate artwork encoding, RSS range semantics,
independent existing episode-card edits and GUID/enclosure/transcript associations.
Video integration needs matching rebuilt frontend assets, contextual video settings,
the separately deployed static player and its nginx route. Preserve signed-event
verification, channel/relay restrictions, safe return URLs and codec checks.
Never drop unrelated deployed behavior merely because it is absent from this catalog.

Publishing adapters must retain the operator's maintenance pause, explicit show/
channel/signing-identity checks, per-episode locks, dry-run planning and remote
inspection before retrying ambiguous writes. Changing paths or Linux users must
not bypass a pause. A missing/malformed required guard fails closed. Preparing a
patch or catalog change does not authorize deployment, upload or publication.

Recheck official upstream code and open/closed contributions before carrying,
replacing or retiring a patch. Prefer a tested upstream equivalent that covers
the same behavior. Keep previous source/export recovery material until the
replacement is proven. Validate in isolated dependencies and test databases;
never borrow writable production media/configuration for tests.

For the video stack, verify caption/audio alignment, complete media decode,
quality switching, seeking, fallback, MIME/CORS/ranges, and channel restriction.
Chromium mobile viewport tests do not establish Safari/iOS hardware codec support.
After an authorized deployment, verify actual public pages/feeds/media and record
source, build configuration, output hashes, readback, backup and rollback limits.

## Catalog updates and licensing

Edit the catalog and source snapshot in the same change. For each changed topic,
record upstream base, prepared tip/tree, last published tip, prerequisite order, license and validation
limits. Keep retired topics documented if needed to explain historical deployments.
Do not add private host paths, credentials, backups or full deployment logs.

Source remains in the maintained forks under its project license: Castopod's
AGPLv3 and Nostube's MIT. No upstream code or patch exports are vendored here.
Keep original authorship and notices when exporting or redistributing source;
the sovereign-podcaster repository's eventual license does not replace them.
The sitemap topic includes the adapted upstream MR !375 and its authorship.

Leave work unpushed on the Linux maintainer machine. Sync/sign/push from the
operator's MacBook, preserving both UTC timestamps for signing-only changes.
Only after the new catalog is public should the original gist become a short
forwarding notice. The gist remains unchanged until the operator publishes
that notice. Keep future catalog edits here instead of maintaining two independently editable copies.

## Publishing individual Castopod topics

Use the publication/dependency table in [topic-publication.md](topic-publication.md).
The catalog distinguishes prepared revisions from previously verified published
source. Exclude integration branches from topic publication. Compare source content;
signing alone does not require resync or source deployment. Keep historical
integration and deployed pins in private records as provenance. Do not replace
an old deployed pin with a reorganized source head and imply that production was
reinstalled.
