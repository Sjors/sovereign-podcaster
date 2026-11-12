import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent))
import wakeups as w
import episodes as e

class WakeupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.root.chmod(0o700)
  self.work=self.root/'work';self.api=self.root/'api';self.configpath=self.root/'transcription.json';self.feedback=self.root/'feedback';self.feedback.mkdir(mode=0o700)
  self.config=dict(paused=False,show='demo',feedback_root=str(self.feedback),marmot_home=str(self.root/'marmot'),account_id_hex='a'*64,group_id_hex='b'*32,trusted_hex='c'*64,episodes={'guid':dict(number='15',final_audio_sha256='0'*64)})
  e.save(self.configpath,self.config);self.instance=dict(transcription_config=str(self.configpath),state_root=str(self.api),work_root=str(self.work))
  with e.journal(self.work) as (root,data):
   item=e.initialize(root,data,'demo','15');self.directory=Path(item['directory']);self.folder=e.private_root(self.directory/'transcript');task=self.directory/'task.json'
   e.save(task,dict(source='explicit-user-task',operation='transcript',show='demo',episode='15',episode_guid='guid',directory=str(self.folder)))
   item['transcription']=dict(directory=str(self.folder),task=str(task))
  e.save(self.folder/'episode.json',dict(number='15',guid='guid',final_audio_sha256='0'*64))
  self.route=dict(account='a'*64,group='b'*32,cwd=str(self.root));routeid=hashlib.sha256(json.dumps(self.route,sort_keys=True).encode()).hexdigest();self.state=e.private_root(self.api/'episode-contexts'/routeid/hashlib.sha256(b'demo/15').hexdigest());self.handle='spapi_'+'1'*32
  self.cursor=e.private_root(self.state/'cursors')/(self.handle+'.json');e.save(self.cursor,dict(binding=self.route,session_id='sess_fixture',requests={}))
  self.routing=e.private_root(self.api/'routing')/(routeid+'.json');e.save(self.routing,dict(binding=self.route,selected='demo/other',contexts={'demo/15':dict(handle=self.handle,state_root=str(self.state))}))
  self.fetch=Mock(return_value=self.message());self.run=Mock(return_value='Review finished.');self.deliver=Mock()
  self.failurepatch=patch.object(w.failures,'store_root',return_value=self.root/'failures');self.failurepatch.start();self.addCleanup(self.failurepatch.stop)
 def message(self,reactions=True):
  return dict(message_id_hex='d'*64,sender={'account_id_hex':'a'*64},direction='sent',availability='available',reactions_truncated=False,reactions=[dict(reaction_message_id_hex='e'*64,actor={'account_id_hex':'c'*64},emoji='👍',reacted_at=1800000000)] if reactions else [])
 def question(self):
  e.save(self.feedback/'question.json',dict(id='f'*12,state='waiting',episode='15',episode_guid='guid',folder=str(self.folder),account='a'*64,group='b'*32,trusted_sender='c'*64,sent_at='2026-01-01T00:00:00+00:00',message_ids=['d'*64],question={'start':1,'duration':10}))
 def job(self,name='analysis',state='completed'):
  path=e.private_root(self.work/'jobs'/name)/'job.json';request=dict(kind='transcript-analyze',parameters=dict(config=str(self.configpath),folder=str(self.folder),clusters='3'))
  e.save(path,dict(state=state,exit_code=0,nonce=name,request=request,request_sha256=e.digest(request)));return path
 def once(self):return w.run_once(self.instance,self.fetch,self.run,self.deliver)
 def batches(self):return [p for p in (self.api/'wakeups').glob('batch-*.json') if len(p.stem)==70]
 def test_idle_and_running_jobs_never_read_connector_or_invoke_model(self):
  self.job(state='running');self.once();self.run.assert_not_called();self.fetch.assert_not_called()
 def test_trusted_reaction_resumes_original_context_once_without_switching_selection(self):
  self.question();self.once();self.once();self.assertEqual(self.run.call_count,1);self.deliver.assert_not_called()
  state=self.run.call_args.args[2];self.assertEqual(state['kind'],'reaction');self.assertEqual(state['handle'],self.handle);self.assertEqual(e.read(self.routing)['selected'],'demo/other')
  self.assertEqual(e.read(self.feedback/'question.json')['reply']['message_id'],'e'*64)
 def test_unknown_actor_does_not_answer_or_resume(self):
  self.question();message=self.message();message['reactions'][0]['actor']['account_id_hex']='0'*64;self.fetch.return_value=message;self.once();self.run.assert_not_called();self.assertEqual(e.read(self.feedback/'question.json')['state'],'waiting')
 def test_withdrawn_reaction_is_not_submitted_and_restores_waiting(self):
  self.question();self.fetch.side_effect=[self.message(),self.message(False)];self.once();self.run.assert_not_called();self.assertEqual(e.read(self.feedback/'question.json')['state'],'waiting')
 def test_busy_context_defers_without_duplicates_then_completes(self):
  self.question();self.run.side_effect=[w.b.ConversationBusy(),'Ready'];self.once();self.assertEqual(e.read(self.batches()[0])['phase'],'queued');self.once();self.assertEqual(e.read(self.batches()[0])['phase'],'suppressed');self.deliver.assert_not_called()
 def test_completed_jobs_coalesce_and_are_not_replayed_after_restart(self):
  self.job('one');self.job('two');self.once();self.once();self.assertEqual(self.run.call_count,1);self.assertEqual(len(self.run.call_args.args[2]['events']),2)
 def test_job_batch_waits_for_other_running_checks_before_one_continuation(self):
  self.job('fast');slow=self.job('slow','running');self.once();self.run.assert_not_called()
  state=e.read(slow);state['state']='completed';e.save(slow,state);self.once();self.assertEqual(self.run.call_count,1);self.assertEqual(len(self.run.call_args.args[2]['events']),2)
 def test_pending_human_question_prevents_job_wakeup(self):
  self.question();self.fetch.return_value=self.message(False);self.job();self.once();self.run.assert_not_called()
 def context_request(self):
  self.question()
  incoming=dict(account='a'*64,group='b'*32,sender='c'*64,message_id='1'*64,recorded_at=1799999990,text='Can you give me the minute before this?',reply_to=None)
  w.feedback.receive(self.config,incoming)
  return incoming
 def test_context_request_then_thumb_resumes_once_without_explicit_reopen(self):
  incoming=self.context_request();self.fetch.return_value=self.message(False);self.job();self.once()
  self.run.assert_not_called();self.assertEqual(e.read(self.feedback/'question.json')['state'],'reply-received')
  with self.assertRaises(ValueError):w.feedback.require_for_publication(self.config,dict(guid='guid'))
  self.fetch.return_value=self.message();self.run.side_effect=lambda *args:(self.complete() or 'Published and verified.')
  self.once();self.once()
  self.assertEqual(self.run.call_count,1);self.assertEqual(self.run.call_args.args[2]['kind'],'reaction')
  q=e.read(self.feedback/'question.json');self.assertEqual(q['state'],'answered');self.assertIn(incoming,q['reply_history'])
  w.feedback.receive(self.config,incoming)
  self.assertEqual(e.read(self.feedback/'question.json')['reply']['message_id'],'e'*64)
 def test_withdrawn_thumb_restores_unclassified_context_request(self):
  incoming=self.context_request();self.fetch.side_effect=[self.message(),self.message(False)];self.once()
  self.run.assert_not_called();q=e.read(self.feedback/'question.json')
  self.assertEqual(q['state'],'reply-received');self.assertEqual(q['reply'],incoming)
  with self.assertRaises(ValueError):w.feedback.require_for_publication(self.config,dict(guid='guid'))
 def test_delivered_reaction_does_not_hide_a_later_job(self):
  self.question();self.once();self.job();self.once();self.assertEqual(self.run.call_count,2);self.assertEqual(self.run.call_args.args[2]['kind'],'job')
 def test_published_episode_never_starts_another_turn(self):
  e.private_root(self.folder/'publication');e.save(self.folder/'publication/verification.json',dict(verified=True));self.question();self.job();self.once();self.run.assert_not_called();self.fetch.assert_not_called()
 def complete(self):
  e.private_root(self.folder/'publication');(self.folder/'publication/transcript.vtt').write_text('WEBVTT\n')
  e.save(self.folder/'publication/verification.json',dict(verified=True,episode_guid='guid',vtt_sha256=e.file_record(self.folder/'publication/transcript.vtt')['sha256']))
 def test_cached_answer_survives_crash_after_publication_before_notification(self):
  self.job();self.run.side_effect=w.b.ConversationBusy();self.once();path=self.batches()[0];state=e.read(path);state['phase']='running';e.save(path,state)
  cursor=e.read(self.cursor);cursor['requests'][state['request_key']]=dict(phase='completed',answer='Saved answer');e.save(self.cursor,cursor);self.complete()
  self.run.reset_mock();self.once();self.run.assert_not_called();self.assertIn('Saved answer',self.deliver.call_args.args[2])
 def test_uncertain_input_is_reported_once_and_not_resubmitted(self):
  self.job();self.run.side_effect=RuntimeError('Earlier work uncertain');self.once();self.once();self.assertEqual(self.run.call_count,1);self.assertEqual(e.read(self.batches()[0])['phase'],'blocked');self.assertIn('Report UUID',self.deliver.call_args.args[2])
 def test_intermediate_turns_are_saved_silently_then_final_result_is_sent_once(self):
  self.job();self.once();self.deliver.assert_not_called()
  state=e.read(self.batches()[0]);self.assertEqual(state['answer'],'Review finished.');self.assertEqual(state['phase'],'suppressed')
  self.job('wording');self.run.side_effect=lambda *args:(self.complete() or 'Published and verified. Estimated model cost: $0.02.')
  self.once();self.once();self.assertEqual(self.deliver.call_count,1);self.assertIn('Estimated model cost',self.deliver.call_args.args[2]);self.assertEqual(self.run.call_count,2)
 def test_model_failure_uuid_is_delivered_without_intermediate_private_text(self):
  self.job();self.run.return_value='Private details. Report UUID: 12345678-1234-4234-8234-123456789abc';self.once();self.once()
  self.assertEqual(self.deliver.call_count,1);self.assertIn('Report UUID:',self.deliver.call_args.args[2]);self.assertNotIn('Private details',self.deliver.call_args.args[2])
 def test_pending_legacy_send_intent_is_not_silently_suppressed(self):
  self.job();self.run.side_effect=w.b.ConversationBusy();self.once();path=self.batches()[0];state=e.read(path);state.update(phase='model-completed',answer='Legacy progress');e.save(path,state)
  e.save(path.with_suffix('.send.json'),dict(text='Immutable old progress'))
  self.once();self.assertEqual(self.deliver.call_args.args[2],'Immutable old progress')
 def test_notification_manifests_are_not_mistaken_for_batch_state(self):
  self.job();self.once();path=self.batches()[0];e.save(path.with_suffix('.send.json'),{'text':'inert fixture'});self.once();self.assertEqual(self.run.call_count,1)

if __name__=='__main__':unittest.main()
