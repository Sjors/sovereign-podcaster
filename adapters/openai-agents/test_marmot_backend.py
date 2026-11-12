import hashlib
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('backend',Path(__file__).with_name('marmot-backend.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.home_patch=patch.object(Path,'home',return_value=self.root);self.home_patch.start();self.addCleanup(self.home_patch.stop)
        self.auth_patch=patch.object(b.messages,'authenticated',side_effect=lambda config,env,prompt:dict(account='a'*64,group='b'*32,sender='c'*64,message_id=hashlib.sha256(prompt.encode()).hexdigest(),text=prompt,recorded_at=1,reply_to=None));self.auth_patch.start();self.addCleanup(self.auth_patch.stop)
        self.config={'work_root':str(self.root/'work'),'state_root':str(self.root/'state'),'model':'gpt-6.1-sol','repository':str(self.root),
                     'account_id_hex':'a'*64,'workspace_root':str(self.root)}
        self.route={'account':'a'*64,'group':'b'*32,'cwd':str(self.root)}
        self.api=Mock();self.api.key='synthetic-app'
        self.api.call.side_effect=self.api_call
        self.calls=[];self.events=[]
        self.patcher=patch.object(b,'emit',side_effect=self.events.append);self.patcher.start();self.addCleanup(self.patcher.stop)

    def conversation(self,config,handle,prompt,*args,**kwargs):
        incoming=dict(message_id=hashlib.sha256(prompt.encode()).hexdigest(),sender='c'*64,text=prompt)
        return b.conversation(dict(config,incoming_message=incoming),handle,prompt,*args,**kwargs)

    def test_short_wrapper_stops_before_provider_or_request_checkpoint(self):
        with self.assertRaisesRegex(ValueError,'Harness timeout configuration'):
            self.conversation(dict(self.config,turn_timeout_seconds=600,harness_timeout_seconds='300'),None,
                'chapters demo 15',self.route,self.api,'restricted',self.runner)
        self.api.call.assert_not_called()
        self.assertFalse(Path(self.config['state_root']).exists())
        _,handle=self.conversation(dict(self.config,turn_timeout_seconds=600,harness_timeout_seconds='900'),None,
            'chapters demo 15',self.route,self.api,'restricted',self.runner)
        self.assertTrue(handle.startswith('spapi_'))

    def test_quoted_yes_to_transcript_question_is_not_a_video_approval(self):
        import types
        import episode_routing
        import transcription_feedback
        selected=types.SimpleNamespace(reply=None,context='_unassigned',state_root=self.root/'episode-state',backend_handle=None,observe=lambda *args:None)
        @contextlib.contextmanager
        def selection(*args):yield selected
        cfg=dict(self.config,transcription_config='private-config',incoming_message=dict(text='yes',reply_to='question'),allow_timeout_only=True,turn_timeout_seconds=180,openai_key_directory=str(self.root),project_id='project')
        with patch.object(episode_routing.episodes,'read',return_value={}), patch.object(transcription_feedback,'receive',return_value={'id':'question'}), patch.object(episode_routing,'select',selection), patch.object(b.transport,'private_read',return_value='synthetic'), patch.object(b.transport,'API'), patch.object(b,'conversation',return_value=('Done','handle')) as run, patch('reviews.accept') as accept:
            b.dispatch(cfg,None,'yes',self.route)
        accept.assert_not_called()
        self.assertEqual(run.call_args.args[0]['turn_timeout_seconds'],600)

    def test_transcribe_shortcut_returns_one_brief_acknowledgement(self):
        import types, episode_routing, transcription_feedback, transcription_intake
        selected=types.SimpleNamespace(reply=None,context='demo/15',state_root=self.root/'episode-state',backend_handle=None,observe=lambda *args:None,work_root=self.root,path=self.root/'routing.json')
        @contextlib.contextmanager
        def selection(*args):yield selected
        cfg=dict(self.config,transcription_config='private-config',incoming_message=dict(text='transcribe demo 15'),allow_timeout_only=True,turn_timeout_seconds=180,transcription_wakeups=True,openai_key_directory=str(self.root),project_id='project',marmot_home=str(self.root))
        with patch.object(episode_routing.episodes,'read',return_value={'feedback_root':str(self.root/'feedback'),'episodes':{'demo/15':{'transcription':{'directory':str(self.root/'transcript')}}}}), patch.object(transcription_feedback,'receive',return_value=None),patch.object(transcription_intake,'enroll',return_value=dict(directory=str(self.root/'transcript'),task='task.json')),patch.object(episode_routing,'select',selection),patch.object(b.transport,'private_read',return_value='synthetic'),patch.object(b.transport,'API'),patch.object(b,'conversation',return_value=('Whisper running. Saved result: /private/job.json','handle')):
            b.dispatch(cfg,None,'transcribe demo 15',self.route)
        replies=[x['item']['text'] for x in self.events if x['type']=='item.completed']
        self.assertEqual(len(replies),1);self.assertIn('Started transcription for demo/15',replies[0]);self.assertNotIn('/private',replies[0])
        self.events.clear()
        with patch.object(episode_routing.episodes,'read',return_value={'episodes':{'demo/15':{'transcription':{'directory':str(self.root/'transcript')}}}}),patch.object(transcription_feedback,'receive',return_value=None),patch.object(transcription_intake,'enroll',return_value=dict(directory=str(self.root/'transcript'),task='task.json')),patch.object(episode_routing,'select',selection),patch.object(b.transport,'private_read',return_value='synthetic'),patch.object(b.transport,'API'),patch.object(b,'conversation',return_value=('Question sent','handle')),patch.object(b.transcription_notices,'waiting_question',return_value=True):
            b.dispatch(cfg,None,'transcribe demo 15',self.route)
        self.assertIn({'type':'adapter.silent'},self.events)
        self.assertFalse(any(x['type']=='item.completed' for x in self.events))

    def test_chapters_reply_requires_verified_receipt_and_uses_deterministic_count(self):
        import types, episode_routing, chapter_intake, chapters
        selected=types.SimpleNamespace(reply=None,context='demo/15',state_root=self.root/'chapter-state',backend_handle=None,observe=lambda *args:None,work_root=self.root,path=self.root/'routing.json')
        @contextlib.contextmanager
        def selection(*args):yield selected
        cfg=dict(self.config,incoming_message=dict(text='chapters demo 15'),allow_timeout_only=True,
            turn_timeout_seconds=180,openai_key_directory=str(self.root),project_id='project',marmot_home=str(self.root))
        for completion in ('Added 3 chapters to episode 15: https://example.org/episode-15',None):
            self.events.clear()
            with patch.object(chapter_intake,'enroll',return_value=dict(directory=str(self.root/'chapters'),task='task.json')),patch.object(episode_routing,'select',selection),patch.object(b.transport,'private_read',return_value='synthetic'),patch.object(b.transport,'API'),patch.object(b,'conversation',return_value=('Model claims success and includes private paths','handle')) as run,patch.object(chapters,'completion',return_value=completion),patch.object(b.failures,'save_notice',return_value='Report UUID: 12345678-1234-4234-8234-123456789abc'):
                b.dispatch(cfg,None,'chapters demo 15',self.route)
            answer=[x['item']['text'] for x in self.events if x['type']=='item.completed']
            self.assertEqual(answer,[completion or 'Report UUID: 12345678-1234-4234-8234-123456789abc'])
            self.assertIn('No manual approval step',run.call_args.args[2])
            self.assertEqual(run.call_args.args[0]['turn_timeout_seconds'],600)

    def test_unexpected_empty_answer_has_no_silent_marker(self):
        import types, episode_routing
        selected=types.SimpleNamespace(reply=None,context='_unassigned',state_root=self.root/'episode-state',backend_handle=None,observe=lambda *args:None)
        @contextlib.contextmanager
        def selection(*args):yield selected
        cfg=dict(self.config,incoming_message=dict(text='What happened?'),allow_timeout_only=True,turn_timeout_seconds=180,openai_key_directory=str(self.root),project_id='project')
        with patch.object(episode_routing,'select',selection),patch.object(b.transport,'private_read',return_value='synthetic'),patch.object(b.transport,'API'),patch.object(b,'conversation',return_value=('','handle')):
            b.dispatch(cfg,None,'What happened?',self.route)
        self.assertNotIn({'type':'adapter.silent'},self.events)

    def test_feedback_continuation_is_explicitly_silent_until_verified_or_failed(self):
        import types, episode_routing, transcription_feedback
        selected=types.SimpleNamespace(reply=None,context='_unassigned',state_root=self.root/'episode-state',backend_handle=None,observe=lambda *args:None)
        @contextlib.contextmanager
        def selection(*args):yield selected
        cfg=dict(self.config,transcription_config='private-config',incoming_message=dict(text='I said use'),allow_timeout_only=True,turn_timeout_seconds=180,transcription_wakeups=True,openai_key_directory=str(self.root),project_id='project')
        for answer in ('', 'Question sent. Saved result: /private/job.json', 'Podcast task needs attention.\nReport UUID: 12345678-1234-4234-8234-123456789abc'):
            self.events.clear()
            with patch.object(episode_routing.episodes,'read',return_value={}),patch.object(transcription_feedback,'receive',return_value={'id':'question','folder':str(self.root/'transcript')}),patch.object(episode_routing,'select',selection),patch.object(b.transport,'private_read',return_value='synthetic'),patch.object(b.transport,'API'),patch.object(b,'conversation',return_value=(answer,'handle')):
                b.dispatch(cfg,None,'I said use',self.route)
            if 'Report UUID:' in answer:
                self.assertTrue(any(x['type']=='item.completed' and 'Report UUID:' in x['item']['text'] for x in self.events))
                self.assertNotIn({'type':'adapter.silent'},self.events)
            else:
                self.assertIn({'type':'adapter.silent'},self.events)
                self.assertFalse(any(x['type']=='item.completed' for x in self.events))
            self.assertEqual(self.events[-1],{'type':'turn.completed'})

    def test_reaction_identity_is_replay_safe_and_older_than_newer_human_turn(self):
        first=dict(self.config,trusted_hex='c'*64,incoming_message=dict(message_id='1'*64,sender='c'*64,text='Task',recorded_at=1))
        _,handle=b.conversation(first,None,'Task',self.route,self.api,'restricted',self.runner)
        reaction=dict(source='connector-timeline-reaction',account='a'*64,group='b'*32,sender='c'*64,message_id='2'*64,recorded_at=2,text='👍',reply_to='3'*64)
        cfg=dict(self.config,trusted_hex='c'*64,incoming_reaction=reaction)
        answer,_=b.conversation(cfg,handle,'Reaction event',self.route,self.api,'restricted',self.runner)
        self.assertEqual(b.conversation(cfg,handle,'Reaction event',self.route,self.api,'restricted',self.runner)[0],answer)
        human=dict(first,incoming_message=dict(message_id='4'*64,sender='c'*64,text='Correction',recorded_at=3))
        b.conversation(human,handle,'Correction',self.route,self.api,'restricted',self.runner)
        with self.assertRaises(b.ReactionSuperseded):b.conversation(dict(cfg,incoming_reaction=dict(reaction,message_id='5'*64)),handle,'Stale reaction',self.route,self.api,'restricted',self.runner)
        self.assertEqual(len(self.calls),3)

    def test_job_completion_is_a_distinct_source_and_namespace(self):
        cfg=dict(self.config,operator_submission=dict(source='job-completion',id='12345678-1234-4234-8234-123456789abc',authorization_file='/private/task.json'))
        _,handle=b.conversation(cfg,None,'Completed job',self.route,self.api,'restricted',self.runner)
        state=json.loads((self.root/'state/cursors'/(handle+'.json')).read_text())
        self.assertIn('job:12345678-1234-4234-8234-123456789abc',state['requests'])
        self.assertEqual(len(self.calls),1)

    def test_nonblocking_background_turn_defers_before_any_api_call(self):
        import fcntl
        root=Path(self.config['state_root']);root.mkdir();key=hashlib.sha256(json.dumps(self.route,sort_keys=True).encode()).hexdigest()
        with (root/(key+'.lock')).open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX)
            cfg=dict(self.config,nonblocking_lock=True,incoming_message=dict(message_id='1'*64,sender='c'*64,text='task'))
            with self.assertRaises(b.ConversationBusy):b.conversation(cfg,None,'Task',self.route,self.api,'restricted',self.runner)
        self.api.call.assert_not_called()

    def test_local_operator_submission_is_distinct_from_authenticated_marmot_input(self):
        config=dict(self.config,operator_submission=dict(source='local-operator',id='12345678-1234-4234-8234-123456789abc',authorization_file='/private/task.json'))
        answer,handle=b.conversation(config,None,'Explicit operator task',self.route,self.api,'restricted',self.runner)
        self.assertEqual(b.conversation(config,handle,'Explicit operator task',self.route,self.api,'restricted',self.runner),(answer,handle))
        path=self.root/'state/cursors'/(handle+'.json');state=json.loads(path.read_text())
        request=state['requests']['operator:12345678-1234-4234-8234-123456789abc']
        self.assertEqual(request['incoming']['source'],'local-operator');self.assertNotIn('sender',request['incoming'])
        self.assertEqual(len(self.calls),1)

    def test_two_distinct_yes_messages_are_new_turns_but_replay_is_cached(self):
        config=dict(self.config,incoming_message=dict(message_id='1'*64,sender='c'*64,text='yes'))
        first,handle=b.conversation(config,None,'yes',self.route,self.api,'restricted',self.runner)
        config['incoming_message']=dict(message_id='2'*64,sender='c'*64,text='yes')
        second,_=b.conversation(config,handle,'yes',self.route,self.api,'restricted',self.runner)
        replay,_=b.conversation(config,handle,'yes',self.route,self.api,'restricted',self.runner)
        self.assertNotEqual(first,second);self.assertEqual(second,replay);self.assertEqual(len(self.calls),2)
        with self.assertRaisesRegex(RuntimeError,'different prompt'):
            b.conversation(config,handle,'changed',self.route,self.api,'restricted',self.runner)

    def api_call(self,path,body=None,submission=None):
        if '/turns?' in path:return {'data':[],'has_more':False}
        return {'id':'sess_synthetic','environment':{'workspace_directory':str(self.root)}}

    def runner(self,*args):
        self.calls.append(args)
        return 'Answer '+str(len(self.calls)),{'id':'turn_'+str(len(self.calls)),'usage':{'output_tokens':5}}

    def test_task_cost_report_includes_final_turn_and_is_replayed(self):
        def runner(api,session,body,submission,config,key,folder,baseline):
            context=json.loads(Path(config['cost_context']).read_text())
            b.task_costs.begin(context,'episode18','transcript')
            b.task_costs.finish(context,'episode18')
            self.calls.append('run')
            return 'Published',{'id':'final','usage':{'input_tokens':100,'input_tokens_details':{'cached_tokens':20},'output_tokens':10}}
        pricing=self.root/'prices.json';pricing.write_text(json.dumps({'gpt-6.1-sol':dict(input=2,cached_input=0.5,output=8)}));pricing.chmod(0o600)
        config=dict(self.config,cost_pricing=str(pricing))
        answer,handle=self.conversation(config,None,'Publish transcript',self.route,self.api,'restricted',runner)
        self.assertIn('Published',answer);self.assertIn('Estimated model cost: US$0.00.',answer)
        self.assertEqual(self.conversation(config,handle,'Publish transcript',self.route,self.api,'restricted',runner),(answer,handle))
        self.assertEqual(len(self.calls),1)
        report=json.loads((self.root/'state/task-costs/episode18.json').read_text())
        self.assertEqual(report['summary']['turns'],1);self.assertEqual(report['state'],'closed')

    def test_failed_cost_observation_does_not_lose_completed_result(self):
        def runner(api,session,body,submission,config,key,folder,baseline):
            context=json.loads(Path(config['cost_context']).read_text())
            b.task_costs.begin(context,'t','video');b.task_costs.finish(context,'t')
            return 'Rendered',{'id':'final','usage':None}
        with patch.object(b.task_costs,'observe',side_effect=ValueError('synthetic')),patch.object(b.failures,'save_notice',return_value='Failure UUID fixture'):
            answer,handle=self.conversation(self.config,None,'Render',self.route,self.api,'restricted',runner)
        self.assertEqual(answer,'Rendered\n\nFailure UUID fixture')
        state=json.loads((self.root/'state/cursors'/(handle+'.json')).read_text())
        self.assertEqual(next(iter(state['requests'].values()))['phase'],'completed')

    def test_accounting_guidance_reaches_resumed_sessions_without_an_extra_turn(self):
        _,handle=self.conversation(self.config,None,'Earlier task',self.route,self.api,'restricted',self.runner)
        pricing=self.root/'prices.json';pricing.write_text('{}');pricing.chmod(0o600)
        self.conversation(dict(self.config,cost_pricing=str(pricing)),handle,'New task',self.route,self.api,'restricted',self.runner)
        body=self.calls[-1][2]
        content=body['events'][0]['input'][0]['content']
        self.assertEqual(content[0]['text'],'New task')
        self.assertEqual(content[1]['text'],b.COST_INSTRUCTIONS)
        self.assertEqual(len(self.calls),2)
        self.assertIn('cost_context',self.calls[-1][4])

    def test_completed_request_replays_without_repeating_model_or_tools(self):
        answer,next_handle=self.conversation(self.config,None,'Do one thing',self.route,self.api,'restricted',self.runner)
        parent=self.events[0]['thread_id']
        again=self.conversation(self.config,parent,'Do one thing',self.route,self.api,'restricted',self.runner)
        self.assertEqual(again,(answer,next_handle));self.assertEqual(len(self.calls),1)

    def test_native_harness_keeps_first_session_handle_across_multiple_turns(self):
        _,handle=self.conversation(self.config,None,'First task',self.route,self.api,'restricted',self.runner)
        answer,next_handle=self.conversation(self.config,handle,'Follow up',self.route,self.api,'restricted',self.runner)
        self.assertEqual(answer,'Answer 2');self.assertEqual(next_handle,handle)
        self.assertEqual({e['thread_id'] for e in self.events if e['type']=='thread.started'},{handle})
        self.assertEqual(sum(c.args[0]=='sessions' for c in self.api.call.call_args_list),1)

    def test_exact_repeated_prompt_reuses_completed_result_even_after_followup(self):
        answer,handle=self.conversation(self.config,None,'yes',self.route,self.api,'restricted',self.runner)
        self.conversation(self.config,handle,'Different task',self.route,self.api,'restricted',self.runner)
        self.assertEqual(self.conversation(self.config,handle,'yes',self.route,self.api,'restricted',self.runner),(answer,handle))
        self.assertEqual(len(self.calls),2)

    def test_legacy_completed_cursor_upgrades_without_replaying(self):
        answer,handle=self.conversation(self.config,None,'First task',self.route,self.api,'restricted',self.runner)
        path=self.root/'state/cursors'/(handle+'.json')
        state=json.loads(path.read_text());state['request']=next(iter(state.pop('requests').values()))
        b.transport.save(path,state)
        self.assertEqual(self.conversation(self.config,handle,'First task',self.route,self.api,'restricted',self.runner),(answer,handle))
        self.assertEqual(self.conversation(self.config,handle,'Follow up',self.route,self.api,'restricted',self.runner)[0],'Answer 2')
        self.assertEqual(len(self.calls),2)

    def test_uncertain_outcome_blocks_new_work_and_preserves_input(self):
        def failure(*args):raise RuntimeError('Synthetic lost response')
        with self.assertRaisesRegex(RuntimeError,'lost response'):
            self.conversation(self.config,None,'Perform an authorized action',self.route,self.api,'restricted',failure)
        with self.assertRaisesRegex(RuntimeError,'unresolved'):
            self.conversation(self.config,self.events[0]['thread_id'],'retry',self.route,self.api,'restricted',self.runner)
        self.assertFalse(self.calls)
        inputs=list((self.root/'state').glob('turn-*/input.json'))
        self.assertEqual(len(inputs),1)
        self.assertIn('Perform an authorized action',inputs[0].read_text())

    def test_lost_session_creation_response_blocks_another_creation(self):
        def lost(path,*args):
            if path=='sessions':raise RuntimeError('Synthetic lost create response')
            return self.api_call(path,*args)
        self.api.call.side_effect=lost
        with self.assertRaisesRegex(RuntimeError,'lost create'):
            self.conversation(self.config,None,'First task',self.route,self.api,'restricted',self.runner)
        with self.assertRaisesRegex(RuntimeError,'unresolved'):
            self.conversation(self.config,None,'First task',self.route,self.api,'restricted',self.runner)
        self.assertEqual(sum(c.args[0]=='sessions' for c in self.api.call.call_args_list),1)

    def test_missing_resumed_handle_never_starts_another_session(self):
        with self.assertRaisesRegex(RuntimeError,'handle is missing'):
            self.conversation(self.config,'spapi_'+'0'*32,'Follow up',self.route,self.api,'restricted',self.runner)
        self.api.call.assert_not_called()

    def test_cursor_cannot_cross_groups(self):
        _,handle=self.conversation(self.config,None,'hello',self.route,self.api,'restricted',self.runner)
        other=dict(self.route,group='c'*32)
        with self.assertRaisesRegex(RuntimeError,'another conversation'):
            self.conversation(self.config,handle,'hello',other,self.api,'restricted',self.runner)
        self.assertEqual(len(self.calls),1)

    def test_executor_does_not_inherit_application_key_agent_or_bearer_token(self):
        with patch.object(b.Path,'home',return_value=self.root),patch.dict(os.environ,{
                'OPENAI_API_KEY':'application-secret','SSH_AUTH_SOCK':'shared-agent',
                'MARMOT_AGENT_AUTH_TOKEN':'control-secret'}):
            env=b.executor_environment({},'restricted-key')
        self.assertEqual(env['CODEX_API_KEY'],'restricted-key')
        self.assertFalse({'OPENAI_API_KEY','SSH_AUTH_SOCK','MARMOT_AGENT_AUTH_TOKEN'}&env.keys())
        self.assertNotIn('application-secret',json.dumps(env))

    def test_local_help_list_and_status_need_no_keys_even_when_model_spending_disabled(self):
        config=dict(self.config,allow_timeout_only=False,turn_timeout_seconds=-1,work_root=str(self.root/'work'))
        path=self.root/'instance.json';b.transport.save(path,config)
        original=b.transport.private_read
        def read_only_config(p):
            self.assertEqual(Path(p),path)
            return original(p)
        cases=[('help','Podcast commands'),('podcast help','Podcast commands'),
               ('episodes','No episode projects'),('podcast episodes','No episode projects'),
               ('podcast status','No episode selected')]
        for prompt,expected in cases:
            with self.subTest(prompt=prompt):
                self.events.clear()
                with patch.dict(os.environ,{'SP_MARMOT_INSTANCE':str(path),'MARMOT_ACCOUNT_ID_HEX':'a'*64,'MARMOT_GROUP_ID_HEX':'b'*32}),patch.object(b.sys,'argv',['backend','exec','--json','-']),patch.object(b.sys,'stdin',io.StringIO(prompt)),patch.object(b.Path,'cwd',return_value=self.root),patch.object(b.signal,'signal'),patch.object(b.transport,'private_read',side_effect=read_only_config),patch.object(b.transport,'API') as api:
                    b.main();api.assert_not_called()
                self.assertTrue(any(expected in x.get('item',{}).get('text','') for x in self.events))

    def test_inbox_deduplicates_delivery_but_accepts_another_identical_reply(self):
        config=dict(self.config,allow_timeout_only=False)
        path=self.root/'instance.json';b.transport.save(path,config)
        incoming=dict(account='a'*64,group='b'*32,sender='c'*64,message_id='d'*64,text='yes',recorded_at=1,reply_to=None)
        env={'SP_MARMOT_INSTANCE':str(path),'MARMOT_ACCOUNT_ID_HEX':'a'*64,'MARMOT_GROUP_ID_HEX':'b'*32}
        def dispatched(*args):b.emit({'type':'turn.completed'})
        with patch.dict(os.environ,env),patch.object(b.sys,'argv',['backend','exec','--json','-']),patch.object(b.Path,'cwd',return_value=self.root),patch.object(b.signal,'signal'),patch.object(b.messages,'authenticated',side_effect=lambda *a:dict(incoming)),patch.object(b,'dispatch',side_effect=dispatched) as dispatch:
            for identifier in ('d'*64,'d'*64,'e'*64):
                incoming['message_id']=identifier
                with patch.object(b.sys,'stdin',io.StringIO('yes')):b.main()
            self.assertEqual(dispatch.call_count,2)
            self.assertEqual(len(list((self.root/'state/inbox').glob('*.json'))),2)

    def test_model_task_still_requires_enabled_spending_policy(self):
        config=dict(self.config,allow_timeout_only=False,turn_timeout_seconds=180,work_root=str(self.root/'work'))
        path=self.root/'instance.json';b.transport.save(path,config)
        with patch.dict(os.environ,{'SP_MARMOT_INSTANCE':str(path),'MARMOT_ACCOUNT_ID_HEX':'a'*64,'MARMOT_GROUP_ID_HEX':'b'*32}),patch.object(b.sys,'argv',['backend','exec','--json','-']),patch.object(b.sys,'stdin',io.StringIO('Prepare slides')),patch.object(b.Path,'cwd',return_value=self.root),patch.object(b.signal,'signal'),patch.object(b.transport,'API') as api:
            with self.assertRaisesRegex(RuntimeError,'spending-limit policy'):b.main()
            api.assert_not_called()

    def test_bypass_flags_and_cross_account_route_are_refused(self):
        with self.assertRaises(RuntimeError):b.arguments(['exec','--dangerously-bypass-approvals-and-sandbox','--json','-'])
        with self.assertRaises(RuntimeError):b.binding(self.config,{'MARMOT_ACCOUNT_ID_HEX':'c'*64,'MARMOT_GROUP_ID_HEX':'b'*32},self.root)


if __name__=='__main__':unittest.main()
