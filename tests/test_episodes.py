import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e

class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data={'schema':1,'episodes':{}}
        self.item=e.initialize(self.root,self.data,'fixture','one')
        self.files={}
        for role in ('video','fallback','thumbnail','metadata'):
            path=self.root/(role+'.fixture');path.write_text('synthetic '+role);self.files[role]=str(path)
        self.rev=e.revision(self.item,'r1',self.files);self.sha=self.rev['manifest_sha256']
        self.evidence=self.root/'human-message.txt';self.evidence.write_text('Synthetic test approval; not a real operator instruction')

    def receipt(self,stage,**kw):
        path=self.root/(stage+'.json');path.write_text(json.dumps(dict(manifest_sha256=self.rev['nostr_manifest_sha256'] if stage=='nostr' else self.sha,verified=True,**kw)));return path

    def publish(self):
        e.approve(self.item,'r1','nostr',self.evidence)
        e.record_publication(self.item,'r1','nostr',self.receipt('nostr',video_event_id='a'*64,announcement_event_id='b'*64,blobs=[{'server':'https://example.org','sha256':'c'*64}]))
        e.record_publication(self.item,'r1','youtube-private',self.receipt('private',video_id='fixture-video',channel_id='fixture-channel',privacy_status='private'))
        e.approve(self.item,'r1','youtube-public',self.evidence)
        e.record_publication(self.item,'r1','youtube-public',self.receipt('public',video_id='fixture-video',channel_id='fixture-channel',privacy_status='public'))

    def draft(self,identifier,sha,**kw):
        path=self.root/(identifier+'.json');e.save(path,{'state':'verified','server':'https://example.org','sha256':sha,'existed_before':False,'upload_acknowledged':True,'reused':False,**kw})
        self.item['drafts'][identifier]={'server':'https://example.org','sha256':sha,'receipt':str(path)}

    def test_cleanup_waits_for_both_final_platforms(self):
        with self.assertRaisesRegex(ValueError,'cleanup waits'):e.cleanup_plan(self.data,self.item)
        self.publish();self.assertTrue(e.complete(self.item))

    def test_public_youtube_approval_requires_private_review_and_same_video(self):
        with self.assertRaisesRegex(ValueError,'private YouTube'):e.approve(self.item,'r1','youtube-public',self.evidence)
        self.publish()
        with self.assertRaisesRegex(ValueError,'same private video'):
            e.record_publication(self.item,'r1','youtube-public',self.receipt('wrong-video',video_id='different',channel_id='fixture-channel',privacy_status='public'))

    def test_modified_artifacts_invalidate_prior_approval(self):
        self.publish();Path(self.files['metadata']).write_text('changed metadata')
        with self.assertRaisesRegex(ValueError,'bytes changed'):e.approve(self.item,'r1','nostr',self.evidence)
        with self.assertRaisesRegex(ValueError,'bytes changed'):e.cleanup(self.root,self.data,self.item,{},False)

    def test_cleanup_retains_final_shared_and_preexisting_blobs(self):
        self.publish();self.draft('final','c'*64);self.draft('shared','d'*64);self.draft('temporary','e'*64)
        self.draft('preexisting','f'*64,existed_before=True)
        other=e.initialize(self.root,self.data,'fixture','two');other['drafts']['reused']={'server':'https://example.org','sha256':'d'*64}
        choices={d['id']:d['decision'] for d in e.cleanup_plan(self.data,self.item)}
        self.assertEqual(choices,{'final':'retained-reference','shared':'retained-reference','temporary':'delete','preexisting':'retained-reused-or-uncertain'})

    def test_youtube_metadata_revision_preserves_nostr_publication_but_requires_new_review(self):
        self.publish();Path(self.files['metadata']).write_text('revised YouTube description')
        updated=e.revision(self.item,'r2',self.files)
        self.assertEqual(updated['nostr_manifest_sha256'],self.rev['nostr_manifest_sha256'])
        self.assertIsNotNone(e.published(self.item,'nostr',updated['nostr_manifest_sha256']))
        self.assertFalse(e.complete(self.item))
        self.assertIsNone(e.approval(self.item,'youtube-public',updated['manifest_sha256']))

    def test_cleanup_dry_run_has_no_network_or_subprocess(self):
        self.publish();self.draft('temporary','e'*64)
        with patch.object(e.subprocess,'run') as run:
            self.assertEqual(e.cleanup(self.root,self.data,self.item,{},False)[0]['decision'],'delete');run.assert_not_called()

    def test_changed_receipt_cannot_delete_an_unregistered_hash(self):
        self.publish();self.draft('temporary','e'*64)
        receipt=Path(self.item['drafts']['temporary']['receipt']);value=e.read(receipt);value['sha256']='9'*64;e.save(receipt,value)
        with patch.object(e.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'registered server/hash'):e.cleanup(self.root,self.data,self.item,{},True)
            run.assert_not_called()

    def test_apply_cleanup_without_operator_guard_never_calls_transport(self):
        self.publish();self.draft('temporary','e'*64)
        with patch.object(e.subprocess,'run') as run:
            with self.assertRaises(KeyError):e.cleanup(self.root,self.data,self.item,{},True)
            run.assert_not_called()

    def test_missing_stop_guard_blocks_mutations(self):
        with self.assertRaises((KeyError,ValueError,OSError)):e.guard({},'draft-delete')

    def test_episode_root_in_git_is_refused(self):
        (self.root/'.git').mkdir();(self.root/'.git/HEAD').write_text('ref: refs/heads/fixture\n')
        with self.assertRaisesRegex(ValueError,'outside Git'):e.private_root(self.root/'episode-state')

if __name__=='__main__':unittest.main()
