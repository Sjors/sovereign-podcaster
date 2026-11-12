---
name: youtube-publishing
description: Access an authorized YouTube channel through the Data API, including OAuth recovery, uploads, metadata, captions, thumbnails and playlists. Video production stays in its source workflow.
---

# YouTube publishing

Use `scripts/youtube_access.py` and its pinned `scripts/requirements.txt`.
Require explicit private `--config-dir` and expected `--channel-id`; read the
operator's private channel configuration rather than inferring the last channel.
The helper rejects extra scopes, non-Google endpoints, foreign credentials/files
and wrong live channel identity. It supports `check`, `check --refresh` and
`authorize`; those commands do not mutate YouTube resources.

For a first setup or migration, read [the API setup guide](../../docs/youtube-api-setup.md).
Reuse an existing working OAuth grant before asking for new authorization. Install
the runtime under the isolated user; keep credentials outside source, artifacts,
skills and logs, with directories 0700/files 0600. Never print tokens, client
secrets, callback codes, exception bodies or resumable upload URLs.

For channel operations, read [references/operations.md](references/operations.md).
Use the verified SDK context and exact expected channel; inspect ownership before
modifying videos/playlists. Mutations use the shared private lock, preserve
unrelated fields and retain readback/recovery evidence. Coordinate token writes
during migration; even a read-only identity check may refresh/save the local token.

Keep local planning, private review upload and public publication distinct.
Private review uploads explicitly set `privacyStatus=private` and the requested
notification policy. Reuse the existing video ID for metadata/caption/thumbnail
edits. Inspect live state before retrying ambiguous creates. Each external action
needs task authorization; credential access grants no standing publication,
deletion, moderation or cross-platform announcement permission.

Keep the operator's review of exact video, thumbnail, captions and metadata tied
to artifact hashes before public publication. Preserve maintenance guards and
other workflow protections. Never copy one episode's sponsor/audience/disclosure
flags into another without checking its actual content and instructions.

Distinguish processed video from pending optional source-analysis metadata; see
the processing guidance in the operations reference. Carry human transcript
corrections into both the rendered picture and uploaded captions. Preserve the
exact private upload ID for an already authorized public release instead of
creating a replacement or requesting the same approval again.

For complete episode publication use the [production runbook](../../docs/production.md)
and `tools/publish.py`. It reuses this OAuth/ownership/lock context for durable
resumable private uploads, metadata/thumbnail/caption revisions, processing/readback
and exact-ID public release. `youtube_access.py` remains the authorization/check CLI.
