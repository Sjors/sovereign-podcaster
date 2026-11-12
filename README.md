# sovereign-podcaster

Tools and agent workflows for podcast transcription, chapters and slide videos.
Start with final audio and a reviewed transcript, or create one with
[local transcription](docs/transcription.md). Review clips and send feedback
through White Noise/Marmot before publishing video to Nostr or YouTube.

Agents can use [PPQ or Codex](docs/llm-providers.md). The
[production runbook](docs/production.md) covers rendering, captions, chapters,
revisions and publishing, including AV1/HLS packaging.

Try the offline slide preview with Python 3.11 or later:

```sh
python3 tools/slides.py build --transcript examples/transcript.json --plan examples/slides.json --out /tmp/podcaster-review-r1
python3 tools/slides.py verify /tmp/podcaster-review-r1
python3 -m unittest discover -s tests -v
```

Open `/tmp/podcaster-review-r1/index.html` in a browser to see the slide contact
sheet. For revisions, pass `--feedback FILE` and choose a new `--out` directory.
Each bundle includes its inputs and a SHA-256 manifest, so you can copy it to
another machine and check it with `verify`.

The preview uses only Python's standard library. Video rendering needs the
additional tools described in [setup](docs/setup.md), including FFmpeg and fonts.
Input timestamps must use the original audio's clock.

## Guides

- [Setup](docs/setup.md) and [Ubuntu installation](docs/setup-linux.md):
  account creation, dependencies and configuration.
- [Workflow overview](docs/workflow.md) and [Marmot episode flow](docs/episode-flow.md):
  episode tasks, background jobs and encrypted review clips.
- [Audio editing](skills/podcast-editing/SKILL.md): recordings, live-audience
  audio and transcript timing.
- [Local transcription](docs/transcription.md): produce, review and attach
  episode transcripts.
- [Chapters](docs/chapters.md): publish Podcasting 2.0 chapters and episode
  description timestamps with `chapters SHOW NUMBER`.
- [Nostr setup](docs/nostr-setup.md) and [YouTube API setup](docs/youtube-api-setup.md):
  identities, relays, Blossom storage and publishing credentials.
- [Marmot adapter](adapters/marmot/README.md) and
  [Agents API adapter](adapters/openai-agents/README.md): messaging and agent integration.
- [Castopod publishing](skills/castopod-publishing/references/operations.md) and
  [maintenance](skills/castopod-maintenance/SKILL.md): episode operations,
  upgrades, backups and rollback.
- [Castopod and Nostube patches](docs/patches/README.md), with a
  [source snapshot](patches/catalog.json).
- [Failure reports](docs/failure-reporting.md): troubleshooting failed tasks.
- [Reuse and licensing](docs/provenance.md), and [planned work](TODO.md).

## Before production

Run the agent under a dedicated, unprivileged user. Keep credentials and
production media outside the repository, back up your podcast host and retain
original audio. Read the [operational backstops](docs/backstops.md) before
granting the agent access to hosting accounts or paid services.

## Contribute

Open pull requests on [GitHub](https://github.com/Sjors/sovereign-podcaster/pulls)
or [GitWorkshop](https://gitworkshop.dev/npub1v25jqj332n630klwtqeqxgyrjl4alw4phmluhu2x6lcxzwy9m03suqexw3/nostr.sprovoost.nl/sovereign-podcaster).
GitWorkshop supports issues and pull requests over Nostr; GitHub hosts the code.

Pull requests are welcome, especially integrations with different agent
harnesses, podcast hosting providers, Nostr relay software and Blossom storage
implementations. Improvements to the tools, skills, documentation and
reproducibility are welcome too.

For coding agents collaborating over Nostr, follow the upstream
[ngit agent guidance](https://ngit.dev/agents/). Optionally run
`ngit skill install` inside the checkout; locally installed skill copies are
ignored by Git rather than vendored here.
Use the `nostr` remote for Nostr collaboration and `origin` for GitHub.

Keep integrations configurable and put harness-specific code in adapters.
Document setup, dependencies and the versions/environments you tested.

Each pull request should be tested by **at least one person other than its
author before merging**. That person can be Sjors. Include reproducible test
steps and record who tested the change, their environment and the results in
the pull request. If you need someone to test it, say so in the pull request.
