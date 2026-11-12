"""Standalone PPQ integration invariants; no network or production inputs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import urllib.error

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[1]/'tools'))
import providers
import episodes as e
spec=importlib.util.spec_from_file_location('ppq_test_backend',HERE/'marmot-backend.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class PPQTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=dict(state_root=str(self.root/'state'),work_root=str(self.root/'work'),workspace_root=str(self.root),repository=str(self.root),current_workspace=str(self.root),
            model='gpt-6.1-sol',reasoning_effort='high',provider='ppq',ppq_base_url='https://api.ppq.ai/v1',turn_timeout_seconds=30)
        self.route=dict(account='a'*64,group='b'*32,cwd=str(self.root))
        self.usage=dict(prompt_tokens=10,completion_tokens=5,total_tokens=15,prompt_tokens_details=dict(cached_tokens=2))
    def response(self,message,reason='stop'):
        return dict(choices=[dict(message=message,finish_reason=reason)],usage=self.usage)
    def test_settings_reject_world_readable_secrets_and_foreign_endpoints(self):
        settings=self.root/'llm.json';key=self.root/'api.key';key.write_text('fixture-secret');key.chmod(0o600)
        value=dict(provider='ppq',model='gpt-6.1-sol',reasoning_effort='high',api_key_file=str(key))
        e.save(settings,value)
        config=dict(self.cfg,llm_config=str(settings),cost_pricing='openai-prices')
        selected,api,restricted=b.model_client(config)
        self.assertIsInstance(api,providers.PPQ);self.assertEqual(restricted,'');self.assertEqual(selected['reasoning_effort'],'high');self.assertIsNone(selected['cost_pricing'])
        settings.chmod(0o644)
        with self.assertRaises(RuntimeError):b.model_client(config)
        e.save(settings,dict(value,base_url='https://other.example/v1'))
        with self.assertRaises(ValueError):b.model_client(config)
        e.save(settings,value);key.chmod(0o644)
        with self.assertRaises(RuntimeError):b.model_client(config)
    def test_missing_explicit_settings_fails_and_legacy_default_keeps_codex(self):
        with self.assertRaises(ValueError):providers.settings(dict(self.cfg,llm_config=str(self.root/'missing')),b.read)
        with patch.object(Path,'home',return_value=self.root):self.assertEqual(providers.settings(self.cfg,b.read)['provider'],'codex')
    def test_ppq_tool_loop_resumes_and_replayed_input_does_not_repeat_effects(self):
        api=providers.PPQ(self.cfg,'fixture-secret')
        call=dict(id='call_fixture',type='function',function=dict(name='exec_command',arguments=json.dumps(dict(command='printf fixture > result.txt'))))
        api.complete=Mock(side_effect=[self.response(dict(role='assistant',content=None,tool_calls=[call]),'tool_calls'),self.response(dict(role='assistant',content='Ready for review.')),self.response(dict(role='assistant',content='Resumed.'))])
        cfg=dict(self.cfg,incoming_message=dict(message_id='d'*64,sender='c'*64,text='Make a fixture'))
        answer,handle=b.conversation(cfg,None,'Make a fixture',self.route,api,'',emit_event=lambda _:None)
        self.assertEqual(answer,'Ready for review.');self.assertEqual((self.root/'result.txt').read_text(),'fixture')
        answer2,_=b.conversation(cfg,handle,'Make a fixture',self.route,api,'',emit_event=lambda _:None)
        self.assertEqual(answer2,answer);self.assertEqual(api.complete.call_count,2)
        cfg['incoming_message']=dict(message_id='e'*64,sender='c'*64,text='Continue')
        b.conversation(cfg,handle,'Continue',self.route,api,'',emit_event=lambda _:None)
        request=api.complete.call_args.args[0]
        self.assertEqual(request['model'],'gpt-6.1-sol');self.assertEqual(request['reasoning_effort'],'high')
        self.assertTrue(any(m['role']=='tool' for m in request['messages']))
        cursor=e.read(Path(self.cfg['state_root'])/'cursors'/(handle+'.json'))
        self.assertEqual(cursor['provider'],'ppq');self.assertTrue(cursor['session_id'].startswith('ppq_'))
        self.assertEqual(cursor['requests']['c'*64+':'+'d'*64]['usage']['input_tokens'],20)
    def test_failed_request_stays_unresolved_and_is_never_automatically_replayed(self):
        api=providers.PPQ(self.cfg,'fixture-secret');api.complete=Mock(side_effect=RuntimeError('fixture failure'))
        cfg=dict(self.cfg,incoming_message=dict(message_id='d'*64,sender='c'*64,text='Fixture'))
        with self.assertRaises(RuntimeError):b.conversation(cfg,None,'Fixture',self.route,api,'',emit_event=lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'unresolved'):b.conversation(cfg,None,'Fixture',self.route,api,'',emit_event=lambda _:None)
        self.assertEqual(api.complete.call_count,1)
        self.assertEqual(len(list(Path(self.cfg['state_root']).glob('*.active.json'))),1)
    def test_http_failure_is_not_retried_or_exposed(self):
        api=providers.PPQ(self.cfg,'fixture-secret');api.opener=Mock()
        api.opener.open.side_effect=urllib.error.HTTPError('https://api.ppq.ai',402,'private body',{},None)
        folder=e.private_root(self.root/'turn')
        with self.assertRaisesRegex(RuntimeError,'PPQ request failed'):api.complete(dict(model='fixture'),folder,0,10)
        with self.assertRaisesRegex(RuntimeError,'already attempted'):api.complete(dict(model='fixture'),folder,0,10)
        self.assertEqual(api.opener.open.call_count,1)
        request=api.opener.open.call_args.args[0];self.assertEqual(request.get_header('Authorization'),'Bearer fixture-secret')
        self.assertNotIn('private body',json.dumps(e.read(folder/'inference-000-failure.json')))
    def test_shell_tools_do_not_inherit_provider_or_operator_secrets(self):
        api=providers.PPQ(self.cfg,'fixture-secret');folder=e.private_root(self.root/'turn')
        call=dict(id='env',function=dict(name='exec_command',arguments=json.dumps(dict(command='test -z "${PPQ_API_KEY-}" && test -z "${OPENAI_API_KEY-}" && test -z "${PRIVATE_OPERATOR_SECRET-}"'))))
        with patch.dict(os.environ,dict(PPQ_API_KEY='fixture-secret',OPENAI_API_KEY='fixture-other',PRIVATE_OPERATOR_SECRET='fixture-private')):
            result,_=api.tool(call,self.cfg,folder,0,10)
        self.assertEqual(result['exit_code'],0)
        call['function']['arguments']=json.dumps(dict(command='pwd',cwd='/'))
        with self.assertRaises(ValueError):api.tool(call,self.cfg,folder,1,10)
    def test_missing_usage_is_reported_unknown(self):
        self.assertIsNone(providers.usage([None]));self.assertIsNone(providers.usage([dict(prompt_tokens=1)]))

    def test_switching_provider_preserves_original_codex_session(self):
        handle='spapi_'+'1'*32;root=e.private_root(Path(self.cfg['state_root']));e.private_root(root/'cursors')
        e.save(root/'cursors'/(handle+'.json'),dict(binding=self.route,handle=handle,requests={},session_id='agent_original'))
        api=providers.PPQ(self.cfg,'fixture-secret');api.complete=Mock(return_value=self.response(dict(role='assistant',content='PPQ fixture.')))
        cfg=dict(self.cfg,incoming_message=dict(message_id='d'*64,sender='c'*64,text='Use PPQ'))
        b.conversation(cfg,handle,'Use PPQ',self.route,api,'',emit_event=lambda _:None)
        cursor=e.read(root/'cursors'/(handle+'.json'));ppq_id=cursor['session_id']
        self.assertEqual(cursor['provider_sessions']['codex'],'agent_original')
        original=Mock();original.call.side_effect=lambda path,*a:dict(id='agent_original')
        cfg.update(provider='codex',incoming_message=dict(message_id='e'*64,sender='c'*64,text='Use Codex'))
        with patch.object(b,'paged',return_value=[]):
            b.conversation(cfg,handle,'Use Codex',self.route,original,'fixture',runner=lambda *a:('Codex fixture.',dict(id='original-turn',usage=None)),emit_event=lambda _:None)
        original.call.assert_called_once_with('sessions/agent_original')
        cursor=e.read(root/'cursors'/(handle+'.json'));self.assertEqual(cursor['provider_sessions']['ppq'],ppq_id);self.assertEqual(cursor['session_id'],'agent_original')

if __name__=='__main__':unittest.main()
