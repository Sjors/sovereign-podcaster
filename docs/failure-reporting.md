# Private failure reports, UUIDs in Marmot

When an episode task is blocked or fails, the agent saves its diagnostic report
privately and sends a short notice to Marmot:

```text
Podcast task needs attention.
Report UUID: 7dd78267-d940-4f05-8378-edf856231a13
Give this reference to the maintainer for diagnosis.
```

Give the UUID to the maintainer in the development chat. The full report is **not**
sent over chat. The maintainer resolves it on the agent machine under the isolated
account, using its existing authorized maintenance access:

```sh
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/tools/failures.py" lookup UUID --json
```

Lookup returns the private report and original record path, so the maintainer can
find the job's saved state and inspect relevant evidence locally. It validates
the UUID, file ownership/permissions and matching original record. A changed
original fails lookup rather than silently returning a different failure.
A UUID is a reference, **not a credential or public download URL**. This feature
adds no remote service, credential or extra permission. Keep the private index
and original reports in backups together. Maintenance access after the executor
handoff remains a separate operator decision; a UUID does not restore revoked
access to the isolated account.

## What is recorded

Reports contain UTC time, stage/job/episode identifiers when available, installed
source revision, Python version, a safe problem code/component and suggested next
step. The private record also retains source code locations for local diagnosis.
New references are full random UUID4s. Existing short references remain readable;
a legacy report becomes indexed when it is persisted/used for a new notice.
Existing confirmed notifications are not resent. Prepared notifications remain
immutable; if a pending legacy notice contains a full report, delivery must be
inspected before any replacement. The UUID-only path will not send that old body
or invent a new idempotency key to bypass uncertainty.

The structured diagnostic still excludes raw exception strings, provider bodies,
credential values, upload-session URLs, transcript text and log excerpts. Codes
and guidance come from allowlisted templates. Ordinary job/render logs stay in
their private locations and are not automatically copied into the report or chat.
The maintainer can inspect them locally if the structured report is insufficient.

Reports mark a worker preflight as not started only before launching production.
Other failures conservatively mark external actions as possibly partial. The
maintainer must inspect saved receipts/remote state before retrying an upload or
announcement. Fixing a requirement or resolving a UUID does not resume production,
replace an approval, bypass a maintenance pause or authorize a duplicate upload.

## Creation and storage

Foreground/model/controller failures use the normal harness reply for the short
notice. Background workers use the existing idempotent notification, without
model calls. Basic missing-tool/module/input/configuration checks run before
production. Tool exceptions write structured reports; unrecognized failures use
a generic code requiring local inspection.

If the agent discovers a missing input while discussing the episode, it runs:

```sh
python3 "$SP_REPO/tools/failures.py" create --code missing-input --stage prepare \
  --component transcript --show SHOW --episode EPISODE
```

The command saves the report and prints only its UUID notice. Return that notice
in chat. Do not paste the full lookup output. Use `--help` for allowed values.

Default report files are
`~/.local/share/sovereign-podcaster/failures/UUID.json`.
A worker instead keeps `failure.json` next to its `job.json` and `production.log`.
Both forms are indexed by UUID under
`~/.local/share/sovereign-podcaster/failures/index/`; the private index contains a
snapshot and original path. Directories are mode 0700 and files 0600, outside Git.
An explicit `create --out FILE` uses the same index. Read a known local file with
`failures.py show FILE` or `jobs.py report --job DIR`; these print the full
structured diagnostic for **local inspection**, not automatic chat forwarding.
`podcast status` exposes only the UUID notice for failed jobs.

If local storage/indexing fails, the notice says the report could not be saved
and local inspection is required. It does not advertise a UUID that cannot be
looked up. If the connector/relay is down, the original saved report and send
ledger remain available, but the outage cannot immediately be reported over that
broken channel. Restore transport, inspect its original send intent and timeline,
then run `jobs.py notify --job DIR`; it does not re-run production. Uncertain sends
remain protected by the ledger. An abruptly killed worker may need local status
inspection. There is no idle model health polling.

No dependencies beyond Python's standard library and the existing base tools
are added; apt entries remain in [Linux setup](setup-linux.md) and
[production dependencies](production.md#dependencies-and-tested-environment).
