import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import transcribe
import transcription_feedback as feedback

class TranscriptTests(unittest.TestCase):
 def test_feedback_question_uses_readable_time_and_no_routing_token(self):
  text=feedback.question_text(dict(number='14'),dict(start=1311,duration=30,question='Did you say use?',provisional='use',test_required=True))
  self.assertIn('Episode 14, 21:51–22:21.',text)
  self.assertIn('Reply here',text)
  self.assertNotIn('Question ',text)
  self.assertNotIn('include ',text)
  self.assertNotIn('test',text)

 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.root.chmod(0o700)
 def test_scope_requires_exact_authorized_final_audio(self):
  episode=dict(guid='one',number='18',final_audio_sha256='a'*64);config=dict(paused=False,episodes={'one':dict(number='18',final_audio_sha256='a'*64)})
  transcribe.scope(config,episode)
  with self.assertRaises(ValueError):transcribe.scope(dict(config,paused=True),episode)
  with self.assertRaises(ValueError):transcribe.scope(config,dict(episode,final_audio_sha256='b'*64))
 def test_feedback_authentication_routing_idempotency_and_required_gate(self):
  root=self.root/'feedback';root.mkdir();path=root/'one.json'
  q=dict(id='abc',state='waiting',episode_guid='guid',account='a'*64,group='b'*64,trusted_sender='c'*64,sent_at='2026-01-01T00:00:00+00:00',message_ids=['d'*64])
  e.save(path,q);config=dict(feedback_root=str(root),episodes={'guid':dict(force_feedback=True)},account_id_hex=q['account'],group_id_hex=q['group'],trusted_hex=q['trusted_sender'])
  incoming=dict(account='a'*64,group='b'*64,sender='e'*64,message_id='f'*64,recorded_at=1800000000,text='yes',reply_to='d'*64)
  self.assertIsNone(feedback.receive(config,incoming))
  trusted=dict(incoming,sender='c'*64)
  for text,reply in [('help',None),('podcast status',None),('yes','unrelated'),('approve 123456abcdef',None)]:
   self.assertIsNone(feedback.receive(config,dict(trusted,text=text,reply_to=reply)))
  with self.assertRaises(ValueError):feedback.require_for_publication(config,dict(guid='guid'))
  accepted=feedback.receive(config,dict(incoming,sender='c'*64));self.assertEqual(accepted['state'],'reply-received')
  with self.assertRaises(ValueError):feedback.require_for_publication(config,dict(guid='guid'))
  self.assertEqual(feedback.classify(config,q['id'],trusted['message_id'],'answer')['state'],'answered')
  self.assertEqual(feedback.receive(config,dict(incoming,sender='c'*64))['id'],q['id'])
  self.assertEqual(len(feedback.require_for_publication(config,dict(guid='guid'))),1)
  new=dict(q,id='new',state='waiting');e.save(root/'two.json',new)
  self.assertEqual(feedback.receive(config,trusted)['id'],q['id'])
  self.assertEqual(e.read(root/'two.json')['state'],'waiting')
  self.assertEqual(feedback.receive(config,dict(trusted,message_id='0'*64,reply_to=None))['id'],'new')
 def test_operator_reuses_explicit_group_even_when_phone_workspace_is_home(self):
  path=Path(__file__).resolve().parents[1]/'adapters/openai-agents/task.py'
  spec=importlib.util.spec_from_file_location('operator_task',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  config=dict(account_id_hex='a'*64,workspace_root=str(self.root),repository=str(self.root/'repo'))
  record=dict(binding=dict(account='a'*64,group='b'*32,cwd=str(self.root)))
  self.assertEqual(module.paired_route(config,dict(group_id_hex='b'*32),[record]),record)
  with self.assertRaises(ValueError):module.paired_route(config,dict(group_id_hex='c'*32),[record])
  with self.assertRaises(ValueError):module.paired_route(config,dict(group_id_hex='b'*32),[record,record])
 def test_same_user_maintenance_pause_can_be_managed_without_sudo(self):
  cp=transcribe.transport();guard=self.root/'maintenance.json'
  e.save(guard,dict(paused=False))
  cp.ensure_database_writes_allowed(dict(maintenance_pause=str(guard)))
  e.save(guard,dict(paused=True))
  with self.assertRaises(RuntimeError):cp.ensure_database_writes_allowed(dict(maintenance_pause=str(guard)))
  guard.unlink()
  with self.assertRaises(RuntimeError):cp.ensure_database_writes_allowed(dict(maintenance_pause=str(guard)))

class ReviewEvidenceTests(unittest.TestCase):
 def test_windows_refuse_out_of_source_and_unbounded_work(self):
  import transcription_review as review
  self.assertEqual(len(review.windows([dict(start=2,end=4)],10)),1)
  for selected in [[],[dict(start=-1,end=3)],[dict(start=1,end=101)],[dict(start=0,end=11)]]:
   with self.assertRaises(ValueError):review.windows(selected,10)
 def test_rendered_paragraphs_preserve_order_grouping_and_duplicates(self):
  import captions
  cues=[dict(speaker='One',text='First.'),dict(speaker='One',text='Second.'),dict(speaker='Two',text='Third.')]
  page='<p>First. is mentioned in the description.</p><main><article><p><span>One</span> First. Second.</p></article><article><p>Two Third.</p></article></main><p>Third. is mentioned in the footer.</p>'
  self.assertEqual(captions.compare_paragraphs(page,cues)['transcript_paragraphs'],2)
  for wrong in [page.replace('First. Second.','Second. First.'),page.replace(' Second.',''),page.replace('</main>','<article><p>Two Third.</p></article></main>'),page.replace('Two Third.','Two Changed.'),page.replace('<main>','<div>').replace('</main>','</div>')]:
   with self.assertRaises(ValueError):captions.compare_paragraphs(wrong,cues)
  self.assertEqual(captions.compare_paragraphs(page.replace('First. Second.','First.  Second.'),cues)['transcript_paragraphs'],2)

class UsageTests(unittest.TestCase):
 def test_cancelled_turns_count_once_and_missing_is_unknown(self):
  path=Path(__file__).resolve().parents[1]/'adapters/openai-agents/task.py';spec=importlib.util.spec_from_file_location('operator_usage',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  one=dict(id='one',status='cancelled',usage=dict(input_tokens=20,input_tokens_details={'cached_tokens':10},output_tokens=2,total_tokens=22))
  result=module.usage_summary([one,one,dict(id='two',usage=None)])
  self.assertEqual(result['tokens']['input_tokens'],20);self.assertEqual(result['tokens']['cached_input_tokens'],10)
  self.assertFalse(result['complete']);self.assertEqual(result['missing_usage_turn_ids'],['two']);self.assertIsNone(result['billed_cost'])

class ReactionAndPacketTests(unittest.TestCase):
 def test_reaction_requires_exact_question_and_trusted_actor(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);q=dict(id='question',state='waiting',account='a'*64,group='b'*32,trusted_sender='c'*64,sent_at='2026-01-01T00:00:00+00:00',message_ids=['d'*64]);e.save(root/'q.json',q)
   cfg=dict(feedback_root=str(root),account_id_hex=q['account'],group_id_hex=q['group'],trusted_hex=q['trusted_sender'])
   msg=dict(direction='sent',availability='available',sender={'account_id_hex':'a'*64},message_id_hex='d'*64)
   reaction=dict(actor={'account_id_hex':'c'*64},emoji='👍',reaction_message_id_hex='e'*64,reacted_at=1800000000)
   self.assertIsNone(feedback.receive_reaction(cfg,msg,dict(reaction,actor={'account_id_hex':'f'*64})))
   self.assertIsNone(feedback.receive_reaction(cfg,dict(msg,message_id_hex='f'*64),reaction))
   self.assertIsNone(feedback.receive_reaction(cfg,msg,dict(reaction,emoji='❤️')))
   self.assertIsNone(feedback.receive_reaction(cfg,msg,dict(reaction,reacted_at=1)))
   self.assertEqual(feedback.receive_reaction(cfg,msg,reaction)['state'],'answered')
   self.assertEqual(e.read(root/'q.json')['reply']['message_id'],'e'*64)
   self.assertIsNone(feedback.receive_reaction(cfg,msg,reaction))
 def test_packet_groups_original_word_indices_and_paginates(self):
  import transcription_packet as packet
  words=[dict(word=' '+str(i),start=i,end=i+.5) for i in range(20)]
  flags=[dict(word_index=i,reasons=['test']) for i in [2,4,12]]
  grouped=packet.groups(words,flags)
  self.assertEqual([(g['start_word_index'],g['end_word_index_exclusive']) for g in grouped],[(2,5),(12,13)])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);e.save(root/'words-for-review.json',words);e.save(root/'review-flags.json',flags)
   first=packet.packet(root,'flags',0,1);second=packet.packet(root,'flags',1,1)
   self.assertEqual(first['total'],2);self.assertTrue(first['more']);self.assertFalse(second['more'])
   self.assertEqual(second['items'][0]['start_word_index'],12)

class PacketCliTests(unittest.TestCase):
 def test_invalid_limit_is_actionable_usage_error_before_reading_files(self):
  import subprocess
  script=Path(__file__).resolve().parents[1]/'tools/transcription_packet.py'
  result=subprocess.run([sys.executable,str(script),'--folder','/does-not-exist','--limit','120'],capture_output=True,text=True)
  self.assertEqual(result.returncode,2);self.assertIn('1 to 100',result.stderr);self.assertNotIn('Report UUID',result.stderr)

class CompactCueTests(unittest.TestCase):
 def test_compact_display_keeps_complete_text_speaker_and_exact_milliseconds(self):
  import subprocess
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'publication').mkdir();e.save(root/'publication/expected-captions.json',[dict(number=0,startTime=1.234,endTime=2.567,speaker='Full Name',text='An exact sentence, with punctuation.')])
   script=Path(__file__).resolve().parents[1]/'tools/transcription_packet.py'
   out=subprocess.check_output([sys.executable,str(script),'--folder',str(root),'--section','cues','--format','text'],text=True).splitlines()
   self.assertFalse(json.loads(out[0])['more'])
   self.assertIn('1.234–2.567 <Full Name> An exact sentence, with punctuation.',out[1])


