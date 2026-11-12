# Validation on 2026-11-01 (UTC)

The production port was exercised on Ubuntu **26.04.1 LTS x86-64**, both as the
maintainer and under the isolated `podcaster` UID. Inputs were an explicitly
synthetic twenty-second chirp/envelope audio fixture, two placeholder portraits,
two transcript cues and two slides/chapters. No real episode was selected.
No production upload, Nostr announcement, YouTube mutation, paid model request or
real completion message was sent by these checks.

| Check | Result |
| --- | --- |
| Renderer, caption/portrait/waveform layout and thumbnail | Master and all three AV1 renditions generated; sample frame inspected |
| Source preservation/edit clocks | Immutable input hashes; caption wording, explicit cut boundaries, chapters and feedback parent tests passed |
| Audio alignment | Sampled edited-audio comparison recovers AAC priming delay, with correlation above 0.99 for the chirp fixture |
| Media/container checks | Full decode, codec/colour metadata, fast-start/no-edit-list and chapter checks passed |
| AV1/HLS packaging | 720p/480p/360p, independent exact-byte fallback, aligned keys, six-second fMP4 HLS, ordered compressed-packet equality and full HLS decode passed |
| Background execution | Detached render and package jobs reached durable completion as the isolated user |
| Python suite | 38 tool/handoff tests, 26 API-backend/routing tests, 1 setup test passed |
| YouTube SDK compatibility | Installed pinned SDK constructed private resumable and caption replacement requests with anonymous credentials; no HTTP execution |
| Provider recovery fixtures | Lost initiation/final upload responses, same-ID private packet correction, changed thumbnail rejection and reviewed-ID public visibility transition passed with fake transports |
| Nostr production transport fixture | Bottom-up upload order, saved signed-event IDs, addressable video links, all final blobs and exact HLS advertised/child readback paths passed with fake signer/transports |
| Authenticated replies/reviews | Connector timeline checks, separate identical-word messages, exact-ID replay, wrong route/sender, stale/changed packets and combined/private/public approval separation passed |
| Completion notification recovery | Fake connector failure/retry and confirmed-send replay tests passed without repeating production |
| Patched Marmot source build | Locked upstream tag/commit, private umask, 148 library tests and 22 process-contract tests passed; checked binary installed for podcast harness only |

The first upstream library run used the maintainer's permissive umask and hit
artifact-source protection failures. Re-running with the intended **umask 077**
passed all 148; the public builder enforces that umask. The build is a pinned,
checked source build, not a claim of compiler bit-for-bit reproducibility.

Private instance validation artifacts and service/build manifests belong
outside Git. These synthetic checks do not authorize production writes.

Still required: select the real episode/materials; verify the updated phone
help/reply/approval and real completion-notice paths; inspect long-duration
rendering/playback; authorize and test actual draft storage, Nostr publication,
private YouTube review, exact public release and guarded draft cleanup. Fake
transport receipts are test evidence only. They do not establish live provider
acceptance, public playback, editorial approval or deletion.
