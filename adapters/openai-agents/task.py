#!/usr/bin/env python3
"""Trusted local operator submits a task to an existing paired episode context; never forges a Marmot message."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('backend',HERE/'marmot-backend.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
import episode_routing
import episodes as e


def paired_route(config,transcription,records):
    matches=[x for x in records if x['binding']['account']==config['account_id_hex'] and x['binding']['group']==transcription['group_id_hex']]
    if len(matches)!=1:raise ValueError('Exactly one explicitly paired account/group binding is required')
    record=matches[0]
    if not Path(record['binding']['cwd']).resolve().is_relative_to(Path(config['workspace_root']).resolve()):raise ValueError('Paired workspace is outside the configured isolated account')
    return record

def usage_summary(turns):
    unique={turn['id']:turn for turn in turns if not turn.get('subagent_id')}
    totals=dict(input_tokens=0,cached_input_tokens=0,output_tokens=0,total_tokens=0)
    missing=[]
    for identifier,turn in unique.items():
        usage=turn.get('usage')
        if usage is None:missing.append(identifier);continue
        for key in ('input_tokens','output_tokens','total_tokens'):totals[key]+=usage.get(key,0)
        totals['cached_input_tokens']+=usage.get('input_tokens_details',{}).get('cached_tokens',0)
    return dict(turns=len(unique),tokens=totals,missing_usage_turn_ids=missing,complete=not missing,billed_cost=None)


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['submit','status','log','usage']);p.add_argument('--instance',type=Path,required=True);p.add_argument('--task',type=Path,required=True);p.add_argument('--submission',required=True);p.add_argument('--prompt',type=Path)
    args=p.parse_args();identifier=str(uuid.UUID(args.submission))
    if identifier!=args.submission:raise ValueError('Use a canonical submission UUID')
    config=b.read(args.instance);task=b.read(args.task)
    transcription=e.read(config['transcription_config'])
    allowed=transcription['episodes'].get(task['episode_guid'])
    if task['source']!='explicit-user-task' or task['operation']!='transcript' or transcription.get('paused') is not False or task['show']!=transcription['show'] or not allowed or allowed['number']!=task['episode']:raise ValueError('Task lacks the explicitly authorized episode scope')
    root=e.private_root(Path(task['directory'])/'controller');receipt=root/(identifier+'.json')
    if args.action!='submit':
        state=b.read(receipt)
        if args.action=='log':
            print(json.dumps(e.read(Path(state['turn_directory'])/'items.json'),indent=2))
        elif args.action=='usage':
            _,api,_=b.model_client(dict(config,state_root=str(Path(state['turn_directory']).parent)))
            turns=b.paged(api,'sessions/'+state['session_id']+'/turns')
            summary=usage_summary(turns)
            report=dict(observed_at=e.now(),session_id=state['session_id'],summary=summary,turns=turns)
            e.save(root/'usage-observed.json',report);print(json.dumps(summary,indent=2))
        else:print(json.dumps(state,indent=2))
        return
    if not args.prompt:raise ValueError('An explicit private prompt file is required')
    prompt=b.transport.private_read(args.prompt);binding=dict(task=e.file_record(args.task),prompt=e.file_record(args.prompt),submission=identifier)
    if receipt.exists():
        old=b.read(receipt)
        if old['binding']!=binding:raise ValueError('Submission UUID belongs to different task/prompt')
        if old['phase']=='completed':print(old['answer']);return
        raise ValueError('Earlier local submission is unresolved; inspect its session, do not resubmit')
    routes=[e.read(path) for path in (Path(config['state_root'])/'routing').glob('*.json')]
    record=paired_route(config,transcription,routes);route=record['binding']
    for name,value in [('MARMOT_ACCOUNT_ID_HEX',route['account']),('MARMOT_GROUP_ID_HEX',route['group']),('MARMOT_AGENT_SOCKET',str(Path(config['marmot_home'])/'dev/wn-agent.sock'))]:os.environ[name]=value
    show=task['show'];number=task['episode']
    with e.journal(Path(config['work_root'])) as (_,data):exists=e.key(show,number) in data['episodes']
    with episode_routing.select(config,record['public_handle'],f'podcast {"use" if exists else "new"} {show} {number}',route):pass
    with e.journal(Path(config['work_root'])) as (_,data):
        data['episodes'][e.key(show,number)]['transcription']={'directory':task['directory'],'task':str(args.task)}
    with episode_routing.select(config,record['public_handle'],'',route) as selected:
        state=dict(binding=binding,phase='pending',created_at=e.now(),task=str(args.task));e.save(receipt,state)
        instructions=('Authorized task: transcribe and publish only the selected existing episode. '+
            'Read the private task file '+str(args.task)+' and docs/transcription.md. This is transcript production, not video publication. '+
            'Existing user authorization covers native transcript attachment after actual wording/speaker/timebase review. Do not modify audio, notes, GUID, pubDate or other media. '+
            'For required samples use tools/transcription_feedback.py: one voice memo followed by its text question. Save and honor actual feedback/deadlines. '+
            'Long recognition is a deterministic background process; return when waiting rather than spending tokens polling it. '
            'After sending a feedback question, finish this turn immediately with a waiting checkpoint; the human reply will start a new turn. '+
            'Use the configured local Whisper runtime, never an OpenAI transcription service. Read compact review packets rather than giant project histories. '+
            'If blocked, store a failure report and return only its UUID notice. Keep API keys/SSH secrets out of prompts and tool output.')
        scoped=dict(config,state_root=str(selected.state_root),turn_timeout_seconds=600,operator_submission=dict(source='local-operator',id=identifier,authorization_file=str(args.task)),episode_instructions=instructions)
        scoped,api,restricted=b.model_client(scoped)
        def observe(event):
            selected.observe(event,lambda _:None)
            if event.get('type')=='thread.started':state['handle']=event['thread_id'];e.save(receipt,state)
        if config.get('allow_timeout_only') is not True:raise ValueError('No accepted spending-limit policy')
        b.emit=lambda _:None
        answer,handle=b.conversation(scoped,selected.backend_handle,prompt,route,api,restricted,emit_event=observe)
        cursor=e.read(selected.state_root/'cursors'/(handle+'.json'));request=cursor['requests']['operator:'+identifier]
        state.update(phase='completed',answer=answer,session_id=cursor['session_id'],turn_directory=request['folder'],usage=request.get('usage'),finished_at=e.now());e.save(receipt,state)
        print(answer)
if __name__=='__main__':
    try:main()
    except Exception as error:
        import failures
        print(failures.save_notice(failures.from_exception(error,'controller')),file=sys.stderr);raise SystemExit(1) from None
