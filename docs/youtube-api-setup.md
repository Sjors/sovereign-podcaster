# YouTube API access and credential migration

Use this on the isolated **agent machine**, not the podcast hosting machine.
YouTube access is independent of Castopod SSH access and the OpenAI Agents API.
This guide combines the operator's successful setup with current official Google
documentation checked on 2026-11-01. Console labels can change.

The Ubuntu 26.04.1 migration was validated under the isolated UID: nine helper
guard tests, channel identity, explicit token refresh, repeated channel identity
and reads of an existing owned video and playlist passed. Old secret copies were
removed only afterward. The moved grant remained active; no YouTube content changed.

## What each credential means

An API key can read some public data; it does not authorize channel management.
A client ID identifies your application. A downloaded Desktop OAuth client JSON
configures it. Browser consent produces an authorized-user refresh token for the
selected channel. A client ID ending in `.apps.googleusercontent.com` by itself
is not the complete downloaded configuration or a channel authorization.
Do not use service-account credentials to manage an ordinary YouTube channel.
See [YouTube authentication](https://developers.google.com/youtube/data/guides/authentication).

Keep client JSON, authorized-user JSON and secret upload-recovery state outside
repositories, skills, chat and render artifacts. Use owner-only directories/files
(0700/0600). Desktop apps are public OAuth clients; the refresh token is the
credential that enables ongoing access. Never print either file.

## First-time Google setup

1. Select the intended channel/Brand Account and record its exact `UC…` channel ID
   privately. If you also have a personal channel, do not infer which channel the
   browser will select. Confirm uploads over 15 minutes are enabled when needed at
   [YouTube verification](https://www.youtube.com/verify).
2. Create/select a dedicated [Google Cloud project](https://console.cloud.google.com/).
   In that same project enable
   [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
3. Configure [Google Auth branding](https://console.cloud.google.com/auth/branding)
   and [audience](https://console.cloud.google.com/auth/audience). External Testing
   restricts access to listed testers. For the operator's ongoing personal tool,
   changing to In production resolved `403 access_denied`; its podcast domain also
   had to be added to Authorized domains before publication of the OAuth app.
   Configure domains you control when the console requires them. This publishes
   the OAuth app configuration, not any video. In production and Google verification
   are different states; follow Google's applicable verification rules. A personal-
   use exception is not permission to distribute an unverified public service.
4. Under [Clients](https://console.cloud.google.com/auth/clients), create a **Desktop
   app** OAuth client. For agent use select **Use this client for an AI-powered
   agent** when offered; this is an application classification, not an extra scope
   or an MCP requirement. Google says this setting cannot be changed after creation.
   See [Google's client instructions](https://developers.google.com/workspace/guides/create-credentials#desktop-app).
5. Configure only the scope the existing helper supports:
   `https://www.googleapis.com/auth/youtube.force-ssl`. It includes deletion
   capability; the operator accepts that scope, but a task must still authorize
   each mutation. Do not add Gmail/Drive/profile scopes or `youtube.upload` on top.
   See [YouTube scopes and Desktop OAuth](https://developers.google.com/youtube/data/guides/auth/installed-apps).
6. Save the full client JSON securely at creation, then transfer it privately into
   `~/.config/youtube-publishing/SHOW/client-secret.json` under the isolated UID.
   If you only saved a client ID and the UI no longer offers the secret/download,
   do not delete the client: use the console's secret-management recovery path.
   In the operator's setup, **Client secrets → Add secret** produced a fresh value
   and downloadable JSON. Save it immediately; later secret redisplay is restricted.

Testing-mode external apps using this scope have seven-day refresh-token expiry.
Moving out of Testing avoids that particular limit; it does not make grants immune
to revocation/expiry. [Google's token rules](https://developers.google.com/identity/protocols/oauth2/#expiration)
and [verification exceptions](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification#exceptions-verification-requirements)
explain the distinction.

## Install the helper under the isolated UID

As administrator install system prerequisites (venv support may be an additional
package even when Python itself is installed):

```sh
sudo apt install --no-install-recommends python3 python3-venv ca-certificates openssh-client
```

As the isolated user, from a clean shell with `umask 077`:

```sh
SP_REPO="$HOME/src/sovereign-podcaster"
SP_PYTHON="$HOME/.local/share/sovereign-podcaster/youtube-venv/bin/python"
python3 -m venv "$HOME/.local/share/sovereign-podcaster/youtube-venv"
PIP_CONFIG_FILE=/dev/null "$SP_PYTHON" -m pip --disable-pip-version-check install \
  --index-url https://pypi.org/simple -r "$SP_REPO/skills/youtube-publishing/scripts/requirements.txt"
"$SP_PYTHON" -m unittest discover -s "$SP_REPO/skills/youtube-publishing/scripts" -v
```

The helper and guard tests were reused from the owner's existing skill. It checks
the expected live channel before saving tokens, verifies Google endpoints/scopes,
uses atomic owner-only token writes, and exposes a shared mutation lock. Install
the repo's skill through the selected harness's skills/capability directory; do
not point it at the administrator's old private skills tree. Instance settings stay
in a private operator config, with explicit channel/config-dir values.

## Browser authorization with a remote agent

The helper listens on agent loopback. Your browser runs on the operator machine.
On that operator machine, keep this tunnel open to the **agent machine**:

```sh
ssh -N -L 127.0.0.1:18765:127.0.0.1:18765 podcaster@AGENT_HOST
```

On the agent, as the isolated UID:

```sh
"$SP_PYTHON" "$SP_REPO/skills/youtube-publishing/scripts/youtube_access.py" authorize \
  --config-dir "$HOME/.config/youtube-publishing/SHOW" --channel-id EXPECTED_CHANNEL_ID
```

Open the helper's fresh authorization URL in your own browser and select the
intended channel. Keep that URL out of saved logs; do not copy historical links,
callback codes or a refresh token into chat. PKCE/state and the loopback receiver
handle the callback. Desktop loopback remains supported; Google's deprecation for
mobile client types does not require a web-app client here. If browser and helper
share a machine, omit the tunnel and open the URL locally.

## Move an existing grant before removing its old copy

Reusing the current grant usually needs no browser or new Google account/client.
Stop concurrent operations and hold the shared mutation lock plus any legacy
workspace locks. Reads can also refresh/write token files, so coordinate those.

Transfer the client and authorized-user JSON through a private encrypted stream
into an absent destination, never Git, command-line values, logs or a public temp
file. Preserve secret upload-recovery state separately: a resumable upload URL may
be a bearer credential. Keep completed video/playlist IDs and public receipts.
Use 0700 directories, 0600 regular files, no symlinks and destination ownership.

Validate as the destination UID, using the existing grant:

```sh
SP_CONFIG="$HOME/.config/youtube-publishing/SHOW"
SP_CHANNEL=EXPECTED_CHANNEL_ID
SP_HELPER="$SP_REPO/skills/youtube-publishing/scripts/youtube_access.py"
"$SP_PYTHON" "$SP_HELPER" check --config-dir "$SP_CONFIG" --channel-id "$SP_CHANNEL"
"$SP_PYTHON" "$SP_HELPER" check --refresh --config-dir "$SP_CONFIG" --channel-id "$SP_CHANNEL"
"$SP_PYTHON" "$SP_HELPER" check --config-dir "$SP_CONFIG" --channel-id "$SP_CHANNEL"
```

Also read known existing video/playlist IDs and verify their channel ownership.
These checks make no YouTube mutations; they can refresh/save local token state.
Switch authoritative configuration/callers to the destination and its shared lock.
Only after successful verification and checking that the old source files did not
change during transfer, remove the old credential/recovery copies and confirm
their absence. Leave a nonsecret migration notice so old helpers fail clearly
rather than creating replacement credentials. If validation fails, retain the old
working copy and report the move incomplete.

Do **not revoke the Google grant** when deleting the old local files: that would
also invalidate the moved refresh token. File deletion is not verified secure
erasure from snapshots, backups or SSD history. Access checks and migration do not
authorize uploads, metadata changes, moderation, announcements or publication.
