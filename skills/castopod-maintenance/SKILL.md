---
name: castopod-maintenance
description: Maintain or upgrade a configured Castopod instance, preserving deployed custom behavior, checking upstream replacements, staging patches, backups, regression checks and rollback. Use castopod-publishing for episode operations.
---

# Castopod maintenance

Read [the maintenance procedure](references/operations.md), the repository's
[patch catalog](../../docs/patches/README.md) and
[patch maintenance notes](../../docs/patches/maintenance.md). Read the selected
private instance record before host work, then inspect actual state; a snapshot
is not a live inventory. Keep host paths, accounts, deployed commit/diff evidence,
backups and credentials outside the shared skill. Never infer a target instance.

For each new tag, **first check current official upstream code and contributions**
for the required behavior. Confirm which fixes are actually included in the
chosen tag, and test equivalence before dropping a local patch. A closed issue,
merged MR elsewhere, conflicting cherry-pick or missing patch-specific test helper
does not establish that the target release covers the behavior. Prefer a tested
upstream equivalent; record any required unreleased commit explicitly.

Preserve every deployed local change, including unrelated edits, helper interfaces,
settings/data and separately deployed player/frontend/nginx artifacts. The public
catalog is not an exhaustive inventory of somebody's production installation.
Do not reset/clean a live checkout, combine duplicate patch representations or
repeat historical one-off database/media repairs merely because source upgraded.

If carrying patches is no longer a trivial cherry-pick, recommend the operator's
own fork with explicit upstream tags, topic/integration branches, provenance,
regression tests and license notices. Keep the patch register and canonical
catalog current. Consult upstream again on the next release.

Prepare private verified backups and a migration-aware rollback before deployment.
An archive or base-table dump with missing views/media is not a complete backup.
Stage source, dependencies, tests and frontend builds in isolation without writable
links to production media/configuration/database. Pause cooperating episode
writers using the existing operator-owned maintenance control; changing accounts
or paths must not bypass it. Record the exact control and restoration procedure.

A requested upgrade authorizes its necessary patch-preservation/deployment work;
this skill adds no blanket approval gate. Preparing these tools alone requests
no upgrade, episode publication, upstream message, MR or Git push. Respect existing
authorization and the installed runtime/version's actual requirements.

Verify public pages, feeds, enclosure lengths/ranges, artwork, transcripts and
read-only publishing helpers after an authorized deployment. For video integration
also verify media decode/alignment, player routing, seeking/quality/fallback,
CORS/MIME/ranges, signed-event verification and channel restrictions. Distinguish
browser viewport tests from actual phone codec/playback results.

Record deployed source/diffs, build outputs, backups, checks and rollback limits
privately. Keep validated Git work unpushed for the operator's signing workflow;
use UTC timestamps and compare tree/patch equivalence across signing-only SHA
changes. Preserve working old access until replacement and recovery paths pass.
