"""Offline checks of credential/channel/ownership rejection and shared locking."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import youtube_access as access

CHANNEL = "UC6AHujk9Qxi98Ko4_49oTfg"


class AccessGuards(unittest.TestCase):
    def test_migrated_directory_cannot_start_reauthorization(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "MIGRATED.json").write_text('{}\n')
            with patch.object(access.InstalledAppFlow, 'from_client_config') as flow:
                with self.assertRaises(access.GuardError):
                    access.authorize(temporary, CHANNEL, 18765)
                flow.assert_not_called()

    def test_exact_scope_and_live_channel(self):
        access.validate_scopes(access.SCOPES)
        for scopes in ([], None, [*access.SCOPES, "https://mail.google.com/"]):
            with self.assertRaises(access.GuardError):
                access.validate_scopes(scopes)
        good = {"id": CHANNEL}
        self.assertEqual(access.validate_channel({"items": [good]}, CHANNEL), good)
        for items in ([], [{"id": "another-channel"}], [good, good]):
            with self.assertRaises(access.GuardError):
                access.validate_channel({"items": items}, CHANNEL)

    def test_non_google_client_endpoint(self):
        config = {"installed": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-only",
                                "auth_uri": next(iter(access.AUTH_URIS)), "token_uri": access.TOKEN_URI}}
        access.validate_client(config)
        config["installed"]["token_uri"] = "https://example.org/collect"
        with self.assertRaises(access.GuardError):
            access.validate_client(config)

    def test_private_storage_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            token = Path(temporary) / "config/authorized-user.json"
            access.private_write(token, {"test": "fixture"})
            self.assertEqual(token.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            self.assertEqual(access.private_read(token), {"test": "fixture"})
            link = token.with_name("link.json")
            link.symlink_to(token)
            with self.assertRaises(OSError):
                access.private_read(link)

    def test_wrong_live_channel_does_not_save_or_yield(self):
        with tempfile.TemporaryDirectory() as temporary:
            token = Path(temporary) / "authorized-user.json"
            access.private_write(token, {"scopes": list(access.SCOPES), "verified_channel_id": CHANNEL,
                                         "token_uri": access.TOKEN_URI})
            credentials = Mock(valid=True, granted_scopes=None)
            service = Mock()
            service.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "wrong"}]}
            with patch.object(access.Credentials, "from_authorized_user_info", return_value=credentials), \
                    patch.object(access, "service_for", return_value=service), \
                    patch.object(access, "save_verified") as save:
                with self.assertRaises(access.GuardError):
                    with access.channel_service(temporary, CHANNEL):
                        self.fail("Wrong channel was yielded")
                save.assert_not_called()
            service.close.assert_called_once()

    def test_non_google_saved_endpoint_rejected_before_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            access.private_write(Path(temporary) / "authorized-user.json", {
                "scopes": list(access.SCOPES), "verified_channel_id": CHANNEL,
                "token_uri": "https://example.org/collect"})
            with patch.object(access.Credentials, "from_authorized_user_info") as create:
                with self.assertRaises(access.GuardError):
                    with access.channel_service(temporary, CHANNEL):
                        self.fail("Unexpected access")
                create.assert_not_called()

    def test_owned_resources_reject_foreign_channel(self):
        service = Mock()
        for method, lookup in ((service.videos, access.owned_video), (service.playlists, access.owned_playlist)):
            method.return_value.list.return_value.execute.return_value = {"items": [{"snippet": {"channelId": "foreign"}}]}
            with self.assertRaises(access.GuardError):
                lookup(service, "resource", CHANNEL)

    def test_forced_refresh_rechecks_live_channel_before_saving(self):
        with tempfile.TemporaryDirectory() as temporary:
            access.private_write(Path(temporary) / "authorized-user.json", {
                "scopes": list(access.SCOPES), "verified_channel_id": CHANNEL, "token_uri": access.TOKEN_URI})
            credentials = Mock(valid=True, granted_scopes=None)
            service = Mock()
            service.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": CHANNEL}]}
            with patch.object(access.Credentials, "from_authorized_user_info", return_value=credentials), \
                    patch.object(access, "service_for", return_value=service), \
                    patch.object(access, "save_verified") as save:
                with access.channel_service(temporary, CHANNEL, force_refresh=True) as (_, channel):
                    self.assertEqual(channel["id"], CHANNEL)
                credentials.refresh.assert_called_once()
                save.assert_called_once_with(Path(temporary) / "authorized-user.json", credentials, CHANNEL)

    def test_mutating_contexts_share_a_nonblocking_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            access.private_write(Path(temporary) / "authorized-user.json", {
                "scopes": list(access.SCOPES), "verified_channel_id": CHANNEL, "token_uri": access.TOKEN_URI})
            credentials = Mock(valid=True, granted_scopes=None)
            service = Mock()
            service.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": CHANNEL}]}
            with patch.object(access.Credentials, "from_authorized_user_info", return_value=credentials), \
                    patch.object(access, "service_for", return_value=service), patch.object(access, "save_verified"):
                with access.channel_service(temporary, CHANNEL, mutate=True):
                    with self.assertRaises(BlockingIOError):
                        with access.channel_service(temporary, CHANNEL, mutate=True):
                            self.fail("Concurrent mutation lock was accepted")


if __name__ == "__main__":
    unittest.main()
