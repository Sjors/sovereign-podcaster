import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).resolve().parents[1] / 'scripts/nostr_publish.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NostrPublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'identity'
        self.public = m.init_identity(self.folder, 'Test', ['wss://relay.example'])
        self.identity = self.folder / 'identity.json'

    def event(self):
        return m.sign_event(self.identity, dict(kind=0, tags=[], content='Unicode: é 🌪️', created_at=1790000000))

    def test_signature_and_tamper_detection(self):
        event = self.event()
        m.verify(event)
        event['content'] += 'tampered'
        with self.assertRaisesRegex(ValueError, 'ID mismatch'):
            m.verify(event)

    def test_cannot_change_author(self):
        with self.assertRaisesRegex(ValueError, 'different author'):
            m.sign_event(self.identity, dict(kind=0, pubkey='00'*32, content='test'))

    def test_private_key_permissions_and_no_overwrite(self):
        path = self.folder / 'secret.hex'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            m.init_identity(self.folder, 'Test', ['wss://relay.example'])
        os.chmod(path, 0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            self.event()

    def test_identity_creation_refuses_repository_and_symlink(self):
        root = Path(self.temp.name)
        git = root / 'repository' / '.git'
        git.mkdir(parents=True)
        (git / 'HEAD').write_text('ref: refs/heads/main\n')
        with self.assertRaisesRegex(ValueError, 'outside Git'):
            m.init_identity(git.parent / 'keys', 'Test', ['wss://relay.example'])
        self.assertFalse((git.parent / 'keys' / 'secret.hex').exists())
        link = root / 'linked-identity'
        link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            m.init_identity(link, 'Test', ['wss://relay.example'])

    def test_sign_does_not_copy_extra_fields(self):
        event = m.sign_event(self.identity, dict(kind=0, content='test', private_data='do not serialize'))
        self.assertNotIn('private_data', event)

    def test_retired_identity_cannot_be_loaded_or_regenerated(self):
        (self.folder / 'MIGRATED.json').write_text('{"migrated": true}')
        with self.assertRaisesRegex(ValueError, 'Identity migrated'):
            self.event()
        (self.folder / 'secret.hex').unlink(); self.identity.unlink()
        with self.assertRaisesRegex(ValueError, 'Identity migrated'):
            m.init_identity(self.folder, 'Test', ['wss://relay.example'])

    def test_nip19_reference_encoding(self):
        pub = bytes.fromhex('3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d')
        self.assertEqual(m.encode('npub', pub), 'npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6')

    def test_no_secret_in_public_result(self):
        secret = (self.folder / 'secret.hex').read_text().strip()
        self.assertNotIn(secret, json.dumps(self.public))
        self.assertNotIn(secret, json.dumps(self.event()))

    def test_longform_address_and_first_publication_metadata(self):
        event = m.article_event('## Subtitle\n\nText.', 'Title', 'stable-slug', 'Summary', 1790000000)
        self.assertEqual(event['kind'], 30023)
        self.assertIn(['d', 'stable-slug'], event['tags'])
        self.assertIn(['published_at', '1790000000'], event['tags'])
        with self.assertRaisesRegex(ValueError, 'without HTML'):
            m.article_event('<audio src="file.mp3"></audio>', 'Title', 'slug', 'Summary', 1790000000)

    @patch.object(m, 'publish_relay', return_value={'accepted': True, 'message': ''})
    @patch.object(m, 'query_relay', return_value={'events': []})
    def test_acknowledgement_is_not_retrieval(self, query, publish):
        result = m.publish_and_check('wss://relay.example', self.event())
        self.assertTrue(result['accepted'])
        self.assertFalse(result['retrieved'])

    @patch.object(m, 'publish_relay', return_value={'accepted': True, 'message': ''})
    @patch.object(m, 'query_relay', side_effect=TimeoutError('readback timeout'))
    def test_readback_timeout_retains_actual_acknowledgement(self, query, publish):
        result = m.publish_and_check('wss://relay.example', self.event())
        self.assertTrue(result['accepted'])
        self.assertFalse(result['retrieved'])
        self.assertIn('query_error', result)

    def test_insecure_relay_refused(self):
        with self.assertRaises(ValueError):
            m.relay_urls(['ws://relay.example'])


if __name__ == '__main__':
    unittest.main()
