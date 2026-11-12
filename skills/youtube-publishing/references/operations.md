# Channel operations

Use the pinned official Google clients in `scripts/requirements.txt`. Consult
current primary references for unfamiliar fields, restrictions or quotas.

## Access and recovery

```python
import sys
sys.path.insert(0, "/path/to/sovereign-podcaster/skills/youtube-publishing/scripts")
import youtube_access as access

with access.channel_service(config_dir, expected_channel_id, mutate=True) as (youtube, channel):
    video = access.owned_video(youtube, video_id, expected_channel_id)
    # Perform only the operation authorized in this task.
```

Select explicit config/channel values from private operator configuration, outside this repository. Use `mutate=False`
for reads. Mutating contexts take a nonblocking shared lock in the credential
directory; cooperating projects must use the same lock. Legacy workspace-local
locks do not coordinate with it. Reads can refresh/save local credentials.
Use `owned_playlist` before changing a playlist. References to other channels'
videos may be added to an owned playlist without editing those videos.

Use the existing refresh token first. A new chat/project doesn't need a new
Google account/client/grant. If reauthorization is necessary, keep this SSH
tunnel open on the operator machine when running the helper on the agent machine:

```sh
ssh -N -L 127.0.0.1:18765:127.0.0.1:18765 podcaster@AGENT_HOST
# On dev, with the selected instance's actual paths/ID:
PYTHON /path/to/youtube_access.py authorize --config-dir PRIVATE_DIRECTORY --channel-id EXPECTED_CHANNEL_ID
```

Open the printed URL on the Mac and select the intended podcast channel/Brand
Account. The helper uses Desktop OAuth, PKCE, state, offline access and a loopback
callback, saving only after live channel verification. A client ID ending in
`.apps.googleusercontent.com` alone isn't enough; Desktop client JSON must contain
its secret. Never request secret contents in chat. Config directories are 0700;
files 0600 and owned by the execution user. Reject extra scopes and non-Google
endpoints before refresh. Don't request Gmail/People/Drive access as a workaround.

For Testing-mode `403 access_denied`, check test-user access or the intended OAuth
app publication setting. The current app is In production. OAuth project status,
token expiry and channel feature eligibility are different concerns.

## Upload and publication

Use an explicitly selected finished video and its validation/source hashes.
Set episode-specific title, description, category, language, audience and paid
promotion. A retained sponsor acknowledgement may still require disclosure after
cutting an ad read. `containsSyntheticMedia` concerns realistic altered/synthetic
content, not merely an agent-made layout or supplied transcript.

Set `status.privacyStatus=private` for a review upload: API defaults can publish.
Set `notifySubscribers=False` for backfill or when requested; otherwise choose
from the task rather than copying an old episode's policy. Uploads use the token's
channel. Use resumable media, retain the source hash/size/intended metadata/video ID,
and keep the resumable URL private. Query server offset/completion after interruption.
Inspect live channel state before retrying an ambiguous creation; don't duplicate.

Wait for `processingDetails.processingStatus=succeeded`; inspect failure/rejection
details otherwise. Verify duration, metadata, captions and thumbnail. If publication
is authorized, update the existing `status` to public while preserving other writable
status fields and omitting stale `publishAt`. Verify visibility and an unauthenticated
read such as oEmbed. Its 200 establishes public metadata, not all-resolution playback.
Don't promise subscriber-notification delivery from a status change.

`processingStatus=succeeded` can coexist with `fileDetailsAvailability=inProgress`
and missing `fileDetails.videoStreams`. Do not mistake that optional analysis
delay for a failed upload or assume those stream details already exist. When
inspection needs the source resolution, verify the registered local master with
ffprobe/hash evidence, the complete saved resumable upload, the API file size
when available, and the processed video's HD/duration/metadata readback. Record
which evidence was available. API `definition=hd` alone does not establish that
the 1080p rendition is selectable; inspect the player before making that claim.
If source-stream details arrive, compare them as additional evidence. A missing
optional field must not cause a second upload or discard the verified existing ID.

Keep the real human authorization and its scope. If they explicitly approved
public release of the exact reviewed packet before upload, inspect the resulting
private video, bind that same instruction to its actual ID/channel/hashes, then
release it. Do not invent another human sign-off or fabricate Marmot provenance.
If they requested a separate private-video review, retain that pending review.
Recheck caption words/times and thumbnail immediately before the visibility change;
late native-transcript corrections must also have reached the rendered picture.

Video bytes cannot be replaced in place. A replacement gets a new ID/URL and splits
links/views/comments. Text, subtitles and thumbnails can be edited on the existing ID.
Don't remove a canonical video as automatic cleanup.

