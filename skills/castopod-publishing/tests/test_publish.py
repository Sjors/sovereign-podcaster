import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).resolve().parents[1] / 'scripts/publish.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublishingFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.audio = Path(self.temp.name) / 'audio with spaces.mp3'
        self.audio.write_bytes(b'audio')
        self.notes = Path(self.temp.name) / 'notes with spaces.md'
        self.notes.write_text('Explicit source and credits.\n')
        self.config = dict(ssh='podcast@host', app='/srv/castopod', user='ai.assistant',
                           incoming='/srv/incoming files', cli='/srv/bin/helpers', state_dir=str(Path(self.temp.name)/'state'))
        self.sequence=0
        paused=patch.object(publisher,'ensure_database_writes_allowed');paused.start();self.addCleanup(paused.stop)

    def new_receipt(self):
        self.sequence+=1;return Path(self.temp.name)/('operation-'+str(self.sequence)+'.json')

    def state(self, episode=None):
        return dict(helper_api=1,user_exists=True, podcast=dict(handle='articles', status='published'), episode=episode)

    def episode(self, **changes):
        value = dict(id=7, slug='test-episode', title='Title', status='draft',
                     description_sha256=publisher.hashlib.sha256(self.notes.read_bytes()).hexdigest(),
                     audio_file_size=5, audio_file_key='podcasts/articles/test.mp3',
                     audio_url='https://host/audio.mp3')
        value.update(changes)
        return value

    def create(self, **kw):
        return publisher.run_episode(self.config, 'articles', 'create', 'test-episode',
                                     title="Title's $HOME `quoted`", audio=self.audio, notes=self.notes, **kw)


