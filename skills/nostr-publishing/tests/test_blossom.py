import argparse
import base64
from email.message import Message
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('blossom', ROOT / 'tools/blossom.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


class BlossomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.file = self.root / 'clip.mp4'; self.file.write_bytes(b'synthetic MP4 bytes')
        self.asset = b.fingerprint(self.file)
        self.state = dict(self.asset, server='https://media.example', pubkey='a'*64,
                          existed_before=False, upload_acknowledged=True, reused=False)

    def test_plan_never_reads_key_or_contacts_server(self):
        args = argparse.Namespace(server='https://media.example', file=self.file, mime=None,
            origin=['https://viewer.example'], expected_pubkey='a'*64, apply=False, receipt=self.root/'receipt.json')
        with patch.object(b, 'signer', side_effect=AssertionError('key read')), \
                patch.object(b, 'opener', side_effect=AssertionError('network')):
            self.assertTrue(b.upload(args)['dry_run'])
        self.assertFalse(args.receipt.exists())

    def test_cleanup_refuses_preexisting_reused_and_unacknowledged_blobs(self):
        for changes in ({'existed_before': True}, {'reused': True}, {'upload_acknowledged': False}):
            with self.assertRaisesRegex(ValueError, 'Refusing to delete'):
                b.deletion_binding(dict(self.state, **changes), self.state['server'], self.state['pubkey'])

    def test_cleanup_requires_same_server_and_identity(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            b.deletion_binding(self.state, 'https://other.example', self.state['pubkey'])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            b.deletion_binding(self.state, self.state['server'], 'b'*64)

    def test_origin_removal_needs_acknowledgement_complete_list_and_all_heads(self):
        self.assertTrue(b.removal_assessment(204,[404,404],True,False))
        for values in [(None,[404,404],True,False),(204,[404,403],True,False),
                       (204,[404,200],True,False),(204,[],True,False),
                       (204,[404,404],False,False),(204,[404,404],True,True)]:
            self.assertFalse(b.removal_assessment(*values))

    def test_only_not_found_is_absence(self):
        for code in (404, 410, 403, 500):
            client = Mock(); client.open.side_effect = urllib.error.HTTPError('https://media.example/hash', code, '', {}, None)
            if code in (404, 410):
                self.assertIsNone(b.remote_check(client, 'https://media.example/hash', self.asset, 'https://viewer.example', 1))
            else:
                with self.assertRaises(urllib.error.HTTPError):
                    b.remote_check(client, 'https://media.example/hash', self.asset, 'https://viewer.example', 1)

    def test_wrong_remote_bytes_are_rejected(self):
        response = io.BytesIO(b'wrong bytes'); response.status = 200
        response.headers = Message(); response.headers['Content-Type'] = 'video/mp4'
        response.headers['Access-Control-Allow-Origin'] = '*'
        client = Mock(); client.open.return_value = response
        with self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
            b.remote_check(client, 'https://media.example/hash', self.asset, 'https://viewer.example', 1)

    def test_redirects_require_explicit_public_read_origin(self):
        handler = b.PublicReadRedirect(['https://cdn.example'])
        req = urllib.request.Request('https://media.example/hash')
        redirected = handler.redirect_request(req,None,307,'',{},'https://cdn.example/hash')
        self.assertEqual(redirected.full_url,'https://cdn.example/hash')
        for url in ('https://unexpected.example/hash','http://cdn.example/hash','https://user:secret@cdn.example/hash'):
            self.assertIsNone(handler.redirect_request(req,None,307,'',{},url))

    def test_mutations_and_authorization_never_follow_redirects(self):
        handler = b.PublicReadRedirect(['https://cdn.example'])
        for method in ('PUT','DELETE','POST'):
            req = urllib.request.Request('https://media.example/upload',method=method)
            self.assertIsNone(handler.redirect_request(req,None,307,'',{},'https://cdn.example/upload'))
        req = urllib.request.Request('https://media.example/hash',headers={'Authorization':'Nostr synthetic'})
        self.assertIsNone(handler.redirect_request(req,None,307,'',{},'https://cdn.example/hash'))

    def test_delete_token_is_bound_to_action_server_and_exact_hash(self):
        spec = importlib.util.spec_from_file_location('publisher', b.SIGNER)
        publisher = importlib.util.module_from_spec(spec); spec.loader.exec_module(publisher)
        pub = publisher.init_identity(self.root/'identity', 'Test', ['wss://relay.example'])
        identity = self.root/'identity/identity.json'
        m = b.signer(identity, pub['pubkey'])
        token = b.authorization(m, identity, 'https://media.example', self.asset['sha256'], 'delete', 'base64url')
        raw = token.split(' ', 1)[1]; event = json.loads(base64.urlsafe_b64decode(raw + '='*(-len(raw)%4)))
        m.verify(event)
        self.assertIn(['t', 'delete'], event['tags'])
        self.assertIn(['server', 'media.example'], event['tags'])
        self.assertIn(['x', self.asset['sha256']], event['tags'])
        self.assertEqual(event['pubkey'], pub['pubkey'])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            b.signer(identity, 'b'*64)

    def test_mutating_tokens_cannot_omit_the_hash(self):
        m = Mock()
        for action in ('upload','delete'):
            with self.assertRaisesRegex(ValueError,'exact blob hash'):
                b.authorization(m,self.root/'identity.json','https://media.example',None,action,'base64url')
        m.sign_event.assert_not_called()


if __name__ == '__main__': unittest.main()
