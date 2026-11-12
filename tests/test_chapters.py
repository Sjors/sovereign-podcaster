import copy
import hashlib
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import wave
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import chapters as c
import episodes as e
REAL_RUN=subprocess.run


class ChapterTests(unittest.TestCase):
    def test_episode_lock_waits_for_a_finishing_worker(self):
        child=subprocess.Popen([sys.executable,'-c',
            'import fcntl,sys,time; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX); '
            'print("ready",flush=True); time.sleep(.2)',str(self.folder/'.chapters.lock')],stdout=subprocess.PIPE,text=True)
        self.addCleanup(child.wait)
        self.assertEqual(child.stdout.readline().strip(),'ready')
        started=time.monotonic()
        with c.locked(self.folder,timeout=2):self.assertGreaterEqual(time.monotonic()-started,.1)
        child.stdout.close()

    def test_episode_lock_timeout_preserves_held_lock_and_saved_state(self):
        marker=self.folder/'saved.json';e.save(marker,dict(phase='running'))
        with (self.folder/'.chapters.lock').open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            with self.assertRaisesRegex(TimeoutError,'still holds'):
                with c.locked(self.folder,timeout=.05):self.fail('Entered a held episode')
            self.assertEqual(e.read(marker),dict(phase='running'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp'); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.folder=e.private_root(self.root/'episode'/'chapters')
        self.audio=b'synthetic final recording'; self.transcript=b'WEBVTT\n\n00:00:00.000 --> 00:00:10.000\nSynthetic fixture.\n'
        self.episode=dict(number='1',guid='fixture-guid',slug='episode-1',url='https://example.org/episode-1',
            pubDate='Tue, 03 Nov 2026 00:00:00 +0000',final_audio_sha256=hashlib.sha256(self.audio).hexdigest())
        self.entry=dict(episode=self.episode,clearance=dict(audit_complete=True,final_audio_sha256=self.episode['final_audio_sha256']))
        self.config=dict(paused=False,show='demo',feed='https://example.org/feed.xml',source_catalog=str(self.root/'catalog.json'),
            review_config=str(self.root/'recognizer.json'),castopod_config=str(self.root/'hosting.json'))
        e.save(self.root/'catalog.json',dict(show='demo',episodes={'1':self.entry}))
        e.save(self.root/'recognizer.json',dict(python=sys.executable))
        incoming=dict(text='chapters demo 1'); e.save(self.root/'request.json',dict(incoming=incoming))
        task=dict(show='demo',episode='1',directory=str(self.folder),feed=self.config['feed'],source=self.entry,
            authorization=dict(request_path=str(self.root/'request.json'),incoming_sha256=e.digest(incoming)))
        e.save(self.folder.parent/'chapters-task.json',task)
        self.original='Useful summary.\n\nSources: https://example.org/source\n\nSponsor and credits stay here.\n'
        self.live=dict(id=1,slug='episode-1',title='Synthetic episode',guid='fixture-guid',status='published',
            number=1,link=self.episode['url'],published_at='2026-11-03 00:00:00',duration=900,
            audio_url='https://example.org/audio.mp3',audio_file_key='podcasts/demo/one.mp3',audio_file_size=len(self.audio),
            transcript_id=2,transcript_url='https://example.org/transcript.vtt',transcript_json_url='https://example.org/transcript.json',
            chapters_id=None,chapters_url=None,description_markdown=self.original,
            description_sha256=hashlib.sha256(self.original.encode()).hexdigest())
        self.cp_config=dict(transport='local',app='/fixture',user='test',cli='/fixture/helpers')
        self.cp=Mock(); self.cp.load_config.return_value=self.cp_config
        self.cp.inspect.side_effect=lambda *_:dict(features=['chapters','conditional-update'],episode=copy.deepcopy(self.live))
        self.cp.run_episode.side_effect=self.mutate
        for name,mock in [('transport',patch.object(c,'transport',return_value=self.cp)),
                          ('get',patch.object(c,'get',side_effect=self.get)),
                          ('run',patch.object(c.subprocess,'run',side_effect=self.fake_run))]:
            mock.start(); self.addCleanup(mock.stop)
        self.rows=[dict(startTime=0,title='Opening'),dict(startTime=300,title='Second Topic'),dict(startTime=600,title='Final Topic')]

    def feed(self):
        root=ET.Element('rss'); channel=ET.SubElement(root,'channel'); item=ET.SubElement(channel,'item')
        for key,value in [('title',self.live['title']),('guid',self.live['guid']),('link',self.live['link']),
                          ('pubDate',self.episode['pubDate']),('description',self.live['description_markdown'])]:
            ET.SubElement(item,key).text=value
        ET.SubElement(item,'enclosure',url=self.live['audio_url'],length=str(self.live['audio_file_size']))
        if self.live['number'] is not None:
            ET.SubElement(item,'{http://www.itunes.com/dtds/podcast-1.0.dtd}episode').text=str(self.live['number'])
        if self.live['transcript_url']:ET.SubElement(item,'{'+c.NS+'}transcript',url=self.live['transcript_url'],type='text/vtt')
        if self.live['chapters_url']:ET.SubElement(item,'{'+c.NS+'}chapters',url=self.live['chapters_url'],type='application/json+chapters')
        return ET.tostring(root)

    def get(self,url,accept=None):
        if url==self.config['feed']:return self.feed(),{}
        if url==self.live['audio_url']:return self.audio,{}
        if url==self.live['transcript_url']:return self.transcript,{}
        if url==self.live['chapters_url']:return (self.folder/'chapters.json').read_bytes(),{'Content-Type':'application/json'}
        if url==self.live['link']:
            self.assertEqual(accept,'text/html')
            return b'episode page',{}
        raise AssertionError('Unexpected URL '+str(url))

    def fake_run(self,args,**kwargs):
        if args[0]=='ffmpeg':
            with wave.open(args[-1],'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(1); wav.writeframes(b'\0\0'*900)
        else:
            windows=e.read(args[args.index('--windows')+1]);out=Path(args[args.index('--out')+1])
            e.save(out,dict(episode_guid=self.episode['guid'],source_audio_sha256=self.episode['final_audio_sha256'],
                windows=[dict(window=w,segments=[dict(start=w['start'],end=w['end'],text='Synthetic boundary evidence')]) for w in windows]))
        return subprocess.CompletedProcess(args,0)

    def mutate(self,*args,**kwargs):
        self.assertEqual(args[1:4],('demo','update','episode-1'))
        self.assertTrue(kwargs['apply']);self.assertNotIn('audio',kwargs);self.assertNotIn('transcript',kwargs)
        self.assertEqual(e.read(kwargs['expected_state']),self.live)
        notes=Path(kwargs['notes']).read_bytes().decode('utf-8')
        self.live.update(chapters_id=3,chapters_url='https://example.org/chapters.json',
            description_markdown=notes,description_sha256=hashlib.sha256(notes.encode()).hexdigest())
        e.save(kwargs['receipt'],dict(phase='verified'))
        return dict(episode=self.live)

    def ready(self):
        c.prepare(self.config,self.folder)
        e.save(self.folder/'chapters.json',dict(version='1.2.0',chapters=self.rows))
        evidence=c.check(self.config,self.folder); c.render(self.config,self.folder)
        e.save(self.folder/'review.json',dict(publication_ready=True,reviewed_full_transcript=True,
            chapters_sha256=c.sha(self.folder/'chapters.json'),source_audio_sha256=self.episode['final_audio_sha256'],
            transcript_sha256=c.sha(self.folder/'transcript.vtt'),evidence_sha256=evidence['evidence_sha256'],
            boundaries=[dict(startTime=row['startTime'],reason='Reviewed synthetic topic transition') for row in self.rows]))

    def test_complete_task_publishes_without_human_approval_and_verifies_before_notice(self):
        self.ready();self.assertIsNone(c.completion(self.folder))
        plan=c.publish(self.config,self.folder);self.assertFalse(plan['apply']);self.cp.run_episode.assert_not_called()
        result=c.publish(self.config,self.folder,True)
        self.assertTrue(result['verified']);self.assertEqual(result['count'],3)
        self.assertEqual(c.completion(self.folder),'Added 3 chapters to episode 1: https://example.org/episode-1')
        self.assertTrue(self.live['description_markdown'].startswith(self.original))
        self.assertEqual((self.folder/'notes-original.md').read_text(),self.original)
        self.cp.run_episode.reset_mock();c.verify(self.config,self.folder)
        c.publish(self.config,self.folder,True);self.cp.run_episode.assert_not_called()

    def test_existing_markdown_line_endings_are_preserved_in_derived_description(self):
        self.original=self.original.replace('\n','\r\n')
        self.live.update(description_markdown=self.original,description_sha256=hashlib.sha256(self.original.encode()).hexdigest())
        self.ready();c.publish(self.config,self.folder,True)
        self.assertTrue(self.live['description_markdown'].startswith(self.original))
        self.assertEqual((self.folder/'notes-original.md').read_bytes(),self.original.encode())

    def test_new_source_missing_transcript_or_native_helpers_stop_before_preparation(self):
        self.live['transcript_url']=None
        with self.assertRaisesRegex(ValueError,'native transcript'):c.prepare(self.config,self.folder)
        self.assertFalse((self.folder/'episode-before.json').exists());self.cp.run_episode.assert_not_called()
        self.config['paused']=True
        with self.assertRaisesRegex(ValueError,'paused'):c.prepare(self.config,self.folder)

    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg unavailable')
    def test_prepare_decodes_real_synthetic_audio_and_establishes_the_source_clock(self):
        original=self.root/'synthetic.wav';encoded=self.root/'synthetic.mp3'
        with wave.open(str(original),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\0\0'*80000)
        REAL_RUN(['ffmpeg','-v','error','-nostdin','-n','-i',str(original),str(encoded)],check=True,capture_output=True)
        self.audio=encoded.read_bytes();self.episode['final_audio_sha256']=hashlib.sha256(self.audio).hexdigest()
        self.entry['clearance']['final_audio_sha256']=self.episode['final_audio_sha256']
        self.live.update(duration=10,audio_file_size=len(self.audio))
        e.save(self.root/'catalog.json',dict(show='demo',episodes={'1':self.entry}))
        task=e.read(self.folder.parent/'chapters-task.json');task['source']=self.entry;e.save(self.folder.parent/'chapters-task.json',task)
        with patch.object(c.subprocess,'run',side_effect=REAL_RUN):prepared=c.prepare(self.config,self.folder)
        self.assertAlmostEqual(prepared['duration'],10,places=2)
        with wave.open(str(self.folder/'audio-16k.wav')) as wav:
            self.assertEqual(wav.getframerate(),16000);self.assertEqual(wav.getnchannels(),1)

    def test_concurrent_notes_edits_and_destination_changes_are_preserved(self):
        self.ready();self.live['description_markdown']='Owner revised the notes'
        with self.assertRaisesRegex(ValueError,'changed since preparation'):c.publish(self.config,self.folder,True)
        self.cp.run_episode.assert_not_called()
        self.cp_config['app']='/different-instance'
        with self.assertRaisesRegex(ValueError,'destination changed'):c.publish(self.config,self.folder,True)

    def test_changed_sources_canonical_json_and_review_cannot_publish(self):
        self.ready();self.audio=b'different served audio'
        with self.assertRaisesRegex(ValueError,'audio/transcript changed'):c.publish(self.config,self.folder,True)
        self.cp.run_episode.assert_not_called()
        self.rows[1]['title']='A changed topic';e.save(self.folder/'chapters.json',dict(version='1.2.0',chapters=self.rows))
        with self.assertRaisesRegex(ValueError,'exports changed'):c.publish(self.config,self.folder,True)

    def test_unknown_mutation_is_not_repeated_and_read_only_verification_recovers_effects(self):
        self.ready()
        def lost(*args,**kwargs):
            self.mutate(*args,**kwargs);e.save(kwargs['receipt'],dict(phase='applying'))
            raise RuntimeError('Synthetic lost response')
        self.cp.run_episode.side_effect=lost
        with self.assertRaisesRegex(RuntimeError,'lost response'):c.publish(self.config,self.folder,True)
        self.assertIsNone(c.completion(self.folder))
        with self.assertRaisesRegex(ValueError,'unresolved'):c.publish(self.config,self.folder,True)
        self.assertEqual(self.cp.run_episode.call_count,1)
        self.assertTrue(c.verify(self.config,self.folder)['verified'])
        self.assertEqual(e.read(self.folder/'transport.json')['phase'],'applying')

    def test_incomplete_checks_never_restart_and_verify_does_not_start_recognition(self):
        c.prepare(self.config,self.folder);e.save(self.folder/'chapters.json',dict(version='1.2.0',chapters=self.rows))
        c.render(self.config,self.folder);e.save(self.folder/'review.json',{})
        with patch.object(c.subprocess,'run',side_effect=AssertionError('No new workers')):
            with self.assertRaisesRegex(ValueError,'Run and review'):c.verify(self.config,self.folder)
        with patch.object(c.subprocess,'run',side_effect=RuntimeError('Synthetic worker failed')):
            with self.assertRaises(RuntimeError):c.check(self.config,self.folder)
        with patch.object(c.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'unresolved'):c.check(self.config,self.folder)
            run.assert_not_called()

    def test_completion_rejects_tampered_receipts_and_artifacts(self):
        self.ready();c.publish(self.config,self.folder,True)
        (self.folder/'notes.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'completion receipt'):c.completion(self.folder)

    def test_public_description_missing_chapter_or_unrelated_feed_changes_fail(self):
        self.ready();c.publish(self.config,self.folder,True)
        original=self.feed
        def incomplete():
            root=ET.fromstring(original());root.find('./channel/item/description').text='Missing timestamps'
            return ET.tostring(root)
        with patch.object(self,'feed',side_effect=incomplete):
            with self.assertRaisesRegex(ValueError,'description omits'):c.verify(self.config,self.folder)
        self.live['title']='Unrelated title edit'
        with self.assertRaisesRegex(ValueError,'Unrelated episode field'):c.verify(self.config,self.folder)

    def test_visible_escaped_internal_markers_block_completion(self):
        self.ready()
        original=self.get
        def visible_marker(url,accept=None):
            if url==self.live['link']:
                self.assertEqual(accept,'text/html')
                return b'<p>&lt;!-- podcast-chapters:start --&gt;</p>',{}
            return original(url,accept)
        with patch.object(c,'get',side_effect=visible_marker):
            with self.assertRaisesRegex(ValueError,'Internal chapter markers'):c.publish(self.config,self.folder,True)
        self.assertEqual(e.read(self.folder/'transport.json')['phase'],'verified')
        self.assertIsNone(c.completion(self.folder))

    def test_html_delivery_requests_an_explicit_accept_header(self):
        import transcribe
        with patch.object(transcribe.urllib.request,'urlopen') as opened:
            opened.return_value.__enter__.return_value.read.return_value=b'html'
            opened.return_value.__enter__.return_value.headers={'Content-Type':'text/html'}
            transcribe.get('https://example.org/episode',accept='text/html')
            self.assertEqual(opened.call_args.args[0].get_header('Accept'),'text/html')

    def test_description_replaces_only_managed_or_selected_legacy_block(self):
        first=c.description(self.original,self.rows)
        revised=c.description(first,self.rows)
        self.assertEqual(first,revised);self.assertNotIn(c.START,first);self.assertEqual(first.count('## Chapters'),1)
        old=self.original+'\n'+c.START+'\n\n## Chapters\n\n00:00:00 Old\n\n'+c.END+'\n'
        migrated=c.description(old,self.rows)
        self.assertNotIn(c.START,migrated);self.assertNotIn(c.END,migrated);self.assertIn(self.original,migrated)
        legacy='Timestamps:\n\n00:00 - intro\n1:02 - 2:10: topic\n2:25 - final\n'
        old=self.original+'\n'+legacy+'\nSupport the Show!\n'
        with self.assertRaisesRegex(ValueError,'old timestamp'):c.description(old,self.rows)
        new=c.description(old,self.rows,legacy)
        self.assertIn(self.original,new);self.assertIn('Support the Show!',new);self.assertNotIn('2:10:',new)
        for wrong in (self.original,legacy+'\nSupport the Show!',legacy.replace('intro','https://example.org')):
            with self.subTest(wrong=wrong),self.assertRaises(ValueError):c.description(old,self.rows,wrong)

    def test_chapters_precede_sponsor_and_contact_footer_without_changing_its_text(self):
        for newline in ('\n', '\r\n'):
            summary = 'Episode summary.\n\nSources: https://example.org/source\n\n'.replace('\n', newline)
            footer = '===\n\nThis episode’s sponsor: CoinKite.\n\nAaron’s Nostr: npub1example\n\nSjors’ Nostr: npub1other'.replace('\n', newline)
            original = summary + footer
            for old in (original, original + '\n\n## Chapters\n\n00:00:00 Old\n'):
                with self.subTest(newline=newline, existing=old != original):
                    notes = c.description(old, self.rows)
                    self.assertTrue(notes.startswith(summary + '## Chapters\n\n'))
                    self.assertIn(footer, notes)
                    self.assertLess(notes.index('00:10:00 Final Topic'), notes.index('==='))
                    self.assertEqual(notes, c.description(notes, self.rows))
                    self.assertNotIn('00:00:00 Old', notes)

    def test_episode_sponsor_footer_follows_chapters(self):
        original = 'Summary.\n\nEpisode Sponsor: https://example.org/\n\nSjors New Book: book'
        notes = c.description(original, self.rows)
        self.assertTrue(notes.startswith('Summary.\n\n## Chapters'))
        self.assertTrue(notes.rstrip('\n').endswith('Episode Sponsor: https://example.org/\n\nSjors New Book: book'))
        self.assertEqual(notes, c.description(notes, self.rows))

    def test_inline_episode_sponsor_footer_follows_chapters(self):
        original = 'Summary. Episode Sponsor: https://example.org/ Sjors New Book: book'
        notes = c.description(original, self.rows)
        self.assertTrue(notes.startswith('Summary. \n\n## Chapters'))
        self.assertTrue(notes.rstrip('\n').endswith('Episode Sponsor: https://example.org/ Sjors New Book: book'))
        self.assertEqual(notes, c.description(notes, self.rows))

    def test_contact_only_footer_follows_chapters_and_prose_is_not_moved(self):
        original = 'Summary mentions our sponsor in passing.\n\nAaron’s Nostr: npub1example'
        notes = c.description(original, self.rows)
        self.assertTrue(notes.startswith('Summary mentions our sponsor in passing.\n\n## Chapters'))
        self.assertTrue(notes.endswith('Aaron’s Nostr: npub1example'))
        self.assertEqual(notes, c.description(notes, self.rows))

    def test_exact_unlabelled_footer_and_inline_separator_are_preserved(self):
        footer='---------------------------------------------\r\n\r\nMagazine offer!\r\n\r\nhttps://example.org/offer\r\n\r\nAnother newsletter offer.\r\n'
        original='Summary paragraph. Final summary sentence. '+footer
        anchor='---------------------------------------------\r\n\r\nMagazine offer!'
        notes=c.description(original,self.rows,footer=anchor)
        self.assertTrue(notes.startswith('Summary paragraph. Final summary sentence. \n\n## Chapters'))
        self.assertIn(footer.rstrip('\r\n'),notes)
        self.assertEqual(notes,c.description(notes,self.rows,footer=anchor))
        self.assertEqual(notes.count('https://example.org/offer'),1)
        for bad in ('missing footer','short','00:00:00 Opening'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):c.description(original,self.rows,footer=bad)

    def test_footer_selection_is_bound_to_render_before_publication(self):
        e.save(self.folder/'footer.json',dict(start='Sponsor and credits stay here.'))
        self.ready()
        self.assertIn('footer_sha256',e.read(self.folder/'render.json'))
        e.save(self.folder/'footer.json',dict(start='Sources: https://example.org/source'))
        with self.assertRaisesRegex(ValueError,'exports changed'):c.publish(self.config,self.folder,True)
        self.cp.run_episode.assert_not_called()

    def test_duration_mismatch_still_requires_source_bound_inspection(self):
        self.live['duration']=896.31
        with self.assertRaisesRegex(ValueError,'clocks differ'):c.prepare(self.config,self.folder)
        self.assertFalse((self.folder/'prepared.json').exists())
        review=dict(verdict='use-decoded-clock',episode_guid=self.episode['guid'],
            source_audio_sha256=self.episode['final_audio_sha256'],metadata_duration=896.31,
            decoded_frames=900,sample_rate=1,reason='Inspected container estimate; native and resampled clocks agree.')
        e.save(self.folder/'clock-review.json',review)
        self.assertEqual(c.reviewed_clock(self.folder,self.episode,896.31,900,1),self.folder/'clock-review.json')
        for changed in (dict(metadata_duration=895),dict(decoded_frames=901),dict(source_audio_sha256='other'),dict(reason='')):
            e.save(self.folder/'clock-review.json',review|changed)
            with self.assertRaisesRegex(ValueError,'exact source'):c.reviewed_clock(self.folder,self.episode,896.31,900,1)

    def test_inspected_clock_verdict_is_preserved_and_bound_to_prepared_inputs(self):
        self.live['duration']=896.31
        review=dict(verdict='use-decoded-clock',episode_guid=self.episode['guid'],
            source_audio_sha256=self.episode['final_audio_sha256'],metadata_duration=896.31,
            decoded_frames=900,sample_rate=1,reason='Inspected duration estimate.')
        e.save(self.folder/'clock-review.json',review);self.ready()
        self.assertIn('clock-review.json',e.read(self.folder/'prepared.json')['inputs'])
        e.save(self.folder/'clock-review.json',review|dict(reason='Changed verdict'))
        with self.assertRaisesRegex(ValueError,'source artifacts changed'):c.publish(self.config,self.folder,True)
        self.cp.run_episode.assert_not_called()

    def test_rendered_smart_quotes_are_allowed_without_relaxing_canonical_json_bytes(self):
        self.rows[1]['title']='Jade\'s "blind PIN" server';self.ready()
        original_feed=self.feed
        self.feed=lambda:original_feed().replace(b"Jade's",'Jade’s'.encode()).replace(b'"blind PIN"','“blind PIN”'.encode())
        self.assertTrue(c.publish(self.config,self.folder,True)['verified'])
        original_get=self.get
        def changed_json(url,accept=None):
            data,headers=original_get(url,accept)
            if url==self.live['chapters_url']:data=data.replace(b"Jade's",'Jade’s'.encode())
            return data,headers
        with patch.object(c,'get',side_effect=changed_json):
            with self.assertRaisesRegex(ValueError,'canonical chapter JSON'):c.verify(self.config,self.folder)

    def test_invalid_chapters_rejected(self):
        for rows in ([self.rows[0]],list(reversed(self.rows)),[dict(startTime=True,title='bad')]+self.rows[1:],
                     [dict(startTime=float('nan'),title='bad')]+self.rows[1:],
                     [dict(startTime=0,title='<b>bad</b>')]+self.rows[1:],self.rows+[dict(startTime=900,title='Past ending')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):c.validate(dict(version='1.2.0',chapters=rows),900)

    def test_published_intake_binds_only_selected_audio_without_transcription_enrollment(self):
        e.save(self.root/'catalog.json',dict(show='demo',episodes={}))
        with self.assertRaisesRegex(ValueError,'no source clearance'):c.requested_source(self.config,'demo','1')
        self.config.update(allow_published_source_intake=True,config_path=str(self.root/'chapter-config.json'))
        e.save(Path(self.config['config_path']),self.config)
        entry=c.acquire_source(self.config,'demo','1')
        self.assertEqual(entry['episode']['guid'],self.episode['guid'])
        self.assertEqual(entry['clearance']['final_audio_sha256'],hashlib.sha256(self.audio).hexdigest())
        self.assertEqual(entry['clearance']['status'],'published_audio_identity_verified')
        self.assertEqual(set(e.read(self.root/'catalog.json')['episodes']),{'1'})

    def test_operator_selection_supports_unnumbered_native_episode_without_editing_metadata(self):
        self.live['number']=None
        e.save(self.root/'catalog.json',dict(show='demo',episodes={}))
        self.config.update(allow_published_source_intake=True,config_path=str(self.root/'chapter-config.json'))
        e.save(Path(self.config['config_path']),self.config)
        selected=dict(self.episode,native_number=None,enclosure=dict(url=self.live['audio_url'],length=str(len(self.audio))))
        wrong=dict(selected,guid='another-guid')
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
            c.acquire_source(self.config,'demo','1',selected=wrong)
        wrong=dict(selected,enclosure=dict(selected['enclosure'],url='https://example.org/other.mp3'))
        with self.assertRaisesRegex(ValueError,'identity changed'):
            c.acquire_source(self.config,'demo','1',selected=wrong)
        entry=c.acquire_source(self.config,'demo','1',selected=selected)
        self.assertIsNone(entry['episode']['native_number'])
        self.assertEqual(entry['episode']['display_name'],self.live['title'])
        task=e.read(self.folder.parent/'chapters-task.json');task['source']=entry;e.save(self.folder.parent/'chapters-task.json',task)
        self.ready();c.publish(self.config,self.folder,True)
        self.assertIsNone(self.live['number'])
        self.assertIn('to Synthetic episode:',c.completion(self.folder))
        with self.assertRaisesRegex(ValueError,'differs from the selected queue'):
            c.acquire_source(self.config,'demo','1',selected=wrong | dict(guid='wrong'))

    def test_published_intake_and_saved_sources_cannot_clear_existing_holds(self):
        controls=self.root/'controls.json';self.config['source_controls']=str(controls)
        held=copy.deepcopy(self.entry);held['clearance']['audit_complete']=False
        e.save(controls,dict(show='demo',episodes={'1':held}))
        with self.assertRaisesRegex(ValueError,'source hold'):c.source(self.config,'demo','1')
        e.save(self.root/'catalog.json',dict(show='demo',episodes={}))
        self.config['allow_published_source_intake']=True
        with self.assertRaisesRegex(ValueError,'source hold'):c.acquire_source(self.config,'demo','1')
        self.assertEqual(e.read(self.root/'catalog.json')['episodes'],{})

    def test_published_intake_cannot_import_a_missing_episode_or_changed_cleared_audio(self):
        controls=self.root/'controls.json';e.save(controls,dict(show='demo',episodes={'1':self.entry}))
        e.save(self.root/'catalog.json',dict(show='demo',episodes={}))
        self.config.update(allow_published_source_intake=True,source_controls=str(controls))
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):c.acquire_source(self.config,'demo','2')
        self.audio=b'Changed published recording'
        with self.assertRaisesRegex(ValueError,'existing source clearance'):c.acquire_source(self.config,'demo','1')
        self.assertEqual(e.read(self.root/'catalog.json')['episodes'],{})


if __name__=='__main__':unittest.main()
