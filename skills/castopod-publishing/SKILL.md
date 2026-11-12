---
name: castopod-publishing
description: Inspect or manage podcast episodes on an explicitly configured Castopod instance, including drafts, audio/show-note updates, native transcript attachments and authorized publication. Use castopod-maintenance for upgrades; media production stays in its source workflow.
---

# Castopod publishing

For finished conversation episodes, read
[episode-delivery.md](references/episode-delivery.md) for final-clock chapters,
rendered Markdown line breaks, transcript revisions and linking an already
published native video. Audio preparation belongs to `podcast-editing`.

Use `scripts/publish.py`; read [operations](references/operations.md) for setup,
CLI examples, required pause controls, receipts and version-dependent transcript
behavior. The client is standard-library Python and uses SSH, or local execution
when deliberately configured. Keep instance configuration, credentials, evidence
and original media outside this repository. Use the isolated account's own SSH
identity and explicit target configuration; never borrow an SSH agent or web login.

Select the intended show and episode from the task and live discovery. Every
mutation requires `--podcast` and `--slug`; do not infer the show from an episode
number, previous invocation or another workflow's defaults. New creates default
to drafts. Updates preserve publication status and existing enclosure identity.
A transcript belongs to the episode whose final audio its cues describe; adding
text to an existing episode is distinct from creating a narrated article.

For autonomous existing-episode chapter tasks, follow
[the chapter workflow](../../docs/chapters.md). `chapters SHOW NUMBER` authorizes
agent review and native JSON/derived-description publication without manual
approval. Use its source-bound toolkit, conditional update and verified receipt;
respect its rollout authorization and backfill hold. Do not independently edit
multiple chapter lists.

Writes require `--apply`, an immutable private `--receipt`, a readable
operator-controlled maintenance pause and the matching installed PHP helper
cohort. The operator and executor share the isolated user; this private pause
state is user-maintained and is not a same-UID security boundary. Missing/malformed/inaccessible pause state fails closed.
Do not introduce a new always-open pause file to bypass an existing maintenance
hold. Respect an authorized task without adding a blanket confirmation step;
credential access and installation alone do not authorize publication.

Inspect before retrying any ambiguous mutation. The receipt binds the target,
operation and input hashes; a verified repeat returns saved evidence, and an
unresolved or changed request stops. Preserve staged files and receipts on
failure. Local episode locks and the matching PHP helpers coordinate cooperating
writers; older helpers do not participate in the new server lock protocol.

Keep exact audio, transcript, artwork/metadata and review evidence with the source
workflow. Transcript readback must preserve GUID, publication date, audio key/URL
and unrelated fields. Metadata readback is separate from listening, public
file-hash/cue checks and page/feed checks. Never claim public delivery or editorial
approval based only on a successful model/database operation.

Read the selected private instance's operator notes when supplied; source-specific
narration, disclosure, rights and independent-review requirements stay there.
Do not copy one show's rules or sponsor/audience flags into another episode.
Use [castopod-maintenance](../castopod-maintenance/SKILL.md) before upgrading
interfaces or carrying compatibility patches. Do not upgrade a production service
merely to obtain a publishing API.