## Scoped metadata and chapters

Read immediately before writing: updated `part` values replace their mutable
properties, so omissions may erase values. Include only necessary parts and preserve
their other writable fields. For description edits, retain existing snippet `title`,
`categoryId`, `tags`, `defaultLanguage`, `defaultAudioLanguage` where present, changing
only the intended text. Title/category are required for snippet updates. Don't send
read-only `channelId`, thumbnails or localized summaries as editable snippet values.
Don't include `status` in a description-only update. Preserve concurrent user edits
instead of replacing the whole description from an old template.

Use plain full HTTPS links. Markdown link syntax won't make description links
clickable. Clickable external links require Advanced features in Studio → Settings →
Channel → Feature eligibility; the API can't enable identity/history verification.
Chapter display also depends on eligibility. Use the final edited clock, starting at
00:00 with at least three ascending chapters of at least ten seconds. Place a silent
ad-omission card in the sponsor chapter; start the next topic after the card.

Save public before/request/after evidence without tokens/upload-session URLs.
Immediate reads can be stale. Retry reads for a bounded interval before declaring
failure; don't repeat successful insertions just because readback hasn't propagated.

## Captions and thumbnails

Upload reviewed timed VTT/SRT via `captions.insert`, with language/name and
`isDraft=False`. Don't enable deprecated auto-sync on timed files. Use timings/words
for the edited video, including cuts. List existing tracks first; language/name pairs
must be unique. Update/reuse the matching track rather than duplicating it; verify
`status=serving`. Uploaded captions are the reviewed transcript, not YouTube ASR.
Auto-translation can use them where available, but technical terms may be wrong.
English text burned into the picture stays English. Machine translations aren't
reviewed translations unless reviewed separately.

Use `thumbnails.set` on the existing ID. For this show, reuse the SVG palette/template
and original portraits, checking legibility at about 320×180. A 3840×2160 PNG was
accepted. Current API documentation accepts PNG/JPEG up to 50 MB; verify current
limits if rejected. Custom thumbnails require the appropriate feature eligibility.

## Playlists and availability

List owned playlists before creation; reuse a saved ID and verify owner/visibility.
New playlist creation may briefly yield `playlistNotFound` on listing: wait/read the
saved ID rather than creating another. Insertions have no idempotency key; read live
membership before retrying an ambiguous insert. Keep progress and exact intended
order, omit duplicate IDs, and verify final membership/order/public visibility.
Explicit positions require manual playlist ordering.

For historical episodes, retain canonical third-party videos. Read all source
playlist pages; inspect `videos.list` for public/processed status, source ownership
and restrictions. Private/deleted entries may be absent from video results. Search
the source channel for missing full episodes, reviewing candidates because searches
also return unrelated videos. Public metadata/oEmbed catches broken links but doesn't
guarantee playback in every region. Avoid unnecessary full-video downloads.
Newest episode first means original chronology, not a duplicate's reupload date.
Choose versions using actual availability, captions, artwork/duration and quality
where needed, rather than assuming newer or older is always better.

## Moderation and branding

Read comments with `commentThreads.list`/`comments.list`. When authorized, use
`comments.setModerationStatus` to hold/reject comments within the user's spam/abuse
policy, preserving discussion and criticism. `comments.delete` is limited to the
authenticated identity's own comments, not general channel moderation. Don't reply
or ban authors unless authorized. A setup discussion of future moderation isn't
permission to moderate now. Studio Basic/Strict settings may help; not every setting
is exposed by the API.

Channel descriptions use `channels.update(part=brandingSettings)`; preserve other
mutable branding values. Profile photos, handles and separate profile-link buttons
are not exposed here: use Studio → Customization → Profile. Don't request broader
Google-account permissions. Banner uploads have a different API and don't set the
profile logo. For circular crops, pad existing art without redrawing its lettering.

## Primary references

- [Desktop OAuth](https://developers.google.com/youtube/v3/guides/auth/installed-apps)
- [Uploads](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
- [Video updates](https://developers.google.com/youtube/data/reference/rest/v3/videos/update)
- [Resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol)
- [Captions](https://developers.google.com/youtube/data/reference/rest/v3/captions)
- [Thumbnails](https://developers.google.com/youtube/data/reference/rest/v3/thumbnails/set)
- [Playlists](https://developers.google.com/youtube/data/reference/rest/v3/playlists)
- [Playlist items](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems)
- [Moderation](https://developers.google.com/youtube/data/reference/rest/v3/comments/setModerationStatus)
- [Channel updates](https://developers.google.com/youtube/data/reference/rest/v3/channels/update)
- [Feature eligibility](https://support.google.com/youtube/answer/9890437?hl=en)
