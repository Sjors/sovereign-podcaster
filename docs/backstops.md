# Operational backstops required before production

The supported runtime uses one isolated Linux user for both operator/controller
and executor. Ordinary authorization is the user's instruction plus reviewed
workflow state. It does not require sudo approval of each episode, file or action.
Instructions tell the operator which directories and originals to preserve;
maintenance pauses, explicit targets, hashes, locks and receipts catch common
mistakes. These controls are not an OS boundary against code under the same UID.
Isolation from other accounts remains useful and should be retained.

**Each new operator must arrange and verify the following before production.**
The repository does not create or silently verify them just because setup ran:

1. **Usage/budget controls.** Inspect the API project's credits, billing/top-up
   settings and any provider-enforced limits actually available. A verified
   server-enforced per-task token/spending limit is still a TODO. Our tested Agents
   endpoint rejected its documented spending-control field. Timeouts and usage
   records are useful but are not hard cost caps. Do not give the executor broad
   billing/admin credentials in an attempt to implement them.
2. **Hosting-machine system backups.** Back up the podcast host, including its
   database, audio/media, transcripts, application/configuration, custom patches,
   Blossom storage and relay data/identities where applicable. Record backup
   location, retention and restoration procedure privately, and test a restore.
   Configure backups for your own actual deployment; this guide does not install
   a scheduler or assert your backups are healthy.
3. **Offline original audio.** Keep recoverable original recordings/audio outside
   the executor's normal writable work area, preferably offline. Record which
   original an edit came from. Working copies, upload receipts or hashes do not
   replace the original bytes. An edited enclosure is not a safe only copy.
4. **Rebuild material.** Keep a recoverable, reviewed copy of `sovereign-podcaster`
   with its skills/scripts, dependency pins, patch provenance and setup instructions.
   Separately back up private configuration, keys and resumable workflow state
   securely; do not put secrets or production histories into the public repository.
   Document the fresh-machine restore steps. Git does not back up untracked media
   or private state. The maintainer signs/pushes from the MacBook; Linux work stays
   unpushed to GitHub until that happens.

Keep the operator-maintained pause file and original source checks current before
writes. Stop and report a UUID for missing prerequisites or unknown outcomes;
inspect receipts and remote state rather than retrying a destructive action.
Do not "repair" a failed job by wiping originals, backup repositories or unrelated
hosting directories. Planning access, credentials and backup existence do not
authorize a particular production change.

A future optional two-user design is tracked in [TODO](../TODO.md). Its operator
might create temporary pre-operation backups outside the executor's write access,
with tested restore/retention behavior. That design needs practical evaluation;
it is not a reason to add root approval prompts to the present single-user mode.
