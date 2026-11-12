"""Synthetic production invariants; no credentials or external services."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import blossom
import jobs
import produce
import publish
import reviews
import reviews_operator
import transcript
from array import array
import math
from video.verify_mp4 import alignment
from video import hls, av1_packaging, youtube
from video.nostr import metadata as nostr_metadata

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.root.chmod(0o700)

    def test_edits_preserve_words_and_reject_a_cut_crossing_a_cue(self):
        cues=[dict(start=1,end=3,speaker='host',text='Whole sentence.'),dict(start=6,end=8,speaker='guest',text='Keep me too.')]
        segments,duration=produce.timeline(dict(edit=[dict(source_start=0,source_end=4),dict(silence_duration=2,title='Break'),dict(source_start=5,source_end=10)]),10)
        result=produce.map_cues(cues,segments)
        self.assertEqual([c['start'] for c in result],[1,7]);self.assertEqual(duration,11)
        with self.assertRaisesRegex(ValueError,'crosses'):produce.map_cues(cues,[dict(start=0,end=2,source_start=2,source_end=4)])
        with self.assertRaisesRegex(ValueError,'ordered'):produce.timeline(dict(edit=[dict(source_start=5,source_end=8),dict(source_start=1,source_end=2)]),10)

    def test_alignment_recovers_aac_priming_without_false_coarse_match(self):
        raw=array('f',(.2*math.sin(2*math.pi*(180*(i/12000)+80*(i/12000)**2))*(.4+.6*math.sin(2*math.pi*1.37*i/12000)**2) for i in range(72000)))
        delayed=array('f',[0]*256)+raw[:-256]
        with patch('video.verify_mp4.audio_samples',side_effect=lambda path,*args:raw if path=='source' else delayed):
            observations=alignment('source','encoded',20,.15)
            self.assertTrue(all(abs(o['delay_seconds']-256/12000)<1/12000 for o in observations))
            self.assertTrue(all(o['correlation']>.99 for o in observations))
        with patch('video.verify_mp4.audio_samples',side_effect=lambda path,*args:raw if path=='source' else array('f',[0]*len(raw))):
            with self.assertRaises(ValueError):alignment('source','wrong-audio',20,.15)

    def test_vtt_import_never_silently_skips_an_unattributed_cue(self):
        raw='WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Host>Reviewed &amp; exact words.</v>\n'
        cue=transcript.parse(raw)[0];self.assertEqual(cue['speaker'],'Host');self.assertEqual(cue['text'],'Reviewed & exact words.')
        with self.assertRaises(ValueError):transcript.parse(raw.replace('<v Host>','').replace('</v>',''))
        self.assertEqual(transcript.parse(raw.replace('<v Host>','').replace('</v>',''),'Explicit host')[0]['speaker'],'Explicit host')

    def test_hls_content_addressing_dependency_order_and_tampering(self):
        out=self.root/'bundle';(out/'hls/480p').mkdir(parents=True)
        (out/'hls/master.m3u8').write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=123\n480p/index.m3u8\n')
        (out/'hls/480p/index.m3u8').write_text('#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:6,\nchunk.m4s\n')
        (out/'hls/480p/init.mp4').write_bytes(b'init');(out/'hls/480p/chunk.m4s').write_bytes(b'chunk')
        fallback=self.root/'fallback.mp4';fallback.write_bytes(b'exact original fallback')
        assets,master,sha=hls.package_hls(out,fallback)
        e.save(out/'bundle.json',dict(version=1,assets=assets,master_sha256=master,fallback_sha256=sha))
        hls.validate_bundle(out);self.assertEqual((out/'blobs'/sha).read_bytes(),fallback.read_bytes())
        (out/'blobs'/master).write_text('#EXTM3U\nhttps://attacker.invalid/segment\n')
        with self.assertRaises(ValueError):hls.validate_bundle(out)
        with self.assertRaises(ValueError):hls.local_child(out/'hls','../../../etc/passwd',out/'hls')

    def test_av1_codec_and_peak_bandwidth(self):
        self.assertEqual(av1_packaging.av1_codec_string(bytes.fromhex('81080c00')),'av01.0.08M.08')
        with self.assertRaises(ValueError):av1_packaging.av1_codec_string(b'bad')
        paths=[]
        for i,size in enumerate((60,120,30)):
            path=self.root/str(i);path.write_bytes(b'a'*size);paths.append(path)
        result=av1_packaging.bandwidth(paths,[6,6,2]);self.assertGreaterEqual(result['peak_bandwidth'],160)

    def episode(self):
        data=dict(schema=1,episodes={});item=e.initialize(self.root,data,'show','one');files={}
        for name in ('video','fallback','thumbnail','metadata','captions','nostr_bundle','nostr_metadata'):
            path=self.root/(name+'.json');e.save(path,{'title':'Fixture','description':'Synthetic'}) if name=='metadata' else path.write_text('fixture '+name);files[name]=str(path)
        e.save(Path(files['nostr_metadata']),dict(d='fixture-one',title='Fixture',description='Reviewed description',announcement='Reviewed announcement'))
        revision=e.revision(item,'r1',files);e.save(self.root/'episodes.json',data);return data,item,revision

    def approved(self,data,item,scope,config):
        route=dict(account='a'*64,group='b'*64);packet=reviews.request(self.root,data,item,'r1',scope,route,config)
        packet.update(state='sent',message_ids=['f'*64])
        incoming=dict(**route,sender='c'*64,message_id='d'*64,text='approve '+packet['id'],recorded_at=1,reply_to=None)
        reviews.accept(self.root,data,incoming);return packet,incoming

    def test_approval_is_bound_to_artifacts_route_scope_destination_and_message(self):
        data,item,r=self.episode();config=dict(destination='fixture')
        packet,incoming=self.approved(data,item,'nostr',config)
        reviews.require(item,'nostr',r['nostr_manifest_sha256'],config)
        self.assertIn('already approved',reviews.accept(self.root,data,incoming));self.assertEqual(len(item['approvals']),1)
        self.assertIsNone(reviews.accept(self.root,data,dict(incoming,text='yes',message_id='e'*64)))
        with self.assertRaises(RuntimeError):reviews.accept(self.root,data,dict(incoming,group='e'*64))
        with self.assertRaises(ValueError):reviews.require(item,'nostr',r['nostr_manifest_sha256'],dict(destination='changed'))
        Path(r['files']['video']['path']).write_text('changed video')
        with self.assertRaises(ValueError):reviews.accept(self.root,data,incoming)

    def test_combined_review_allows_nostr_then_private_but_not_public(self):
        data,item,r=self.episode();route=dict(account='a'*64,group='b'*64)
        packet=reviews.request(self.root,data,item,'r1','nostr',route,{},include_youtube_private=True)
        packet.update(state='sent',message_ids=['f'*64])
        reviews.accept(self.root,data,dict(**route,sender='c'*64,message_id='d'*64,text='approve '+packet['id'],recorded_at=1,reply_to=None))
        reviews.require(item,'nostr',r['nostr_manifest_sha256'],{})
        reviews.require(item,'youtube-private',r['manifest_sha256'],{})
        with self.assertRaises(ValueError):reviews.require(item,'youtube-public',r['manifest_sha256'],{})

    def test_direct_operator_approval_preserves_source_and_exact_bindings(self):
        data,item,r=self.episode();config=dict(destination='fixture')
        path=self.root/'operator.json'
        grant=dict(source='explicit-maintainer-user-request',show='show',episode='one',revision='r1',
                   scopes=['nostr','youtube-private','youtube-public'],manifest_sha256=r['manifest_sha256'],
                   nostr_manifest_sha256=r['nostr_manifest_sha256'],configuration_sha256=e.digest(config),
                   human_request='Synthetic fixture authorization',approval_context='Synthetic direct operator test')
        e.save(path,grant)
        reviews_operator.record(self.root,'show','one','r1','nostr',path,config)
        saved=e.read(self.root/'episodes.json')['episodes']['show/one']
        approval=reviews.require(saved,'nostr',r['nostr_manifest_sha256'],config)
        self.assertNotIn('authenticated',approval);self.assertNotIn('message_id',approval)
        with self.assertRaises(ValueError):reviews.require(saved,'nostr',r['nostr_manifest_sha256'],{'changed':True})
        with self.assertRaises(ValueError):reviews_operator.record(self.root,'show','one','r1','youtube-public',path,config)
        saved['current_revision']='r2'
        with self.assertRaises(ValueError):reviews.require(saved,'nostr',r['nostr_manifest_sha256'],config)
        saved['current_revision']='r1';Path(approval['evidence']['path']).write_text('{}')
        with self.assertRaises(ValueError):reviews.require(saved,'nostr',r['nostr_manifest_sha256'],config)

    def test_direct_operator_rejects_scope_and_revision_changes_without_recording(self):
        data,item,r=self.episode();path=self.root/'operator.json'
        e.save(path,dict(source='explicit-maintainer-user-request',show='show',episode='other',revision='r1',scopes=['nostr']))
        with self.assertRaises(ValueError):reviews_operator.record(self.root,'show','one','r1','nostr',path,{})
        self.assertEqual(e.read(self.root/'episodes.json')['episodes']['show/one']['approvals'],[])

    def test_publisher_requires_approval_and_records_once_before_resuming(self):
        data,item,r=self.episode();config=dict(maintenance_guard='/missing-fixture-guard');config_path=self.root/'config.json';e.save(config_path,config)
        args=types.SimpleNamespace(root=self.root,show='show',episode='one',revision='r1',config=config_path,stage='nostr',apply=True)
        receipt=dict(verified=True,manifest_sha256=r['nostr_manifest_sha256'],video_event_id='a'*64,announcement_event_id='b'*64,blobs=[dict(server='https://example.org',sha256='c'*64)])
        with patch.object(publish,'nostr',return_value=receipt) as send,patch.object(e,'guard') as guard:
            with self.assertRaises(ValueError):publish.publish(args,config)
            send.assert_not_called()
            self.approved(data,item,'nostr',config)
            publish.publish(args,config);publish.publish(args,config)
            self.assertEqual(send.call_count,1);self.assertGreaterEqual(guard.call_count,2)
            saved=e.read(self.root/'episodes.json')['episodes']['show/one'];self.assertEqual(len(saved['publications']),1)
            Path(r['files']['fallback']['path']).write_text('tampered')
            with self.assertRaises(ValueError):publish.publish(args,config)
            self.assertEqual(send.call_count,1)

    def test_complete_nostr_transport_reuses_signed_ids_and_exact_hls_readbacks(self):
        data,item,r=self.episode();directory=self.root/'hls';directory.mkdir();assets=[]
        for role,mime,content in [('fallback','video/mp4','fixture fallback'),('segment','video/iso.segment','segment'),('master',hls.HLS_MIME,'master')]:
            path=directory/(role+'.blob');path.write_text(content);rec=e.file_record(path);assets.append(dict(role=role,mime=mime,sha256=rec['sha256'],size=rec['size'],path=path.name))
        r['files']['fallback']=e.file_record(directory/'fallback.blob')
        e.save(directory/'bundle.json',{});r['files']['nostr_bundle']=e.file_record(directory/'bundle.json')
        e.save(directory/'media-verification.json',dict(complete=True,variants=[dict(full_hls_decode_passed=True)]))
        meta=self.root/'nostr-meta.json';native_text='Discussing the episode with nostr:npub1fixture.\n\nhttps://podcast.example.org/one'
        e.save(meta,dict(d='fixture-one',title='Fixture',description=native_text,announcement='Watch this episode.',source_url='https://podcast.example.org/one',participants=['b'*64,'c'*64],announcement_mentions=['c'*64]))
        r['files']['nostr_metadata']=e.file_record(meta)
        fallback=dict(sha256=assets[0]['sha256'],size=assets[0]['size'],width=854,height=480,duration=20,average_bitrate=1000,codecs='av01.0.08M.08,mp4a.40.2')
        bundle=dict(version=2,policy='av1-15fps-aac64-mono-6s',assets=assets,master_sha256=assets[-1]['sha256'],fallback_sha256=assets[0]['sha256'],fallback=fallback,variants=[dict(duration=20)])
        config=dict(expected_pubkey='a'*64,identity_file='/fixture/identity.json',publication_servers=['https://example.org'],publication_relays=['wss://relay.example.org'],playback_origins=['https://player.example.org'],nostr_python='/fixture/python')
        signer=Mock();signer.load_identity.return_value={'pubkey':'a'*64};signer.relay_urls.side_effect=lambda x:x
        signer.query_relay.return_value=dict(complete=True,events=[])
        def signed(identity,unsigned):return dict(unsigned,id=e.digest(unsigned),sig='f'*128)
        signer.sign_event.side_effect=signed;signer.convertbits.side_effect=lambda *a:a[0];signer.bech32_encode.side_effect=lambda prefix,data:prefix+'1fixture'
        signer.publish_and_check.return_value=dict(accepted=True,retrieved=True)
        order=[]
        def upload(args,**kw):
            source=Path(args[args.index('--file')+1]);receipt=Path(args[args.index('--receipt')+1]);order.append(source.name)
            e.save(receipt,dict(state='verified',sha256=e.file_record(source)['sha256'],server='https://example.org'))
        def readback(client,url,asset,origin,timeout):return dict(url=url,origin=origin,sha256=asset['sha256'])
        folder=self.root/'release';folder.mkdir()
        with patch.object(publish,'module',return_value=signer),patch.object(hls,'validate_bundle',return_value=bundle),patch.object(publish.subprocess,'run',side_effect=upload),patch.object(blossom,'opener'),patch.object(blossom,'remote_check',side_effect=readback):
            native=publish.nostr(config,r,'b'*64,folder,lambda:None,phase='video')
            self.assertNotIn('announcement_event_id',native)
            self.assertEqual(signer.publish_and_check.call_count,1)
            with self.assertRaises(ValueError):publish.nostr(config,r,'b'*64,folder,lambda:None,phase='announcement')
            self.assertEqual(signer.publish_and_check.call_count,1)
            link=self.root/'castopod.json'
            e.save(link,dict(verified=True,manifest_sha256='b'*64,video_event_id=native['video_event_id'],identifier='naddr1fixture',episode_url='https://podcast.example.org/one'))
            first=publish.nostr(config,r,'b'*64,folder,lambda:None,phase='announcement',castopod_receipt=link)
            self.assertEqual(len(order),3)  # announcing never reuploads assets
            second=publish.nostr(config,r,'b'*64,folder,lambda:None)
        self.assertTrue(first['verified']);self.assertEqual(first['video_event_id'],second['video_event_id']);self.assertEqual(signer.sign_event.call_count,2)
        self.assertEqual(set(order[:2]),{'fallback.blob','segment.blob'});self.assertEqual(order[2],'master.blob')
        self.assertEqual(len(first['hls_public_readback']),3)
        self.assertTrue(any(x['url'].endswith('.m3u8') for x in first['hls_public_readback']))
        events=e.read(folder/'events.json');self.assertIn('nostr:naddr',events['announcement']['content'])
        self.assertEqual(events['video']['content'],native_text)
        self.assertEqual(events['announcement']['content'],'Watch this episode.\n\nnostr:naddr1fixture')
        self.assertEqual([t for t in events['video']['tags'] if t[0]=='p'],[['p','b'*64],['p','c'*64]])
        self.assertEqual([t for t in events['announcement']['tags'] if t[0]=='p'],[['p','c'*64]])
        self.assertIn(['r','https://podcast.example.org/one'],events['video']['tags'])

        # A back catalogue release signs/publishes only the native video, and
        # cannot be switched to an announcement phase on retry.
        quiet=self.root/'quiet-release';quiet.mkdir()
        value=e.read(meta);value.update(announce=False,announcement='',announcement_mentions=[]);e.save(meta,value)
        signer.reset_mock()
        with patch.object(publish,'module',return_value=signer),patch.object(hls,'validate_bundle',return_value=bundle),patch.object(publish.subprocess,'run',side_effect=upload),patch.object(blossom,'opener'),patch.object(blossom,'remote_check',side_effect=readback):
            result=publish.nostr(config,r,'c'*64,quiet,lambda:None)
            self.assertTrue(result['announcement_skipped']);self.assertEqual(result['identifier'],'naddr1fixture')
            self.assertNotIn('announcement_event_id',result)
            self.assertEqual(signer.sign_event.call_count,1);self.assertEqual(signer.sign_event.call_args.args[1]['kind'],34235)
            self.assertEqual(signer.publish_and_check.call_count,1)
            with self.assertRaisesRegex(ValueError,'forbids announcements'):publish.nostr(config,r,'c'*64,quiet,lambda:None,phase='announcement')

    def test_full_release_approval_binds_verified_private_id_without_another_human_message(self):
        data,item,r=self.episode();route=dict(account='a'*64,group='b'*64);config={}
        packet=reviews.request(self.root,data,item,'r1','nostr',route,config,include_youtube_public=True)
        packet.update(state='sent',message_ids=['f'*64])
        incoming=dict(**route,sender='c'*64,message_id='d'*64,text='approve '+packet['id'],recorded_at=1,reply_to=None)
        reviews.accept(self.root,data,incoming)
        with self.assertRaises(ValueError):reviews.bind_public(item,'r1',config)
        receipt=self.root/'private.json';e.save(receipt,dict(verified=True,manifest_sha256=r['manifest_sha256'],video_id='fixture-video',channel_id='fixture-channel',privacy_status='private'))
        # Preserve the production ordering requirement when recording private media.
        native=self.root/'native.json';e.save(native,dict(verified=True,manifest_sha256=r['nostr_manifest_sha256'],video_event_id='a'*64,announcement_event_id='b'*64,blobs=[dict(server='https://example.org',sha256='c'*64)]))
        e.record_publication(item,'r1','nostr',native);e.record_publication(item,'r1','youtube-private',receipt)
        with self.assertRaises(ValueError):reviews.bind_public(item,'r1',dict(changed_destination=True))
        reviews.bind_public(item,'r1',config);reviews.bind_public(item,'r1',config)
        public=reviews.require(item,'youtube-public',r['manifest_sha256'],config)
        self.assertEqual(public['youtube_video_id'],'fixture-video');self.assertEqual(public['message_id'],incoming['message_id'])
        self.assertEqual(len([a for a in item['approvals'] if a['scope']=='youtube-public']),1)
        packet['include_youtube_public']=False
        with self.assertRaises(ValueError):reviews.require(item,'youtube-public',r['manifest_sha256'],config)

    def test_no_announcement_receipt_requires_reviewed_policy(self):
        data,item,r=self.episode();self.approved(data,item,'nostr',{})
        receipt=self.root/'native.json';value=dict(verified=True,manifest_sha256=r['nostr_manifest_sha256'],video_event_id='a'*64,announcement_skipped=True,blobs=[dict(server='https://example.org',sha256='c'*64)])
        e.save(receipt,value)
        with self.assertRaisesRegex(ValueError,'omission was not reviewed'):e.record_publication(item,'r1','nostr',receipt)
        meta=Path(r['files']['nostr_metadata']['path']);value_meta=e.read(meta);value_meta.update(announce=False,announcement='');e.save(meta,value_meta)
        updated=e.revision(item,'r2',{k:v['path'] for k,v in r['files'].items()})
        auth=self.root/'approval.json';e.save(auth,dict(human_request='Approve fixture without announcement'));e.approve(item,'r2','nostr',auth)
        value['manifest_sha256']=updated['nostr_manifest_sha256'];e.save(receipt,value)
        e.record_publication(item,'r2','nostr',receipt)
        value['announcement_event_id']='b'*64;e.save(receipt,value)
        with self.assertRaisesRegex(ValueError,'forbids an announcement'):e.record_publication(item,'r2','nostr',receipt)

    def test_nostr_metadata_preserves_text_and_requires_explicit_valid_tag_lists(self):
        original=dict(d='fixture-one',title='Fixture',description='Exact reviewed words.',announcement='Watch.',source_url='https://podcast.example.org/one')
        self.assertEqual(nostr_metadata(original),original)
        self.assertEqual(nostr_metadata(original)['description'],'Exact reviewed words.')
        for field in ('participants','announcement_mentions'):
            for invalid in ('b'*64,['npub1fixture'],['B'*64],['b'*63],['b'*64,'b'*64],[123],None):
                with self.subTest(field=field,value=invalid):
                    with self.assertRaisesRegex(ValueError,field):nostr_metadata(dict(original,**{field:invalid}))
            self.assertEqual(nostr_metadata(dict(original,**{field:['b'*64]}))[field],['b'*64])

    def test_nostr_review_displays_tag_intent_and_changed_tags_invalidate_approval(self):
        data,item,r=self.episode();path=Path(r['files']['nostr_metadata']['path'])
        meta=e.read(path);meta.update(participants=['b'*64],announcement_mentions=['c'*64],source_url='https://podcast.example.org/one',hashtags=['bitcoin'])
        e.save(path,meta);r=e.revision(item,'r2',{k:v['path'] for k,v in r['files'].items()})
        config=dict(expected_pubkey='a'*64,publication_servers=['https://example.org'],publication_relays=['wss://relay.example.org'],marmot_home='/fixture')
        route=dict(account='a'*64,group='b'*64)
        with patch.object(reviews.subprocess,'check_output',return_value=json.dumps(dict(response=dict(message_ids_hex=['f'*64]))).encode()):
            packet=reviews.request(self.root,data,item,'r2','nostr',route,config,send=True)
        message=e.read(Path(item['directory'])/'reviews'/(packet['id']+'.send.json'))['text']
        self.assertIn('Video participant p tags: '+'b'*64,message)
        self.assertIn('Announcement mention p tags: '+'c'*64,message)
        self.assertIn('Source reference: https://podcast.example.org/one',message)
        self.assertIn('Hashtags: bitcoin',message)
        incoming=dict(**route,sender='c'*64,message_id='d'*64,text='approve '+packet['id'],recorded_at=1,reply_to=None)
        reviews.accept(self.root,data,incoming)
        reviews.require(item,'nostr',r['nostr_manifest_sha256'],config)
        meta['announcement_mentions']=['d'*64];e.save(path,meta)
        with self.assertRaises(ValueError):reviews.accept(self.root,data,incoming)
        changed=e.revision(item,'r3',{k:v['path'] for k,v in r['files'].items()})
        with self.assertRaises(ValueError):reviews.require(item,'nostr',changed['nostr_manifest_sha256'],config)

    def test_quoted_yes_approves_only_its_exact_review(self):
        data,item,r=self.episode();route=dict(account='a'*64,group='b'*64)
        packet=reviews.request(self.root,data,item,'r1','nostr',route,{})
        packet.update(state='sent',message_ids=['f'*64])
        text=reviews.accept(self.root,data,dict(**route,sender='c'*64,message_id='d'*64,text='yes',recorded_at=1,reply_to='f'*64))
        self.assertIn('Approved nostr',text)

    def test_job_completion_and_failed_notification_never_repeat_production(self):
        folder=self.root/'job';folder.mkdir();request=dict(kind='render',parameters=dict(revision='/synthetic/revision'),notify=dict(home='/synthetic/home',account='a'*64,group='b'*64))
        e.save(folder/'job.json',dict(state='queued',id='fixture',request=request,request_sha256=e.digest(request)))
        with patch.object(jobs,'preflight',return_value=None),patch.object(jobs.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run,patch.object(jobs.subprocess,'check_output',side_effect=RuntimeError('transport unavailable')):
            jobs.worker(folder)
            self.assertEqual(e.read(folder/'job.json')['state'],'completed');self.assertEqual(e.read(folder/'notification.json')['state'],'unresolved')
            with self.assertRaises(ValueError):jobs.worker(folder)
            self.assertEqual(run.call_count,1)
        receipt=json.dumps(dict(response=dict(message_ids_hex=['f'*64]))).encode()
        with patch.object(jobs.subprocess,'check_output',return_value=receipt) as send:
            jobs.notify(folder);jobs.notify(folder);self.assertEqual(send.call_count,1)
        self.assertEqual(jobs.status(folder)['notification'],'confirmed')

    def test_automatic_transcript_jobs_are_silent_and_failures_still_notify(self):
        home=e.private_root(self.root/'marmot');e.save(home/'podcaster-instance.json',dict(transcription_wakeups=True))
        folder=e.private_root(self.root/'job');request=dict(kind='transcript-analyze',parameters={},notify=dict(home=str(home),account='a'*64,group='b'*64))
        state=dict(id='fixture',nonce='nonce',state='completed',request=request);e.save(folder/'job.json',state)
        with patch.object(jobs.subprocess,'check_output') as send:
            self.assertEqual(jobs.notify(folder)['state'],'suppressed');jobs.notify(folder);send.assert_not_called()
        self.assertFalse((folder/'notice.send.json').exists())
        failed=e.private_root(self.root/'failed');e.save(failed/'job.json',dict(state,state='failed'))
        with patch.object(jobs.failures,'store_root',return_value=self.root/'failures'),patch.object(jobs.failures,'source_revision',return_value='unknown'),patch.object(jobs.subprocess,'check_output',return_value=b'{}') as send:
            jobs.notify(failed);jobs.notify(failed);self.assertEqual(send.call_count,1)
        self.assertIn('Report UUID:',e.read(failed/'notice.send.json')['text'])

    def test_pending_transcript_notice_survives_policy_change(self):
        home=e.private_root(self.root/'marmot');e.save(home/'podcaster-instance.json',dict(transcription_wakeups=True))
        folder=e.private_root(self.root/'job');request=dict(kind='transcript-analyze',parameters={},notify=dict(home=str(home),account='a'*64,group='b'*64))
        e.save(folder/'job.json',dict(id='fixture',nonce='nonce',state='completed',request=request))
        intent=dict(account_id_hex='a'*64,group_id_hex='b'*64,text='Immutable old notice',idempotency_key='job-nonce')
        e.save(folder/'notice.send.json',intent);e.save(folder/'notification.json',dict(state='unresolved'))
        with patch.object(jobs.subprocess,'check_output',return_value=b'{}') as send:jobs.notify(folder);self.assertEqual(send.call_count,1)
        self.assertEqual(e.read(folder/'notice.send.json'),intent)

    def test_job_identity_and_environment_are_limited(self):
        request=dict(kind='render',parameters=dict(revision='/fixture'))
        with patch.object(jobs.subprocess,'Popen',return_value=types.SimpleNamespace(pid=999999)) as start:
            jobs.start(self.root/'jobs','one',request);jobs.start(self.root/'jobs','one',request);self.assertEqual(start.call_count,1)
            with self.assertRaises(ValueError):jobs.start(self.root/'jobs','one',dict(request,parameters=dict(revision='/different')))
        self.assertFalse({'OPENAI_API_KEY','CODEX_API_KEY','SSH_AUTH_SOCK'}&jobs.clean_env().keys())
        with self.assertRaises(ValueError):jobs.command(dict(kind='shell',parameters=dict(command='anything')))

    def test_youtube_jobs_use_configured_sdk_runtime_without_changing_upload_scope(self):
        config=self.root/'publication.json';e.save(config,dict(youtube_python=sys.executable))
        for kind in ('youtube-private','youtube-public'):
            params=dict(root=str(self.root/'work'),show='fixture',episode='99',revision='r2',config=str(config))
            command=jobs.command(dict(kind=kind,parameters=params,apply=True))
            self.assertEqual(command[0],sys.executable);self.assertEqual(command[2],kind);self.assertEqual(command[-1],'--apply')
            for key,value in params.items():self.assertEqual(command[command.index('--'+key)+1],value)
        e.save(config,dict(youtube_python='python3'))
        with self.assertRaises(ValueError):jobs.command(dict(kind='youtube-private',parameters=params,apply=True))
        e.save(config,{})
        with self.assertRaises(ValueError):jobs.command(dict(kind='youtube-private',parameters=params,apply=True))

class YoutubeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        video=self.root/'video.mp4';video.write_bytes(b'synthetic-video')
        self.metadata=dict(title='Test',description='Draft',category_id='28',language='en',tags=['test'],made_for_kids=False,contains_synthetic_media=False)
        self.packet=dict(files={'video':e.file_record(video)},metadata=self.metadata,channel_id='fixture-channel',manifest_sha256='a'*64)
        http=types.ModuleType('googleapiclient.http');http.MediaFileUpload=lambda *a,**kw:object()
        self.patch=patch.dict(sys.modules,{'googleapiclient':types.ModuleType('googleapiclient'),'googleapiclient.http':http});self.patch.start();self.addCleanup(self.patch.stop)
        self.service=Mock();self.service.videos().insert.return_value=types.SimpleNamespace(uri='https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable',body='{}',headers={'Content-Type':'application/json'})
    def response(self,status,**headers):return type('Response',(dict,),{'status':status})(headers)

    def test_thumbnail_readback_accepts_different_urls_only_for_identical_preferred_image(self):
        updated='https://i.ytimg.com/vi/fixture/maxresdefault.jpg?version=one'
        served='https://i.ytimg.com/vi/fixture/maxresdefault.jpg?version=two'
        response=dict(items=[dict(maxres=dict(url=updated,width=1280,height=720))])
        video=dict(snippet=dict(thumbnails=dict(maxres=dict(url=served,width=1280,height=720))))
        class Download:
            def __init__(self,body):self.body=body;self.headers=Mock();self.headers.get_content_type.return_value='image/jpeg'
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.body
        opener=Mock();images={updated:b'same reviewed thumbnail',served:b'same reviewed thumbnail'}
        opener.open.side_effect=lambda url,**kw:Download(images[url])
        with patch.object(youtube.urllib.request,'build_opener',return_value=opener):
            self.assertEqual(youtube.thumbnail_readback(response,video),__import__('hashlib').sha256(images[served]).hexdigest())
            images[served]=b'different image'
            self.assertIsNone(youtube.thumbnail_readback(response,video))
        response['items'][0]={'high':dict(url=updated,width=480,height=360)}
        self.assertIsNone(youtube.thumbnail_readback(response,video))

    def test_caption_polling_binds_video_and_waits_for_nonempty_download_without_reinsertion(self):
        captions=self.root/'reviewed.vtt';captions.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nReviewed words.\n')
        self.packet['files']['captions']=e.file_record(captions)
        name='sovereign-podcaster-'+self.packet['files']['captions']['sha256'][:20]
        calls=[]
        def listed(**params):
            self.assertEqual(params['videoId'],'same-video');calls.append(params)
            status='syncing' if len(calls)==1 else 'serving'
            track=dict(id='same-caption',snippet=dict(name=name,language='en',status=status))
            return types.SimpleNamespace(execute=lambda **kw:dict(items=[track]))
        service=Mock();service.captions().list.side_effect=listed
        downloads=[b'WEBVTT\n\n',captions.read_bytes()]
        service.captions().download.side_effect=lambda **kw:types.SimpleNamespace(execute=lambda **opts:downloads.pop(0))
        folder=self.root/'captions';folder.mkdir()
        with patch.object(youtube.time,'sleep'):
            track=youtube.caption_ready(service,'same-video',self.packet,folder,lambda:None)
        self.assertEqual(track['id'],'same-caption');self.assertEqual(e.read(folder/'caption.json')['phase'],'verified')
        service.captions().insert.assert_not_called();service.captions().update.assert_not_called()
        self.assertEqual(service.captions().download.call_count,2)
        service.captions().download.side_effect=lambda **kw:types.SimpleNamespace(execute=lambda **opts:b'WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nWrong words.\n')
        with self.assertRaisesRegex(ValueError,'reviewed words/timing'):youtube.caption_ready(service,'same-video',self.packet,folder,lambda:None)

    def test_resumable_lost_final_response_recovers_same_video_without_second_insert(self):
        self.service._http.request.side_effect=[(self.response(200,location='https://www.googleapis.com/upload/youtube/v3/videos?upload_id=private'),b''),RuntimeError('lost PUT')]
        with self.assertRaisesRegex(RuntimeError,'uncertain'):youtube.resumable(self.service,self.packet,self.root,{},lambda:None)
        self.service._http.request.side_effect=[(self.response(200),b'{"id":"same-video"}')]
        self.assertEqual(youtube.resumable(self.service,self.packet,self.root,{},lambda:None),'same-video')
        self.assertEqual(self.service.videos().insert.call_count,1)
        saved=e.read(self.root/'upload.private.json');self.assertEqual(saved['video_id'],'same-video')
        self.assertEqual((self.root/'upload.private.json').stat().st_mode&0o777,0o600)

    def test_lost_initiation_never_creates_duplicate_upload(self):
        self.service._http.request.side_effect=RuntimeError('lost POST')
        with self.assertRaisesRegex(RuntimeError,'initiation response'):youtube.resumable(self.service,self.packet,self.root,{},lambda:None)
        with self.assertRaisesRegex(RuntimeError,'initiation outcome'):youtube.resumable(self.service,self.packet,self.root,{},lambda:None)
        self.assertEqual(self.service.videos().insert.call_count,1)

    def test_packet_change_and_foreign_upload_uri_are_rejected(self):
        with self.assertRaises(ValueError):youtube.valid_uri('https://evil.invalid/upload')
        with self.assertRaises(ValueError):youtube.progress(self.response(308,range='bytes=0-999'),100)
        e.save(self.root/'upload.private.json',dict(binding={'different':True}))
        with self.assertRaises(ValueError):youtube.resumable(self.service,self.packet,self.root,{},lambda:None)
        self.service._http.request.assert_not_called()
        with self.assertRaises(ValueError):youtube.metadata(dict(self.metadata,title='<unsafe>'))

class YoutubePacketTests(unittest.TestCase):
    setUp=YoutubeTests.setUp
    response=YoutubeTests.response
    def test_private_revision_publication_reuses_id_and_rejects_changed_thumbnail(self):
        captions=self.root/'captions.vtt';captions.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nOriginal words.\n')
        thumbnail=self.root/'thumbnail.jpg';thumbnail.write_bytes(b'fixture image')
        self.packet['files'].update(captions=e.file_record(captions),thumbnail=e.file_record(thumbnail))
        live=dict(id='same-video',snippet=dict(youtube.metadata(self.metadata)['snippet'],channelId='fixture-channel',thumbnails={'high':{'url':'https://i.ytimg.com/fixture.jpg'}}),status=youtube.metadata(self.metadata)['status'],processingDetails={'processingStatus':'succeeded'})
        tracks=[];caption_bytes={};thumbnail_hash=['initial']
        def response(value):return types.SimpleNamespace(execute=lambda **kw:copy.deepcopy(value() if callable(value) else value))
        service=Mock()
        def video_update(**kw):
            def apply():
                body=kw['body']
                if 'snippet' in body:live['snippet'].update(body['snippet'])
                if 'status' in body:live['status'].update(body['status'])
                return live
            return response(apply)
        service.videos().update.side_effect=video_update
        service.captions().list.side_effect=lambda **kw:response(lambda:dict(items=[x for x in tracks if not kw.get('id') or x['id']==kw['id']]))
        class Media:
            def __init__(self,path,**kw):self.path=Path(path)
        def insert(**kw):
            def apply():
                track=dict(id='caption-one',snippet=dict(kw['body']['snippet'],status='serving'));tracks.append(track);caption_bytes[track['id']]=kw['media_body'].path.read_bytes();return track
            return response(apply)
        service.captions().insert.side_effect=insert
        def update_caption(**kw):
            def apply():caption_bytes[kw['body']['id']]=kw['media_body'].path.read_bytes();return {'id':kw['body']['id']}
            return response(apply)
        service.captions().update.side_effect=update_caption
        service.captions().download.side_effect=lambda **kw:response(lambda:caption_bytes[kw['id']])
        def set_thumbnail(**kw):
            def apply():thumbnail_hash[0]=e.file_record(kw['media_body'].path)['sha256'];return dict(items=[{'high':{'url':'https://i.ytimg.com/fixture.jpg'}}])
            return response(apply)
        service.thumbnails().set.side_effect=set_thumbnail
        access=Mock();access.owned_video.side_effect=lambda *a,**kw:copy.deepcopy(live)
        folder=self.root/'release/r1/youtube-private';folder.mkdir(parents=True)
        with patch('googleapiclient.http.MediaFileUpload',Media),patch.object(youtube,'sdk',return_value=access),patch.object(youtube,'thumbnail_bytes',side_effect=lambda video:thumbnail_hash[0]),patch.object(youtube,'resumable',return_value='same-video') as upload:
            first=youtube.private(service,self.packet,folder,lambda:None)
            self.assertEqual(first['privacy_status'],'private');self.assertEqual(first['video_id'],'same-video')
            self.metadata['description']='Revised reviewed description';captions.write_text('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nCorrected words.\n');thumbnail.write_bytes(b'reviewed revised image')
            packet=copy.deepcopy(self.packet);packet.update(metadata=self.metadata,reuse_video_id='same-video',reuse_caption_id='caption-one')
            packet['files'].update(captions=e.file_record(captions),thumbnail=e.file_record(thumbnail))
            revised=self.root/'release/r2/youtube-private';revised.mkdir(parents=True)
            private=youtube.private(service,packet,revised,lambda:None)
            self.assertEqual(upload.call_count,1);self.assertEqual(service.captions().insert.call_count,1);self.assertEqual(service.captions().update.call_count,1)
            public=revised.parent/'youtube-public';public.mkdir()
            thumbnail_hash[0]='unreviewed change'
            before=service.videos().update.call_count
            with self.assertRaisesRegex(ValueError,'thumbnail bytes'):youtube.public(service,packet,private,public,lambda:None)
            self.assertEqual(service.videos().update.call_count,before)
            thumbnail_hash[0]=private['thumbnail_readback_sha256']
            receipt=youtube.public(service,packet,private,public,lambda:None)
            self.assertEqual(receipt['privacy_status'],'public');self.assertEqual(receipt['video_id'],'same-video')
            self.assertEqual(live['status']['privacyStatus'],'public')

class IncomingTests(unittest.TestCase):
    def test_timeline_sender_id_text_and_availability_are_verified(self):
        root=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('messages',root/'adapters/marmot/messages.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        env=dict(MARMOT_ACCOUNT_ID_HEX='a'*64,MARMOT_GROUP_ID_HEX='b'*64,MARMOT_MESSAGE_ID_HEX='c'*64,MARMOT_SENDER_ACCOUNT_ID_HEX='d'*64)
        config=dict(account_id_hex='a'*64,trusted_hex='d'*64,marmot_home='/fixture')
        response=dict(type='timeline_message',account_id_hex='a'*64,group_id_hex='b'*64,message_id_hex='c'*64,message=dict(message_id_hex='c'*64,sender=dict(account_id_hex='d'*64),direction='received',availability='available',text='yes',recorded_at=1))
        result=m.authenticated(config,env,'yes',lambda *a:response);self.assertEqual(result['message_id'],'c'*64)
        for key,value in [('availability','deleted'),('text','something else'),('message_id_hex','e'*64)]:
            bad=copy.deepcopy(response);bad['message'][key]=value
            with self.assertRaises(RuntimeError):m.authenticated(config,env,'yes',lambda *a:bad)
        with self.assertRaises(RuntimeError):m.authenticated(config,dict(env,MARMOT_SENDER_ACCOUNT_ID_HEX='e'*64),'yes',lambda *a:response)
if __name__=='__main__':unittest.main()