class DurableTranscriptJobTests(unittest.TestCase):
 def test_job_uses_configured_runtime_and_places_global_options_before_action(self):
  import jobs
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.json';e.save(config,dict(python=sys.executable))
   request=dict(kind='transcript-recognize',parameters=dict(config=str(config),folder='/private/episode',out='/private/evidence.json',windows='/private/windows.json',model='secondary'))
   command=jobs.command(request)
   self.assertEqual(command[0],sys.executable)
   self.assertLess(command.index('--folder'),command.index('recognize'))
   self.assertGreater(command.index('--windows'),command.index('recognize'))
   self.assertNotIn('/bin/sh',command)
   import subprocess
   self.assertEqual(subprocess.run(command+['--help'],capture_output=True).returncode,0)
   with self.assertRaises(ValueError):jobs.command(dict(request,apply=True))


class CompactEvidenceTests(unittest.TestCase):
 def test_bounded_evidence_view_keeps_all_segment_text_and_source_binding(self):
  import transcription_packet as packet
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);e.save(root/'evidence.json',dict(windows=[dict(window={'start':1,'end':3},segments=[dict(start=1.2,end=2.3,text=' Complete text.',words=[{'large':'metadata'}])])]))
   view=packet.packet(root,'evidence',evidence='evidence.json')
   self.assertEqual(view['items'][0]['segments'],[dict(start=1.2,end=2.3,text=' Complete text.')])
   self.assertEqual(view['source_sha256'],e.file_record(root/'evidence.json')['sha256'])
   with self.assertRaises(ValueError):packet.packet(root,'evidence',evidence='../other.json')

if __name__=='__main__':unittest.main()
