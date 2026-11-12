# sovereign-podcaster

Portable podcast video production with private Marmot feedback, resumable local
stages and reviewed Nostr/YouTube publication. Start from final audio and a full
reviewed transcript, or use [local transcription](docs/transcription.md) to produce
and attach one to an explicitly selected existing podcast episode. The [production runbook](docs/production.md) covers rendering,
layouts, captions, chapters, revisions, AV1/HLS packaging, background notifications,
authenticated approvals and private-first YouTube publishing. Missing prerequisites
and failed stages send [UUID references to private failure reports](docs/failure-reporting.md) in chat. Synthetic local and
fake-transport checks [passed on Ubuntu 26.04.1](docs/validation-2026-11-01.md).
The fully automatic Marmot video flow still needs its end-to-end acceptance test.
Installation does not authorize external publication.

For raw recordings and modest editorial revisions, use the
[podcast-editing skill](skills/podcast-editing/SKILL.md), including its separate
live-audience processing reference and source-to-final transcript timing guidance.

Choose [PPQ or the existing Codex backend](docs/llm-providers.md) through private
provider/model settings. PPQ uses a standalone Python tool loop and does not
depend on Codex tooling. Explicit video assignments can resume after background
jobs and exact White Noise approvals; [the video runbook](docs/production.md#explicit-video-assignments-and-back-catalogue-publication)
also covers old episodes that need native video without an announcement.

For a small dependency-free first check, build the offline slide contact sheet:

```sh
python3 tools/slides.py build --transcript examples/transcript.json --plan examples/slides.json --out /tmp/podcaster-review-r1
python3 tools/slides.py verify /tmp/podcaster-review-r1
python3 -m unittest discover -s tests -v
```

Open `/tmp/podcaster-review-r1/index.html` in a browser. Supply feedback using
`--feedback FILE` on the next build and choose a new `--out` directory. The CLI
refuses to overwrite a revision. Bundle files contain the complete input
transcript, slide plan, optional feedback, HTML, and a SHA-256 manifest. Copy the
whole directory to resume or review elsewhere. `verify` detects changes against
that manifest; it does not authenticate a human approval.

Python 3.11+ standard library only. The HTML is an editorial contact sheet, not
the finished episode layout or video. It escapes text and makes no network
requests. Source excerpts are proposals requiring source verification; neither
slide summaries nor sources are fabricated by this command. The agent supplies
the editorial content. Input timestamps must use the original audio's clock.

Read the [Marmot episode flow](docs/episode-flow.md) for independent episode
sessions, tracked draft uploads/cleanup and encrypted review clips. Read
[workflow](docs/workflow.md), [setup](docs/setup.md),
[reuse and licensing](docs/provenance.md), and the
[Agents API experiment](adapters/openai-agents/README.md).
The [Ubuntu setup steps](docs/setup-linux.md) cover the isolated Linux account,
apt dependencies and first offline test on Ubuntu.
The [YouTube API setup guide](docs/youtube-api-setup.md) covers Desktop OAuth,
browser tunnels and moving an existing grant into the isolated account.
The [Nostr setup guide](docs/nostr-setup.md) covers shared skills, fresh or migrated
identities, relay/Blossom prerequisites and a temporary five-second publication
with separately verified event/blob cleanup. The offline slide demo still needs
only the standard library; Nostr tools use their own pinned runtime.
The [Marmot adapter](adapters/marmot/README.md) sets up a fresh private messaging
identity for the isolated agent and prints its pairing details. Evolving Marmot
instructions remain upstream; the local adapter uses the existing Agents API keys.
The [Castopod publishing toolkit](skills/castopod-publishing/references/operations.md)
ships a configurable Python client, PHP server helpers, operation receipts and
readback tests. The [maintenance skill](skills/castopod-maintenance/SKILL.md)
covers upstream-first new-tag checks, patch preservation, backups and rollback;
private instance/deployment records remain outside the repository.
The [Castopod and Nostube patch catalog](docs/patches/README.md) is maintained
here, with a [published source snapshot](patches/catalog.json). This supersedes
the earlier gist; patch implementations remain in their maintained forks.
Host-specific inventory and migration commands are maintained outside this
candidate repository. No existing private skill or patch has been bulk copied.
Public release is pending license selection and the provenance review.
The [chapter workflow](docs/chapters.md) prepares autonomous review and publication
of native Podcasting 2.0 chapters and derived
description timestamps through `chapters SHOW NUMBER`. Configure and validate
the workflow for your own instance; backfill requires separate authorization.
The [TODO list](TODO.md) tracks raw-audio editing, transcript production/uploads
(preferring separate speaker tracks), Marmot voice-memo feedback, podcast
publication after transcript completion, reusable Castopod maintenance/operations
and a safe podcast-host access handoff.

The repository is [Sjors/sovereign-podcaster](https://github.com/Sjors/sovereign-podcaster).
The maintainer syncs, signs and pushes from a MacBook. The isolated Linux user
can clone over public HTTPS with no GitHub credential; see [setup](docs/setup.md).
Before public publication, [private bootstrap and source synchronization](docs/executor-sync.md)
can keep an explicitly authorized executor checkout current without GitHub access.

## Before production

The isolated user is both operator and executor. New users must arrange the
[operational backstops](docs/backstops.md): verified usage controls where available,
hosting-machine backups, offline original audio and recoverable rebuild material.
The provider-enforced task budget is still a TODO. Normal operation uses private
user-owned maintenance state and explicit instructions, without sudo approval of
each episode. Optional two-user protection is future work.

## Contribute

Pull requests are welcome, especially integrations with different agent
harnesses, podcast hosting providers, Nostr relay software and Blossom storage
implementations. Improvements to the tools, skills, documentation and
reproducibility are welcome too.

Keep integrations configurable and put harness-specific code in adapters.
Document setup, dependencies and the versions/environments you tested.

Each pull request should be tested by **at least one person other than its
author before merging**. That person can be Sjors. Include reproducible test
steps and record who tested the change, their environment and the results in
the pull request. If you need someone to test it, say so in the pull request.
