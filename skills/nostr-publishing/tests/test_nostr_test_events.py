import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('test_events', ROOT/'tools/nostr_test_events.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)


class TestEventCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.m = t.signer()
        pub = self.m.init_identity(self.root/'keys','Test',['wss://relay.example'])
        self.pubkey = pub['pubkey']; self.identity = self.root/'keys/identity.json'
        self.bundle = self.root/'bundle'; self.bundle.mkdir()
        self.d = 'sovereign-podcaster-test-synthetic'
        for stem,kind,tags in [('video',34235,[['d',self.d]]),('note',1,[])]:
            event = dict(pubkey=self.pubkey,created_at=1790000000,kind=kind,tags=tags,content='Temporary test')
            t.write_new(self.bundle/(stem+'.unsigned.json'),event)
        manifest = dict(purpose=t.PURPOSE,pubkey=self.pubkey,d=self.d,unsigned_sha256={
            p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.bundle.glob('*.unsigned.json')})
        t.write_new(self.bundle/'manifest.json',manifest)
        t.sign(argparse.Namespace(bundle=self.bundle,identity=self.identity))

    def test_deletion_targets_only_bound_test_ids_and_unique_address(self):
        event = t.deletion(argparse.Namespace(bundle=self.bundle))
        ids = {json.loads(p.read_text())['id'] for p in self.bundle.glob('*.signed.json')}
        self.assertEqual({tag[1] for tag in event['tags'] if tag[0]=='e'},ids)
        self.assertIn(['a',f'34235:{self.pubkey}:{self.d}'],event['tags'])
        self.assertEqual(t.deletion(argparse.Namespace(bundle=self.bundle)),event)

    def test_substituting_another_valid_note_blocks_cleanup(self):
        production = self.m.sign_event(self.identity,dict(kind=1,content='Existing production announcement'))
        (self.bundle/'note.signed.json').write_text(json.dumps(production))
        with self.assertRaisesRegex(ValueError,'does not match prepared test'):
            t.deletion(argparse.Namespace(bundle=self.bundle))
        self.assertFalse((self.bundle/'deletion.unsigned.json').exists())

    def test_production_address_blocks_cleanup(self):
        p = self.bundle/'manifest.json';v=json.loads(p.read_text());v['d']='episode-100';p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'Only a generated temporary test'):
            t.deletion(argparse.Namespace(bundle=self.bundle))


if __name__=='__main__':unittest.main()
