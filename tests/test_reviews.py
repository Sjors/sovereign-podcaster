"""Final review UX and exact full-preview binding; no live media or transports."""
import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import reviews


class Response(io.BytesIO):
    def __init__(self,body,size,status=206):
        super().__init__(body)
        self.status=status;self.headers=Message()
        self.headers['Content-Type']='video/mp4'
        self.headers['Content-Range']=f'bytes 0-{min(1023,size-1)}/{size}'
        self.headers['Access-Control-Allow-Origin']='*'


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.data=dict(schema=1,episodes={});self.item=e.initialize(self.root,self.data,'example','7')
        files={}
        for role in ('video','fallback','thumbnail','metadata','nostr_metadata'):
            path=self.root/(role+'.fixture');path.write_bytes((role+' fixture ').encode()*120);files[role]=str(path)
        meta=dict(title='Test episode',description='The exact reviewed description.')
        e.save(Path(files['metadata']),meta)
        e.save(Path(files['nostr_metadata']),dict(d='example-7',**meta,announce=False,announcement='',announcement_mentions=[]))
        task=self.root/'task.json';e.save(task,dict(announce=False));self.item['video_task']=dict(path=str(task))
        self.r=e.revision(self.item,'r1',files);self.asset=self.r['files']['fallback']
        self.config=dict(expected_pubkey='a'*64,draft_servers=['https://media.example.org'],playback_origins=['https://player.example.org'],publication_servers=['https://media.example.org'],publication_relays=['wss://relay.example.org'],marmot_home='/fixture',youtube_channel_id='fixture-channel')
        self.url='https://media.example.org/'+self.asset['sha256']+'.mp4'
        self.receipt=self.root/'draft-receipt.json'
        self.saved=dict(server='https://media.example.org',state='verified',sha256=self.asset['sha256'],size=self.asset['size'],mime='video/mp4',pubkey='a'*64,public_checks=[dict(url=self.url,sha256=self.asset['sha256'],size=self.asset['size'],mime='video/mp4',origin='https://player.example.org',range_verified=True)])
        e.save(self.receipt,self.saved)
        self.item['drafts']['full']=dict(revision='r1',server='https://media.example.org',sha256=self.asset['sha256'],receipt=str(self.receipt))
        self.client=Mock();self.client.open.side_effect=lambda *a,**kw:Response(Path(self.asset['path']).read_bytes()[:1024],self.asset['size'])
        self.sent=[]
        def send(args):
            self.sent.append(e.read(args[-1]))
            return json.dumps(dict(response=dict(message_ids_hex=['f'*64]))).encode()
        for target,options in [('blossom.opener',dict(return_value=self.client)),('reviews.subprocess.check_output',dict(side_effect=send))]:
            patcher=patch(target,**options);mock=patcher.start();self.addCleanup(patcher.stop)
            if target.startswith('reviews'):self.transport=mock
        self.route=dict(account='b'*64,group='c'*64)

    def offer(self,**kwargs):
        return reviews.request(self.root,self.data,self.item,'r1','nostr',self.route,self.config,send=True,include_youtube_public=True,**kwargs)

    def test_full_preview_leads_clear_exact_release_actions_without_hash_clutter(self):
        packet=self.offer();text=self.sent[0]['text']
        self.assertLess(text.index(self.url),text.index('If you approve'))
        self.assertIn('Publish this video on Nostr / Nostube.',text)
        self.assertIn('existing Castopod episode',text)
        self.assertIn('Upload to YouTube privately',text);self.assertIn('make that same video public',text)
        self.assertIn('Announcement: none.',text)
        self.assertEqual(text.count('The exact reviewed description.'),1)
        self.assertNotIn('SHA256',text);self.assertNotIn(self.r['manifest_sha256'],text)
        self.assertIn('approve '+packet['id'],text)
        self.assertEqual(packet['preview']['sha256'],self.asset['sha256'])
        self.assertEqual(packet['manifest_sha256'],self.r['nostr_manifest_sha256'])
        self.assertEqual(e.file_record(packet['preview']['receipt']['path']),packet['preview']['receipt'])
        self.assertEqual(packet['publication_details']['destinations']['publication_relays'],self.config['publication_relays'])
        self.assertEqual(self.item['approvals'],[]);self.assertEqual(self.item['publications'],[])

    def test_prepared_offer_can_be_sent_once_and_confirmed_send_is_reused(self):
        prepared=reviews.request(self.root,self.data,self.item,'r1','nostr',self.route,self.config,include_youtube_public=True)
        self.assertEqual(self.sent,[])
        first=self.offer();second=self.offer()
        self.assertEqual(first['id'],prepared['id']);self.assertEqual(first,second)
        self.assertEqual(len(self.sent),1);self.assertEqual(self.client.open.call_count,1)

    def test_missing_or_invalid_preview_never_sends_or_creates_a_review(self):
        for changes in (dict(state='deleted'),dict(state='uploading'),dict(sha256='0'*64),dict(pubkey='0'*64),dict(size=1),dict(public_checks=[])):
            with self.subTest(changes=changes):
                e.save(self.receipt,dict(self.saved,**changes))
                with self.assertRaises(ValueError):self.offer()
                self.assertEqual(self.item.get('reviews',{}),{});self.assertEqual(self.sent,[])
        e.save(self.receipt,self.saved);self.item['drafts']['full']['revision']='r0'
        with self.assertRaises(ValueError):self.offer()
        self.assertEqual(self.sent,[])

    def test_old_revision_cannot_be_offered_even_when_its_preview_still_exists(self):
        e.revision(self.item,'r2',{role:record['path'] for role,record in self.r['files'].items()})
        with self.assertRaisesRegex(ValueError,'current revision'):self.offer()
        self.assertEqual(self.sent,[])

    def test_link_is_canonical_and_a_failed_live_range_check_does_not_send(self):
        e.save(self.receipt,dict(self.saved,descriptor=dict(url='https://wrong.example.org/clip.mp4')))
        self.assertEqual(self.offer()['preview']['url'],self.url)
        self.item['reviews'].clear();self.sent.clear()
        for status,body in ((200,b'wrong'),(206,b'wrong')):
            self.client.open.side_effect=lambda *a,**kw:Response(body,self.asset['size'],status)
            with self.assertRaisesRegex(ValueError,'no longer playable'):self.offer()
            self.assertEqual(self.sent,[])

    def test_uncertain_send_requires_inspection_without_a_second_transport_call(self):
        self.transport.side_effect=RuntimeError('Synthetic lost transport reply')
        with self.assertRaises(RuntimeError):self.offer()
        self.assertEqual(next(iter(self.item['reviews'].values()))['state'],'sending')
        with self.assertRaisesRegex(ValueError,'uncertain'):self.offer()
        self.assertEqual(self.transport.call_count,1);self.assertEqual(self.client.open.call_count,1)

    def test_old_offer_is_superseded_only_after_full_preview_is_available(self):
        old=reviews.request(self.root,self.data,self.item,'r1','nostr',self.route,self.config,include_youtube_public=True)
        old.pop('message_version');old['state']='sent';self.receipt.unlink()
        with self.assertRaises(ValueError):self.offer()
        self.assertEqual(old['state'],'sent')
        e.save(self.receipt,self.saved);new=self.offer()
        self.assertNotEqual(new['id'],old['id']);self.assertEqual(old['state'],'superseded')
        self.assertEqual(len(self.sent),1)

    def test_separate_public_release_offer_links_only_the_exact_private_id_and_channel(self):
        receipt=dict(verified=True,manifest_sha256=self.r['manifest_sha256'],video_id='exact-private-id',channel_id='fixture-channel',privacy_status='private')
        self.item['publications'].append(dict(stage='youtube-private',manifest_sha256=self.r['manifest_sha256'],receipt=receipt))
        for field,value in [('channel_id','foreign-channel'),('manifest_sha256','0'*64),('privacy_status','public')]:
            changed=dict(receipt,**{field:value})
            with self.assertRaises(ValueError):reviews.preview(self.item,'r1',self.config,dict(receipt=changed))
        packet=reviews.request(self.root,self.data,self.item,'r1','youtube-public',self.route,self.config,send=True)
        self.assertEqual(packet['preview']['url'],'https://www.youtube.com/watch?v=exact-private-id')
        self.assertEqual(self.client.open.call_count,0)
        self.assertIn('Make this same YouTube video public',self.sent[0]['text'])

    def test_announcement_is_an_explicit_separate_action_and_text(self):
        packet=dict(id='fixture-review',include_youtube_private=True)
        path=Path(self.r['files']['nostr_metadata']['path']);meta=e.read(path)
        meta.update(announce=True,announcement='The exact announcement.');e.save(path,meta)
        text=reviews.offer_text(self.item,'r1','nostr',packet,self.config,dict(kind='blossom',url=self.url))
        self.assertIn('Post the announcement shown below.',text)
        self.assertIn('Announcement:\nThe exact announcement.',text)
        self.assertIn('Public release will need a separate approval.',text)
        self.assertNotIn('Announcement: none.',text)


if __name__=='__main__':unittest.main()