class PublishingTests(PublishingFixture, unittest.TestCase):
    @patch.object(publisher.subprocess, 'run')
    def test_dry_run_is_offline_and_draft_and_quotes_arguments(self, transport):
        plan = self.create()
        transport.assert_not_called()
        args = shlex.split(plan['command'])
        self.assertNotIn('--publish', args)
        self.assertIn("--title=Title's $HOME `quoted`", args)
        self.assertIn('--podcast=articles', args)
        self.assertTrue(any(a.startswith('--audio=/srv/incoming files/') for a in args))

    def test_explicit_target_required(self):
        with self.assertRaises(ValueError):
            publisher.run_episode(self.config, None, 'publish', 'test-episode')

    @patch.object(publisher.subprocess, 'run')
    def test_transcript_dry_run_is_offline_and_scoped(self, transport):
        transcript = Path(self.temp.name) / 'captions.vtt'
        transcript.write_text('WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Alice>Test.\n\n')
        result = publisher.run_episode(self.config, 'original-show', 'update', 'test-episode', transcript=transcript)
        self.assertIn('--podcast=original-show', result['command'])
        self.assertIn('--transcript=', result['command'])
        self.assertNotIn('--audio=', result['command'])
        self.assertNotIn('--publish', result['command'])
        transport.assert_not_called()

    @patch.object(publisher, 'inspect')
    @patch.object(publisher, 'remote_json', return_value={'id': 7})
    @patch.object(publisher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    def test_transcript_readback_checks_attachment_and_preserves_audio(self, transport, remote, inspect):
        transcript = Path(self.temp.name) / 'captions.vtt'
        transcript.write_text('WEBVTT\n')
        old = self.episode(guid='original', published_at='2026-08-26')
        new = dict(old, transcript_id=20, transcript_url='https://host/captions.vtt')
        inspect.side_effect = [self.state(old), self.state(new)]
        result = publisher.run_episode(self.config, 'original-show', 'update', 'test-episode', transcript=transcript, apply=True,receipt=self.new_receipt())
        self.assertEqual(result['episode']['transcript_id'], 20)
        changed = dict(new, guid='changed')
        inspect.side_effect = [self.state(old), self.state(changed)]
        with self.assertRaisesRegex(RuntimeError, 'changed guid'):
            publisher.run_episode(self.config, 'original-show', 'update', 'test-episode', transcript=transcript, apply=True,receipt=self.new_receipt())

    @patch.object(publisher, 'inspect')
    @patch.object(publisher.subprocess, 'run')
    def test_duplicate_creation_stops_before_upload(self, transport, inspect):
        inspect.return_value = self.state(self.episode())
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.create(apply=True,receipt=self.new_receipt())
        transport.assert_not_called()

    @patch.object(publisher, 'inspect')
    @patch.object(publisher.subprocess, 'run')
    def test_missing_episode_stops_update(self, transport, inspect):
        inspect.return_value = self.state()
        with self.assertRaisesRegex(RuntimeError, 'not found'):
            publisher.run_episode(self.config, 'articles', 'update', 'test-episode', title='New', apply=True,receipt=self.new_receipt())
        transport.assert_not_called()

    @patch.object(publisher, 'inspect')
    @patch.object(publisher, 'remote_json', return_value={'id': 7})
    @patch.object(publisher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    def test_verified_create_uploads_then_cleans_own_staging(self, transport, remote, inspect):
        episode = self.episode(title="Title's $HOME `quoted`")
        inspect.side_effect = [self.state(), self.state(episode)]
        self.assertEqual(self.create(apply=True,receipt=self.new_receipt())['episode']['id'], 7)
        self.assertEqual(remote.call_count, 1)
        commands = [call.args[0][-1] for call in transport.call_args_list]
        self.assertEqual(sum(c.startswith('cat >') for c in commands), 2)
        self.assertTrue(commands[-1].startswith('rm -f -- '))
        self.assertNotIn('rm -rf', commands[-1])

    @patch.object(publisher, 'inspect')
    @patch.object(publisher, 'remote_json', return_value={'id': 7})
    @patch.object(publisher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    def test_failed_readback_retains_staging_and_does_not_retry(self, transport, remote, inspect):
        inspect.side_effect = [self.state(), self.state(self.episode(title='Wrong'))]
        with self.assertRaisesRegex(RuntimeError, 'title differs'):
            self.create(apply=True,receipt=self.new_receipt())
        self.assertEqual(remote.call_count, 1)
        self.assertFalse(any(call.args[0][-1].startswith('rm ') for call in transport.call_args_list))

    @patch.object(publisher, 'inspect')
    @patch.object(publisher, 'remote_json', return_value={'id': 7})
    def test_draft_publish_is_separate_and_cannot_republish(self, remote, inspect):
        inspect.side_effect = [self.state(self.episode()), self.state(self.episode(status='published'))]
        result = publisher.run_episode(self.config, 'articles', 'publish', 'test-episode', apply=True,receipt=self.new_receipt())
        self.assertEqual(result['episode']['status'], 'published')
        self.assertIn('castopod-publish-draft.php', remote.call_args.args[1])
        inspect.side_effect = None
        inspect.return_value = self.state(self.episode(status='published'))
        with self.assertRaisesRegex(RuntimeError, 'not a draft'):
            publisher.run_episode(self.config, 'articles', 'publish', 'test-episode', apply=True,receipt=self.new_receipt())
        self.assertEqual(remote.call_count, 1)

    @patch.object(publisher, 'inspect')
    @patch.object(publisher, 'remote_json', return_value={'id': 7})
    @patch.object(publisher.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    def test_replacement_rejects_changed_enclosure_url(self, transport, remote, inspect):
        inspect.side_effect = [self.state(self.episode()), self.state(self.episode(audio_url='https://wrong/file.mp3'))]
        with self.assertRaisesRegex(RuntimeError, 'URL changed'):
            publisher.run_episode(self.config, 'articles', 'update', 'test-episode', audio=self.audio, apply=True,receipt=self.new_receipt())


class ChapterPublishingTests(PublishingFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.chapters=Path(self.temp.name)/'chapters.json'
        self.chapters.write_text(json.dumps(dict(version='1.2.0',chapters=[dict(startTime=0,title='Introduction')])))
        self.expected=Path(self.temp.name)/'expected.json'
        self.expected.write_text(json.dumps(self.episode()))

    def update(self,**kwargs):
        return publisher.run_episode(self.config,'articles','update','test-episode',chapters=self.chapters,
            notes=self.notes,expected_state=self.expected,**kwargs)

    def state(self,episode=None):
        return dict(super().state(episode),features=['chapters','conditional-update'])

    @patch.object(publisher.subprocess,'run')
    def test_chapter_plan_is_offline_and_changes_only_chapters_and_notes(self,run):
        plan=self.update();self.assertIn('--chapters=',plan['command']);self.assertIn('--expected-state=',plan['command'])
        self.assertNotIn('--audio=',plan['command']);run.assert_not_called()
        with self.assertRaisesRegex(ValueError,'only chapters and notes'):
            publisher.run_episode(self.config,'articles','update','test-episode',chapters=self.chapters,audio=self.audio)

    @patch.object(publisher,'inspect')
    @patch.object(publisher,'remote_json',return_value={'id':7})
    @patch.object(publisher.subprocess,'run',return_value=subprocess.CompletedProcess([],0))
    def test_conditional_native_attachment_is_receipt_bound_and_preserves_identity(self,run,remote,inspect):
        old=self.episode();new=dict(old,chapters_id=3,chapters_url='https://example.org/chapters.json')
        inspect.side_effect=[self.state(old),self.state(new)]
        receipt=self.new_receipt();self.update(apply=True,receipt=receipt)
        self.assertEqual(set(json.loads(receipt.read_text())['inputs']),{'notes','chapters','expected_state'})
        inspect.side_effect=[self.state(old),self.state(dict(new,audio_file_key='changed.mp3'))]
        with self.assertRaisesRegex(RuntimeError,'changed audio_file_key'):self.update(apply=True,receipt=self.new_receipt())

    @patch.object(publisher,'inspect')
    @patch.object(publisher.subprocess,'run')
    def test_stale_snapshot_or_missing_server_feature_stops_before_upload(self,run,inspect):
        inspect.return_value=self.state(self.episode(title='Owner edited title'))
        with self.assertRaisesRegex(RuntimeError,'changed since inspection'):self.update(apply=True,receipt=self.new_receipt())
        inspect.return_value=dict(self.state(self.episode()),features=[])
        with self.assertRaisesRegex(RuntimeError,'matching reviewed server helpers'):self.update(apply=True,receipt=self.new_receipt())
        run.assert_not_called()


class NumberPublishingTests(PublishingFixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.expected=Path(self.temp.name)/'expected.json'
        self.old=self.episode(number=None,guid='unchanged-uuid')
        self.expected.write_text(json.dumps(self.old))

    def test_number_correction_requires_separate_conditional_update(self):
        for options in ({},dict(notes=self.notes,expected_state=self.expected)):
            with self.assertRaisesRegex(ValueError,'number-only conditional'):
                publisher.run_episode(self.config,'articles','update','test-episode',number=79,**options)

    @patch.object(publisher,'inspect')
    @patch.object(publisher,'remote_json',return_value={'id':7})
    @patch.object(publisher.subprocess,'run',return_value=subprocess.CompletedProcess([],0))
    def test_number_readback_preserves_uuid_and_rejects_any_other_change(self,run,remote,inspect):
        def state(episode):return dict(self.state(episode),features=['conditional-update','episode-number'])
        inspect.side_effect=[state(self.old),state(dict(self.old,number=79))]
        publisher.run_episode(self.config,'articles','update','test-episode',number=79,expected_state=self.expected,apply=True,receipt=self.new_receipt())
        inspect.side_effect=[state(self.old),state(dict(self.old,number=79,guid='changed'))]
        with self.assertRaisesRegex(RuntimeError,'numbering changed guid'):
            publisher.run_episode(self.config,'articles','update','test-episode',number=79,expected_state=self.expected,apply=True,receipt=self.new_receipt())


class GuardAndConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_pause_must_be_explicit_false_and_readable(self):
        pause=self.root/'pause.json';config={'maintenance_pause':str(pause)}
        with patch.object(publisher.os,'access',return_value=False):
            for value in (True,0,'false',None):
                pause.write_text(json.dumps({'paused':value}))
                with self.subTest(value=value),self.assertRaises(RuntimeError):publisher.ensure_database_writes_allowed(config)
            pause.write_text('{malformed')
            with self.assertRaises(RuntimeError):publisher.ensure_database_writes_allowed(config)
            pause.write_text(json.dumps({'paused':False}));publisher.ensure_database_writes_allowed(config)
            pause.unlink()
            with self.assertRaises(RuntimeError):publisher.ensure_database_writes_allowed(config)
        with self.assertRaises(RuntimeError):publisher.ensure_database_writes_allowed({})

    def test_same_user_pause_is_supported_and_symlink_is_refused(self):
        pause=self.root/'pause.json';pause.write_text('{"paused":false}')
        publisher.ensure_database_writes_allowed({'maintenance_pause':str(pause)})
        link=self.root/'linked.json';link.symlink_to(pause)
        with self.assertRaisesRegex(RuntimeError,'unavailable'):
            publisher.ensure_database_writes_allowed({'maintenance_pause':str(link)})

    def test_apply_refuses_missing_pause_before_transport(self):
        with patch.object(publisher.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'maintenance_pause'):
                publisher.run_episode({'app':'/srv/app','user':'publisher','incoming':'/srv/incoming','cli':'/srv/helpers','ssh':'host','state_dir':str(self.root/'state')},'show','publish','episode',apply=True,receipt=self.root/'op.json')
            run.assert_not_called()

    def test_local_transport_and_private_config(self):
        config={'transport':'local','app':'/srv/app','user':'publisher','incoming':'/srv/incoming','cli':'/srv/helpers'}
        path=self.root/'config.json';publisher.save(path,config)
        parsed=publisher.load_config(path)
        self.assertEqual(publisher.transport_args(parsed,"printf '%s' safe"),['/bin/bash','-c',"printf '%s' safe"])
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'0600'):publisher.load_config(path)

    def test_strict_ssh_does_not_use_shared_agent_or_forwarding(self):
        args=publisher.transport_args({'ssh':'podcast-host','ssh_config':'/private/ssh.conf'},'id')
        for value in ('IdentityAgent=none','ForwardAgent=no','ClearAllForwardings=yes','StrictHostKeyChecking=yes','ControlPath=none'):
            self.assertIn(value,args)
        self.assertEqual(args[-2:],['podcast-host','id'])

    def test_read_only_legacy_inspect_works_but_rejects_wrong_show(self):
        config={'ssh':'host','cli':'/srv/helpers','app':'/srv/app','user':'publisher'}
        with patch.object(publisher,'remote_json',return_value={'podcast':{'handle':'show'},'episode':None}):
            publisher.inspect(config,'show','episode')
            with self.assertRaisesRegex(RuntimeError,'different podcast'):publisher.inspect(config,'other','episode')


class DurableOperationTests(PublishingFixture, unittest.TestCase):
    def test_verified_repeat_reuses_receipt_without_transport_and_changed_input_is_refused(self):
        receipt=self.new_receipt()
        with patch.object(publisher,'inspect',side_effect=[self.state(),self.state(self.episode(title="Title's $HOME `quoted`"))]),patch.object(publisher,'remote_json',return_value={'id':7}),patch.object(publisher.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
            self.create(apply=True,receipt=receipt)
        with patch.object(publisher.subprocess,'run') as run,patch.object(publisher,'inspect') as inspect:
            self.assertTrue(self.create(apply=True,receipt=receipt)['receipt_replayed'])
            self.notes.write_text('Changed notes')
            with self.assertRaisesRegex(RuntimeError,'different input/target'):self.create(apply=True,receipt=receipt)
            run.assert_not_called();inspect.assert_not_called()

    def test_unknown_outcome_cannot_be_resubmitted_under_same_receipt(self):
        receipt=self.new_receipt()
        with patch.object(publisher,'inspect',return_value=self.state()),patch.object(publisher,'remote_json',side_effect=RuntimeError('Synthetic lost mutation response')),patch.object(publisher.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
            with self.assertRaisesRegex(RuntimeError,'lost mutation'):self.create(apply=True,receipt=receipt)
        self.assertEqual(json.loads(receipt.read_text())['phase'],'applying')
        with patch.object(publisher,'inspect') as inspect:
            with self.assertRaisesRegex(RuntimeError,'unresolved'):self.create(apply=True,receipt=receipt)
            inspect.assert_not_called()

    def test_changed_input_during_upload_stops_before_database_mutation(self):
        receipt=self.new_receipt()
        def uploaded(args,**kwargs):
            if args[-1].startswith('cat >'):self.notes.write_text('Changed concurrently')
            return subprocess.CompletedProcess([],0)
        with patch.object(publisher,'inspect',return_value=self.state()),patch.object(publisher.subprocess,'run',side_effect=uploaded),patch.object(publisher,'remote_json') as mutation:
            with self.assertRaisesRegex(RuntimeError,'Input changed'):self.create(apply=True,receipt=receipt)
            mutation.assert_not_called()

    def test_pause_changed_during_preflight_blocks_even_staging(self):
        with patch.object(publisher,'ensure_database_writes_allowed',side_effect=[None,None,RuntimeError('Maintenance started')]),patch.object(publisher,'inspect',return_value=self.state()),patch.object(publisher.subprocess,'run') as run,patch.object(publisher,'remote_json') as mutate:
            with self.assertRaisesRegex(RuntimeError,'Maintenance started'):self.create(apply=True,receipt=self.new_receipt())
            run.assert_not_called();mutate.assert_not_called()

    def test_episode_lock_excludes_same_target_but_allows_another(self):
        with publisher.episode_lock(self.config,'articles','test-episode'):
            with self.assertRaisesRegex(RuntimeError,'Another operation'):
                with publisher.episode_lock(self.config,'articles','test-episode'):pass
            with publisher.episode_lock(self.config,'articles','other-episode'):pass

    def test_legacy_helper_cohort_cannot_mutate(self):
        legacy=self.state();legacy.pop('helper_api')
        with patch.object(publisher,'inspect',return_value=legacy),patch.object(publisher.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'matching reviewed server'):self.create(apply=True,receipt=self.new_receipt())
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
