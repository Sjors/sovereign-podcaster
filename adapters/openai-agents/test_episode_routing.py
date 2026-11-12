import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parent))
import episode_routing as routing

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir="/tmp");self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.config={'state_root':str(root/'api'),'work_root':str(root/'work')}
        self.route={'account':'a'*64,'group':'b'*32,'cwd':str(root)}

    def test_transcribe_selects_one_cleared_episode_and_reuses_context(self):
        root=Path(self.tmp.name);settings=root/'transcription.json';catalog=root/'catalog.json'
        routing.episodes.save(settings,dict(paused=False,show='demo',source_catalog=str(catalog)))
        routing.episodes.save(catalog,dict(show='demo',episodes={'15':{}}));self.config['transcription_config']=str(settings)
        with routing.select(self.config,None,'transcribe demo 15',self.route) as selected:
            public=selected.public_handle;first=selected.state_root;self.assertIsNone(selected.reply);self.assertEqual(selected.context,'demo/15')
        with routing.select(self.config,public,'transcribe demo 15',self.route) as selected:self.assertEqual(selected.state_root,first)
        with self.assertRaises(RuntimeError):
            with routing.select(self.config,public,'transcribe demo 14',self.route):pass
        with routing.select(self.config,public,'podcast status',self.route) as selected:self.assertEqual(selected.context,'demo/15')
        self.assertIsNone(routing.command('quoted text: transcribe demo 15'))

    def test_chapters_selects_only_the_configured_cleared_episode_and_group(self):
        root=Path(self.tmp.name);settings=root/'chapters.json';catalog=root/'catalog.json'
        routing.episodes.save(settings,dict(paused=False,show='demo',source_catalog=str(catalog),group_id_hex=self.route['group']))
        routing.episodes.save(catalog,dict(show='demo',episodes={'15':dict(episode=dict(number='15',guid='fixture',final_audio_sha256='a'*64),clearance=dict(audit_complete=True,final_audio_sha256='a'*64))}))
        self.config['chapters_config']=str(settings)
        with routing.select(self.config,None,'chapters demo 15',self.route) as selected:
            public=selected.public_handle;first=selected.state_root;self.assertIsNone(selected.reply);self.assertEqual(selected.context,'demo/15')
        with routing.select(self.config,public,'chapters demo 15',self.route) as selected:self.assertEqual(first,selected.state_root)
        with self.assertRaises(ValueError):
            with routing.select(self.config,public,'chapters demo 14',self.route):pass
        with self.assertRaisesRegex(RuntimeError,'configured chapter conversation'):
            with routing.select(self.config,None,'chapters demo 15',dict(self.route,group='c'*32)):pass
        self.assertIsNone(routing.command('quoted: chapters demo 15'))
        self.assertIsNone(routing.command('chapters demo 15\nalso queue everything'))

    def test_published_transcript_is_visible_and_repeat_command_is_local(self):
        root=Path(self.tmp.name)
        with routing.select(self.config,None,'podcast new demo 15',self.route) as selected:public=selected.public_handle
        with routing.episodes.journal(Path(self.config['work_root'])) as (work,data):
            item=routing.episodes.episode(data,'demo','15');folder=routing.episodes.private_root(Path(item['directory'])/'transcript');item['transcription']={'directory':str(folder)}
            routing.episodes.save(folder/'episode.json',dict(number='15',guid='one'))
            routing.episodes.private_root(folder/'publication');vtt=folder/'publication/transcript.vtt';vtt.write_text('WEBVTT\n')
            routing.episodes.save(folder/'publication/verification.json',dict(verified=True,episode_guid='one',vtt_sha256=routing.episodes.file_record(vtt)['sha256'],transcript_url='https://example.org/transcript.vtt'))
        with routing.select(self.config,public,'episodes',self.route) as selected:self.assertIn('transcript published',selected.reply)
        with routing.select(self.config,public,'transcribe demo 15',self.route) as selected:
            self.assertIn('already published and verified',selected.reply);self.assertIn('https://example.org/transcript.vtt',selected.reply);self.assertIsNone(selected.backend_handle)
        vtt.write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'completion receipt'):
            with routing.select(self.config,public,'transcribe demo 15',self.route):pass

    def test_local_episode_commands_archive_and_resume_independent_contexts(self):
        with routing.select(self.config,None,'podcast new demo one',self.route) as selected:
            public=selected.public_handle;self.assertIn('fresh context',selected.reply)
        with routing.select(self.config,public,'Make slides',self.route) as selected:
            self.assertIsNone(selected.backend_handle);first=selected.state_root
            selected.observe({'type':'thread.started','thread_id':'spapi_'+'1'*32},lambda _:None)
        with routing.select(self.config,public,'podcast new demo two',self.route) as selected:
            self.assertIsNone(selected.backend_handle);self.assertNotEqual(first,selected.state_root)
        with routing.select(self.config,public,'podcast use demo one',self.route) as selected:
            self.assertEqual(selected.backend_handle,'spapi_'+'1'*32);self.assertEqual(first,selected.state_root)
        with routing.select(self.config,public,'podcast status',self.route) as selected:
            self.assertEqual(json.loads(selected.reply)['episode'],'one')

    def test_public_handle_does_not_replace_distinct_backend_handle(self):
        with routing.select(self.config,None,'Hello',self.route) as selected:
            public=selected.public_handle
            selected.observe({'type':'thread.started','thread_id':'spapi_'+'2'*32},lambda _:None)
        with routing.select(self.config,public,'Follow up',self.route) as selected:
            self.assertEqual(selected.backend_handle,'spapi_'+'2'*32)

    def test_local_status_before_first_model_message_does_not_invent_backend_state(self):
        with routing.select(self.config,None,'podcast status',self.route) as selected:public=selected.public_handle
        with routing.select(self.config,public,'Hello',self.route) as selected:
            self.assertIsNone(selected.backend_handle)

    def test_harness_reset_does_not_silently_restart_or_replay_work(self):
        with routing.select(self.config,None,'podcast new demo one',self.route):pass
        with self.assertRaisesRegex(RuntimeError,'Harness session was reset'):
            with routing.select(self.config,None,'Do it again',self.route):pass

    def test_unresolved_work_blocks_switching_to_another_episode(self):
        with routing.select(self.config,None,'podcast new demo one',self.route) as selected:public=selected.public_handle
        with routing.select(self.config,public,'Do work',self.route) as selected:
            selected.observe({'type':'thread.started','thread_id':'spapi_'+'3'*32},lambda _:None)
            selected.state_root.mkdir(parents=True)
            name=__import__('hashlib').sha256(json.dumps(self.route,sort_keys=True).encode()).hexdigest()+'.active.json'
            (selected.state_root/name).write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'unresolved outcome'):
            with routing.select(self.config,public,'podcast new demo two',self.route):pass

    def test_help_and_episode_list_preserve_current_context(self):
        with routing.select(self.config,None,'podcast new demo one',self.route) as selected:public=selected.public_handle
        with routing.select(self.config,public,'help',self.route) as selected:
            self.assertEqual(selected.context,'demo/one');self.assertIn('podcast new SHOW EPISODE',selected.reply)
        with routing.select(self.config,public,'episodes',self.route) as selected:
            self.assertEqual(selected.context,'demo/one');self.assertIn('demo/one',selected.reply)
            self.assertIn('no revision yet',selected.reply)
        with routing.select(self.config,public,'podcast episodes',self.route) as selected:
            self.assertIn('demo/one',selected.reply)

    def test_episode_command_must_be_the_entire_message(self):
        self.assertIsNone(routing.command('help me revise the slides'))
        self.assertIsNone(routing.command('Here is a transcript:\npodcast new demo one'))
        self.assertIsNone(routing.command('podcast new demo one\nalso delete things'))

if __name__=='__main__':unittest.main()
