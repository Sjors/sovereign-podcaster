# Maintaining a configured Castopod instance

This is a guided maintenance procedure, not an automatic deployment program.
Use private instance configuration based on
[the example](../../../examples/castopod-maintenance.json). The skill/agent reads
that record; no new generic upgrade runner consumes it. Consult the actual
release's upstream installation/runtime guidance before selecting commands.

## Prerequisites and scope

An operator supplies the exact SSH target (or intentional local transport),
application/media/helper paths, expected show identities/public origin, source
clone/upstream/fork, backup root and maintenance-pause path. Identify separately
deployed static players, nginx snippets, frontend build configuration and any
compatibility URLs. Discover all current shows instead of hard-coding episode
counts. Keep host-specific source and publication policies in private notes.

On the agent machine the baseline inspection tools are:

```sh
sudo apt install --no-install-recommends \
  bash ca-certificates coreutils git openssh-client python3 tar
```

Omit SSH for deliberate local transport. PHP/database/Composer/Node requirements
belong to the hosting release and build environment: inspect them first; do not install or update
production packages blindly. Runtime compatibility must be checked for each tag.

## First inspect upstream, then the deployed state

Use Castopod's [official repository](https://code.castopod.org/adaures/castopod)
and current release/tag source, issues and open/closed merge requests. A mirror
or an old local duplicate search can be stale. Determine which required behaviors
are already in the exact tag, and which still need a patch. If an unreleased MR
is suitable, test its current scoped commits in isolation and record the pin.

Inspect the live version/HEAD, tracked/untracked changes, lockfiles, publishing
helpers, storage layout, settings, database migration state and public feeds.
Capture a fresh public baseline and compare deployed changes to the
[canonical patch source snapshot](../../../patches/catalog.json). Keep unrelated
local edits. Never blindly apply a full historical deployment diff on top of
contribution branches that already contain the same changes.

For nontrivial patch maintenance, use the operator's own fork. Build integration
branches from an explicit upstream tag, apply each required topic once in dependency
order, preserve authorship/license notices and retain original refs/exports.
Review conflicts as behavior changes. The catalog's branches/commits are source
references, not an instruction to update a live instance or a guarantee that every
patch remains necessary. Publish fork changes only within the operator's authorized
Git workflow; this setup leaves validated branches unpushed for Mac signing.

## Backups, isolated validation and authorized deployment

1. Select a private backup directory outside source with enough capacity. Capture
   application/configuration/Git state and diffs, the database including views and
   any required routines/triggers, relevant media, helper scripts, static player,
   web-server configuration and build artifacts. Record omissions explicitly.
   Verify archive/checksum integrity and practice the relevant restore path.
2. Pause cooperating writers through the existing maintenance decision. Record
   what may continue read-only and when/how the operator permits resumption.
   In the current single-user runtime this is user-maintained operational state,
   not an executor/operator security boundary; honor explicit pause/resume instructions. A different backup path or user
   must not silently discard the pause or use a stale always-open copy.
3. Stage the chosen tag/patches away from production. Use independent dependencies,
   test databases and copied fixtures; no writable symlinks/hardlinks to live data.
   Run upstream checks plus behavior regressions described in the catalog/instance
   notes. Do not infer failure of an upstream alternative from the absence of a
   test-only private helper introduced by the old patch.
4. For the authorized upgrade, deploy the reviewed source/builds and run only the
   target release's required dependency, asset, migration and cache steps. Inspect
   installed CLI help rather than blindly replaying old commands. Preserve persisted
   settings, media references, GUIDs/publication dates and historical repairs.
5. Verify the real deployment and public delivery. Account for migrations and any
   new writes before deciding whether code rollback or data restore is appropriate.
   Preserve failure evidence; do not repeatedly rerun an ambiguous operation.

## Regression and handoff record

Check all current public feeds with HEAD, GET and byte ranges; compare metadata,
GUIDs, dates, enclosure identity/length and transcript references. Check artwork
encoding and derivatives, audio MIME/format/ranges, representative episode and
transcript pages, JSON companions and login. Run publishing `list`/`inspect` reads
against the installed helper cohort. Inspect source-specific legacy compatibility
URLs and directory metadata without changing them incidentally.

Video-enabled deployments also need the matching frontend, static player and
route, contextual video settings, channel/relay restrictions, event signatures,
return-link checks, complete media decode/alignment and quality/seeking/fallback
checks. Compare failures from more than one network vantage point when a proxy
may be responsible. Do not turn a successful feed check into a claim that a
third-party podcast directory has reinstated or refreshed its listing.

Save exact source/build IDs and hashes, retained/replaced patch provenance, backup
locations/completeness, tests, public readback and rollback limits privately.
Update the shared catalog and its source snapshot together when their actual
patch descriptions/dependencies change. Keep private deployments separate.
The repository supersedes the old patch gist; do not maintain divergent manuals.

Before retiring old access, finish outstanding server work, validate the isolated
account and an independent operator recovery route, and account for indirect
maintainer-to-executor access. Sharing these skills does not perform that cutover.
