#!/usr/bin/env python3
"""Explicit-channel YouTube OAuth access; CLI authorizes or checks identity only."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import stat
import tempfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ("https://www.googleapis.com/auth/youtube.force-ssl",)
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URIS = {"https://accounts.google.com/o/oauth2/auth", "https://accounts.google.com/o/oauth2/v2/auth"}


class GuardError(Exception):
    pass


def validate_scopes(scopes):
    actual = set(scopes.split() if isinstance(scopes, str) else scopes or ())
    if actual != set(SCOPES):
        raise GuardError("Expected exactly the agreed YouTube-only scope.")


def validate_channel(response, expected):
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", expected):
        raise GuardError("An explicit valid expected YouTube channel ID is required.")
    items = response.get("items", [])
    if len(items) != 1 or items[0].get("id") != expected:
        raise GuardError("Live OAuth channel differs from the expected channel; no token saved.")
    return items[0]


def validate_client(value):
    installed = value.get("installed", {})
    if not installed.get("client_id", "").endswith(".apps.googleusercontent.com") or not installed.get("client_secret"):
        raise GuardError("Desktop OAuth client JSON with ID and secret is required.")
    if installed.get("token_uri") != TOKEN_URI or installed.get("auth_uri") not in AUTH_URIS:
        raise GuardError("Client must use the standard Google OAuth endpoints.")
    return value


def private_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise GuardError("Credentials must be a regular file owned by the execution user.")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd) as handle:
            fd = -1
            return json.load(handle)
    finally:
        if fd != -1:
            os.close(fd)


def private_directory(path):
    path = Path(path)
    if (path / "MIGRATED.json").exists():
        raise GuardError("This credential directory was migrated; use its new authoritative location.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise GuardError("Private config directory must be owned by the execution user, not a symlink.")
    path.chmod(0o700)
    return path


def private_write(path, value):
    path = Path(path)
    private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".youtube-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def service_for(credentials):
    return build("youtube", "v3", credentials=credentials,
                 cache_discovery=False, static_discovery=True)


def live_channel(service, expected):
    return validate_channel(service.channels().list(
        part="id,snippet", mine=True, fields="items(id,snippet/title)"
    ).execute(num_retries=2), expected)


def save_verified(path, credentials, expected):
    payload = json.loads(credentials.to_json())
    payload.update(scopes=list(SCOPES), verified_channel_id=expected,
                   verified_at=datetime.now(timezone.utc).isoformat())
    private_write(path, payload)


@contextmanager
def channel_service(config_dir, expected_channel_id, mutate=False, force_refresh=False):
    """Yield (SDK, verified channel); optional shared lock covers the whole operation."""
    logging.disable(logging.CRITICAL)
    config = private_directory(config_dir)
    lock = None
    service = None
    try:
        if mutate:
            fd = os.open(config / "channel-mutation.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            lock = os.fdopen(fd, "w")
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        token = config / "authorized-user.json"
        value = private_read(token)
        validate_scopes(value.get("scopes"))
        if value.get("verified_channel_id") != expected_channel_id or value.get("token_uri") != TOKEN_URI:
            raise GuardError("Saved grant has the wrong expected channel or token endpoint.")
        credentials = Credentials.from_authorized_user_info(value, scopes=list(SCOPES))
        if force_refresh or not credentials.valid:
            credentials.refresh(Request())
        if credentials.granted_scopes is not None:
            validate_scopes(credentials.granted_scopes)
        service = service_for(credentials)
        channel = live_channel(service, expected_channel_id)
        save_verified(token, credentials, expected_channel_id)
        yield service, channel
    finally:
        if service is not None:
            service.close()
        if lock is not None:
            lock.close()


def owned_video(service, video_id, expected_channel_id, part="snippet,status"):
    if "snippet" not in part.split(","):
        raise GuardError("Ownership reads must include snippet.")
    items = service.videos().list(part=part, id=video_id).execute(num_retries=2).get("items", [])
    if len(items) != 1 or items[0].get("snippet", {}).get("channelId") != expected_channel_id:
        raise GuardError("Video is missing or belongs to another channel.")
    return items[0]


def owned_playlist(service, playlist_id, expected_channel_id, part="snippet,status,contentDetails"):
    if "snippet" not in part.split(","):
        raise GuardError("Ownership reads must include snippet.")
    items = service.playlists().list(part=part, id=playlist_id).execute(num_retries=2).get("items", [])
    if len(items) != 1 or items[0].get("snippet", {}).get("channelId") != expected_channel_id:
        raise GuardError("Playlist is missing or belongs to another channel.")
    return items[0]


def authorize(config_dir, expected, port):
    config = private_directory(config_dir)
    configuration = validate_client(private_read(config / "client-secret.json"))
    flow = InstalledAppFlow.from_client_config(configuration, scopes=list(SCOPES), autogenerate_code_verifier=True)
    credentials = flow.run_local_server(
        host="127.0.0.1", bind_addr="127.0.0.1", port=port, open_browser=False,
        timeout_seconds=600, prompt="consent select_account", include_granted_scopes="false",
        authorization_prompt_message="Open this URL and choose the intended YouTube channel:\n{url}",
        success_message="Authorization received. Check the terminal for channel verification.")
    validate_scopes(flow.oauth2session.token.get("scope"))
    if not credentials.refresh_token:
        raise GuardError("No offline refresh token returned; credentials not saved.")
    service = service_for(credentials)
    try:
        channel = live_channel(service, expected)
        save_verified(config / "authorized-user.json", credentials, expected)
        return channel
    finally:
        service.close()


def main():
    logging.disable(logging.CRITICAL)
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "authorize"))
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--refresh", action="store_true", help="Force a refresh-token exchange during check.")
    args = parser.parse_args()
    try:
        if args.command == "authorize":
            channel = authorize(args.config_dir, args.channel_id, args.port)
        else:
            with channel_service(args.config_dir, args.channel_id, force_refresh=args.refresh) as (_, channel):
                pass
        print(json.dumps({"verified_channel_id": channel["id"],
                          "title": channel.get("snippet", {}).get("title"),
                          "scopes": list(SCOPES), "youtube_writes_performed": False}, indent=2))
    except GuardError as error:
        parser.exit(1, str(error) + "\n")
    except Exception as error:
        parser.exit(1, f"YouTube access failed ({type(error).__name__}); secret-bearing details suppressed.\n")


if __name__ == "__main__":
    main()
