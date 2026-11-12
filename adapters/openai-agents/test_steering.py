import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import steering as s
import episodes as e


class SteeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.home=self.root/'marmot';self.home.mkdir()
        e.save(self.home/'podcaster-instance.json',dict(state_root=str(self.root/'state')))
        self.config=dict(followup_steering=True,marmot_home=str(self.home),trusted_hex='c'*64,incoming_message=dict(message_id='0'*64))
        self.route=dict(account='a'*64,group='b'*32,cwd=str(self.root))
        self.folder=self.root/'turn';self.folder.mkdir();(self.folder/'input.json').write_text('{}')
        self.messages=[];self.api=Mock()
        self.auth=Mock(side_effect=lambda m:dict(account=self.route['account'],group=self.route['group'],sender='c'*64,
            message_id=m['message_id_hex'],text=m['text'],recorded_at=m['recorded_at'],reply_to=None))
        self.follow=s.Followups(self.config,self.route,self.folder,'session',self.auth,lambda _:dict(messages=self.messages))

    def message(self,identifier='1',text='Actually, use the corrected wording.',**kwargs):
        return dict(message_id_hex=identifier*64,text=text,recorded_at=self.follow.since,
            direction='received',availability='available',sender=dict(account_id_hex='c'*64),**kwargs)

    def test_followup_is_submitted_to_same_session_once_and_later_delivery_is_consumed(self):
        self.messages=[self.message()]
        self.assertEqual(self.follow.scan(self.api,dict(id='active'),10),1)
        self.assertEqual(self.api.call.call_args.args[0],'sessions/session/events')
        incoming=self.auth(self.messages[0])
        self.assertTrue(s.consumed(self.config,incoming,self.route))
        self.assertEqual(self.follow.scan(self.api,dict(id='active'),12),0)
        self.assertEqual(self.api.call.call_count,1)
        s.finish(self.config,self.folder,'final')
        self.assertTrue(s.consumed(self.config,incoming,self.route))
        with self.assertRaises(RuntimeError):s.consumed(self.config,dict(incoming,text='changed'),self.route)
        with self.assertRaises(RuntimeError):s.consumed(self.config,incoming,dict(self.route,cwd='/other'))

    def test_plain_yes_can_steer_but_exact_approval_stays_separate(self):
        self.assertTrue(s.ordinary('yes'))
        self.assertFalse(s.ordinary('yes 123456abcdef'))
        self.assertFalse(s.ordinary('approve'))
        self.messages=[self.message(text='yes',reply_to_message_id_hex='a'*64)]
        self.assertEqual(self.follow.scan(self.api,dict(id='active'),10),0)
        self.api.call.assert_not_called()

    def test_two_distinct_identical_replies_are_distinct_inputs(self):
        self.messages=[self.message('1'),self.message('2')]
        self.assertEqual(self.follow.scan(self.api,dict(id='active'),10),2)
        self.assertEqual(self.api.call.call_count,2)
        self.assertNotEqual(*[call.args[2] for call in self.api.call.call_args_list])

    def test_steered_question_reply_is_saved_for_semantic_review(self):
        questions=self.root/'questions';questions.mkdir()
        cfg=self.root/'transcription.json';e.save(cfg,dict(feedback_root=str(questions)))
        self.config['transcription_config']=str(cfg)
        e.save(questions/'question.json',dict(id='question',state='waiting',account=self.route['account'],
            group=self.route['group'],trusted_sender='c'*64,sent_at=e.now(),message_ids=['d'*64]))
        self.messages=[self.message()]
        self.follow.scan(self.api,dict(id='active'),10)
        question=e.read(questions/'question.json')
        self.assertEqual(question['state'],'reply-received')
        self.assertEqual(question['reply']['message_id'],'1'*64)
        self.assertEqual(e.read(self.follow.accepted[0])['feedback_question'],'question')

    def test_stale_original_untrusted_media_and_commands_never_steer(self):
        stale=self.message('2');stale['recorded_at']-=1
        foreign=self.message('3');foreign['sender']['account_id_hex']='f'*64
        self.messages=[self.message('0'),stale,foreign,self.message('4',media=[{}]),
            self.message('5',text='podcast status'),self.message('6',text='transcribe nado 11'),
            self.message('7',text='approve 123456abcdef'),self.message('8',text='/reset-session')]
        self.assertEqual(self.follow.scan(self.api,dict(id='active'),10),0)
        self.api.call.assert_not_called();self.auth.assert_not_called()

    def test_lost_acceptance_never_resubmits_under_another_id(self):
        self.messages=[self.message()];self.api.call.side_effect=TimeoutError('fixture')
        with self.assertRaises(TimeoutError):self.follow.scan(self.api,dict(id='active'),10)
        self.api.call.side_effect=None
        with self.assertRaises(RuntimeError):self.follow.scan(self.api,dict(id='active'),12)
        self.assertEqual(self.api.call.call_count,1)

    def test_completion_race_waits_for_input_in_its_actual_terminal_turn(self):
        self.messages=[self.message()];self.follow.scan(self.api,dict(id='active'),10)
        marker=e.read(self.follow.accepted[0])['marker']
        item=dict(type='message',role='user',turn_id='later',content=[dict(type='input_text',text=marker)])
        self.assertFalse(self.follow.settled([], [dict(id='active',status='completed')]))
        self.assertFalse(self.follow.settled([item],[dict(id='active',status='completed'),dict(id='later',status='in_progress')]))
        self.assertTrue(self.follow.settled([item],[dict(id='active',status='completed'),dict(id='later',status='completed')]))

    def test_failed_authentication_has_no_submission_effect(self):
        self.messages=[self.message()];self.auth.side_effect=RuntimeError('not authenticated')
        with self.assertRaises(RuntimeError):self.follow.scan(self.api,dict(id='active'),10)
        self.api.call.assert_not_called()

    def test_already_queued_bridge_delivery_is_quiet_without_another_model_call(self):
        spec=importlib.util.spec_from_file_location('steering_backend',Path(__file__).with_name('marmot-backend.py'))
        b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
        self.messages=[self.message()];self.follow.scan(self.api,dict(id='active'),10)
        config=dict(self.config,incoming_message=self.auth(self.messages[0]))
        events=[]
        with patch.object(b,'emit',side_effect=events.append),patch.object(b,'conversation') as run:
            b.dispatch(config,'handle',self.messages[0]['text'],self.route)
        run.assert_not_called()
        self.assertEqual(events,[dict(type='thread.started',thread_id='handle'),dict(type='adapter.silent'),dict(type='turn.completed')])


if __name__=='__main__':unittest.main()
