#!/usr/bin/env python3
"""Token-free local watcher for transcript job completions and trusted question reactions."""
import argparse
from datetime import datetime
import fcntl
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('wakeup_backend',HERE/'marmot-backend.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
import episodes as e
import transcription_feedback as feedback
import failures
import transcription_notices

KINDS={'transcript-analyze','transcript-recognize','transcript-speakers'}
TERMINAL={'delivered','suppressed','blocked'}

def published(folder):
    path=folder/'publication/verification.json'
    return path.exists() and e.read(path).get('verified') is True

def message(config,identifier):
    control=feedback.control();control.MARMOT_DIR=Path(config['marmot_home'])
    result=control.rpc(str(control.MARMOT_DIR/'dev/wn-agent.sock'),dict(type='timeline_message_get',account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],message_id_hex=identifier),30)
    if result.get('type')!='timeline_message' or any(result.get(k)!=v for k,v in [('account_id_hex',config['account_id_hex']),('group_id_hex',config['group_id_hex']),('message_id_hex',identifier)]):raise ValueError('Question timeline route mismatch')
    item=result.get('message') or {}
    if item.get('message_id_hex')!=identifier or item.get('reactions_truncated'):raise ValueError('Incomplete question reaction evidence')
    return item

def send(config,path,text):
    manifest=path.with_suffix('.send.json')
    value=dict(account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],text=text,idempotency_key='transcript-wakeup-'+path.stem)
    if manifest.exists():
        if e.read(manifest)!=value:raise ValueError('Notification intent changed; inspect its receipt')
    else:e.save(manifest,value)
    raw=subprocess.check_output([sys.executable,str(HERE.parents[1]/'skills/marmot-whitenoise/scripts/wn_control.py'),'--home',config['marmot_home'],'--send-text',str(manifest)],stderr=subprocess.DEVNULL)
    e.save(path.with_suffix('.send-receipt.json'),json.loads(raw))

def context(instance,config,item):
    matches=[]
    for path in (Path(instance['state_root'])/'routing').glob('*.json'):
        record=e.read(path);route=record['binding']
        if route['account']==config['account_id_hex'] and route['group']==config['group_id_hex'] and e.key(item['show'],item['episode']) in record['contexts']:matches.append(record)
    if len(matches)!=1:raise ValueError('Cannot uniquely locate the original episode context')
    record=matches[0];route=record['binding'];name=e.key(item['show'],item['episode']);entry=record['contexts'][name]
    # Routing uses json.dumps(sort_keys=True), not the journal's compact digest.
    expected=Path(instance['state_root'])/'episode-contexts'/__import__('hashlib').sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()/__import__('hashlib').sha256(name.encode()).hexdigest()
    if not entry.get('handle') or Path(entry.get('state_root','')).resolve()!=expected.resolve():raise ValueError('Original episode session is missing or moved')
    cursor=e.read(expected/'cursors'/(entry['handle']+'.json'))
    if cursor['binding']!=route or not cursor.get('session_id'):raise ValueError('Original session binding differs')
    return route,expected,entry['handle']

def invoke(instance,config,state):
    route=state['route'];root=Path(state['state_root']);handle=state['handle'];cursor=e.read(root/'cursors'/(handle+'.json'))
    if cursor['binding']!=route or route['account']!=config['account_id_hex'] or route['group']!=config['group_id_hex'] or not Path(route['cwd']).resolve().is_relative_to(Path(instance['workspace_root']).resolve()):raise ValueError('Wake-up session route changed')
    for event in state['events']:
        if state['kind']=='job':
            job=e.read(event['path'])
            if job['nonce']!=event['nonce'] or job['request_sha256']!=event['request_sha256'] or e.digest(job['request'])!=event['request_sha256'] or job['state']!='completed' or job.get('exit_code')!=0:raise ValueError('Completed job evidence changed')
    prior=cursor['requests'].get(state['request_key'])
    if prior:
        if prior['phase']=='completed':return prior['answer']
        raise RuntimeError('Earlier wake-up has an uncertain outcome; inspect before continuing')
    scoped=dict(instance,state_root=str(root),nonblocking_lock=True,turn_timeout_seconds=instance.get('transcription_turn_timeout_seconds',600))
    if state['kind']=='reaction':scoped['incoming_reaction']=state['events'][0]['reply']
    else:scoped['operator_submission']=dict(source='job-completion',id=state['submission'],authorization_file=state['task'])
    if instance.get('allow_timeout_only') is not True or not 30<=scoped['turn_timeout_seconds']<=600:raise ValueError('No accepted active-turn timeout policy')
    for key,value in [('MARMOT_ACCOUNT_ID_HEX',route['account']),('MARMOT_GROUP_ID_HEX',route['group']),('MARMOT_AGENT_SOCKET',str(Path(config['marmot_home'])/'dev/wn-agent.sock'))]:os.environ[key]=value
    # A background event is not a newly received text message.
    for key in ('MARMOT_MESSAGE_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX'):os.environ.pop(key,None)
    scoped,api,restricted=b.model_client(scoped)
    b.emit=lambda _:None
    answer,result=b.conversation(scoped,handle,state['prompt'],route,api,restricted,emit_event=lambda _:None)
    if result!=handle:raise RuntimeError('Unexpected replacement session; inspect saved effects')
    return answer

def scan(instance,config,fetch=message,assigned=None,blocked=None):
    assigned=assigned or set();blocked=blocked or set()
    work=Path(instance['work_root']);journal=work/'episodes.json'
    if not journal.exists():return {}
    items=e.read(journal)['episodes'];found={};questions=[]
    feedback_root=Path(config['feedback_root'])
    for path in feedback_root.glob('*.json'):
        q=e.read(path)
        if q['account']!=config['account_id_hex'] or q['group']!=config['group_id_hex'] or q['trusted_sender']!=config['trusted_hex'] or published(Path(q['folder'])):continue
        if q['state'] in feedback.OPEN_STATES:
            for identifier in q.get('message_ids',[]):
                current=fetch(config,identifier)
                for reaction in current.get('reactions',[]):feedback.receive_reaction(config,current,reaction)
            q=e.read(path)
        q['_path']=str(path);questions.append(q)
    for name,item in items.items():
        registration=item.get('transcription')
        if not registration:continue
        folder=Path(registration['directory'])
        if published(folder) or str(folder) in blocked:continue
        episode=e.read(folder/'episode.json') if (folder/'episode.json').exists() else None
        if not episode or episode['guid'] not in config['episodes']:continue
        task=e.read(registration['task'])
        if task.get('source')!='explicit-user-task' or task.get('operation')!='transcript' or task.get('episode_guid')!=episode['guid'] or task.get('directory')!=str(folder) or task.get('show')!=item['show'] or task.get('episode')!=item['episode']:raise ValueError('Job task authorization or episode differs')
        if config['episodes'][episode['guid']]['final_audio_sha256']!=episode['final_audio_sha256']:raise ValueError('Authorized source hash changed')
        relevant=[q for q in questions if q['episode_guid']==episode['guid'] and Path(q['folder']).resolve()==folder.resolve()]
        reactions=[]
        for q in relevant:
            reply=q.get('reply',{})
            if q['state']=='answered' and reply.get('source')=='connector-timeline-reaction' and 'reaction:'+reply['message_id'] not in assigned:
                reactions.append(dict(id='reaction:'+reply['message_id'],reply=reply,question=q['_path'],question_id=q['id'],target=reply['reply_to']))
        if reactions:found[name]=dict(item=item,folder=str(folder),kind='reaction',events=reactions[:1]);continue
        if any(q['state'] in feedback.UNRESOLVED_STATES for q in relevant):continue
        roots=[work/'jobs',Path(item['directory'])/'jobs',folder/'jobs']+[Path(x) for x in instance.get('transcription_job_roots',[])]
        events=[];seen=set();outstanding=False
        for root in roots:
            for path in root.glob('*/job.json'):
                if path.resolve() in seen:continue
                seen.add(path.resolve());job=e.read(path);request=job.get('request',{});params=request.get('parameters',{})
                if request.get('kind') not in KINDS or params.get('folder')!=str(folder) or Path(params.get('config','')).resolve()!=Path(instance['transcription_config']).resolve():continue
                if job['state'] in ('queued','running'):outstanding=True
                if job['state']=='completed' and job.get('exit_code')==0 and e.digest(request)==job['request_sha256']:
                    events.append(dict(id='job:'+e.digest({'path':str(path),'nonce':job['nonce'],'request':job['request_sha256']}),path=str(path),nonce=job['nonce'],request_sha256=job['request_sha256'],kind=request['kind']))
        if events and not outstanding:found[name]=dict(item=item,folder=str(folder),kind='job',events=events)
    return found

def run_once(instance,fetch=message,run=invoke,deliver=send):
    config=e.read(instance['transcription_config'])
    if config.get('paused') is not False:return dict(paused=True)
    root=e.private_root(Path(instance['state_root'])/'wakeups')
    with (root/'.watch.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(busy=True)
        paths=[p for p in root.glob('batch-*.json') if re.fullmatch(r'batch-[0-9a-f]{64}\.json',p.name)];states={p:e.read(p) for p in paths};assigned={event['id'] for state in states.values() for event in state['events']}
        for name,candidate in scan(instance,config,fetch,assigned,{s['folder'] for s in states.values() if s['phase']=='blocked'}).items():
            events=[x for x in candidate['events'] if x['id'] not in assigned]
            if not events:continue
            item=candidate['item'];route,api_root,handle=context(instance,config,item);identifier=e.digest(dict(episode=name,handle=handle,events=events));submission=str(uuid.uuid5(uuid.NAMESPACE_URL,'sovereign-podcaster-wakeup:'+identifier));path=root/('batch-'+identifier+'.json')
            prompt=('Continue the existing user-authorized transcript task '+item['transcription']['task']+'. This is a verified local '+('trusted thumbs-up on the exact saved feedback question' if candidate['kind']=='reaction' else 'background-job completion')+' event, not a new text message or new publication grant. Evidence: '+json.dumps(events)+'. This task is already registered: do not re-enroll it or require fresh text-message metadata for this background event. Read current task/review/feedback/job state and reuse completed outputs. Continue local transcript review and the already requested native attachment/verification; preserve audio and unrelated fields. Do not repeat an answered question or a completed upload. Background recognition/review jobs now wake this session automatically: return while waiting and do not ask the user to send continue or spend model calls polling. Ask focused voice questions only if human input is actually needed. If already published, verify/report instead of attaching again. Never start another episode. Use docs/transcription.md and the bounded review tools. A thumbs-up on a transcript question is not video publication approval.')
            state=dict(phase='queued',episode=name,kind=candidate['kind'],events=events,route=route,state_root=str(api_root),handle=handle,folder=candidate['folder'],task=item['transcription']['task'],submission=submission,request_key=('reaction:'+events[0]['reply']['message_id']) if candidate['kind']=='reaction' else 'job:'+submission,prompt=prompt,created_at=e.now())
            e.save(path,state);states[path]=state;assigned.update(x['id'] for x in events)
        completed=0
        for path,state in states.items():
            if state['phase'] in TERMINAL:continue
            try:
                cursor=e.read(Path(state['state_root'])/'cursors'/(state['handle']+'.json'));prior=cursor['requests'].get(state['request_key'])
                if prior and prior['phase']=='completed' and state['phase']!='model-completed':state.update(phase='model-completed',answer=prior['answer']);e.save(path,state)
                if published(Path(state['folder'])) and state['phase']=='queued':state.update(phase='suppressed',reason='already-published');e.save(path,state);continue
                if state['phase']!='model-completed':
                    # Revalidate a queued reaction from the connector before inference.
                    if state['kind']=='reaction' and not prior:
                        event=state['events'][0];current=fetch(config,event['target'])
                        if not any(x.get('reaction_message_id_hex')==event['reply']['message_id'] and x.get('actor',{}).get('account_id_hex')==config['trusted_hex'] and x.get('emoji')==event['reply']['text'] for x in current.get('reactions',[])):
                            question_path=Path(event['question'])
                            with question_path.with_suffix('.lock').open('a') as question_lock:
                                fcntl.flock(question_lock,fcntl.LOCK_EX);q=e.read(question_path)
                                if q.get('reply',{}).get('message_id')==event['reply']['message_id']:
                                    q.setdefault('withdrawn_replies',[]).append(q.pop('reply'));q['state']=q.pop('reaction_previous_state','waiting')
                                    previous=q.pop('reaction_previous_reply',None);received=q.pop('reaction_previous_received_at',None)
                                    if previous is not None:q['reply']=previous
                                    if received is not None:q['received_at']=received
                                    else:q.pop('received_at',None)
                                    e.save(question_path,q)
                            state.update(phase='suppressed',reason='reaction-withdrawn');e.save(path,state);continue
                    state['phase']='running';e.save(path,state);answer=run(instance,config,state);state.update(phase='model-completed',answer=answer);e.save(path,state)
                # Model summaries are durable evidence, not automatically chat notices.
                # Never change an already prepared/uncertain send during recovery.
                reply=transcription_notices.result(state['folder'],state['answer'])
                if reply is None and not path.with_suffix('.send.json').exists():
                    state.update(phase='suppressed',reason='internal-transcript-stage',finished_at=e.now());e.save(path,state);continue
                text=e.read(path.with_suffix('.send.json'))['text'] if path.with_suffix('.send.json').exists() else 'Transcript '+state['episode']+'\n'+reply
                deliver(config,path,text);state.update(phase='delivered',finished_at=e.now());e.save(path,state);completed+=1
            except b.ConversationBusy:state['phase']='queued';e.save(path,state)
            except b.ReactionSuperseded:state.update(phase='suppressed',reason='newer-human-turn');e.save(path,state)
            except Exception as error:
                report=failures.from_exception(error,'controller');notice=failures.save_notice(report);state.update(phase='blocked',failure_uuid=report['id']);e.save(path,state)
                try:deliver(config,path.with_name(path.stem+'-failure.json'),notice)
                except Exception:pass
        return dict(delivered=completed)

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--instance',type=Path,required=True);p.add_argument('--once',action='store_true');p.add_argument('--interval',type=float,default=5)
    a=p.parse_args()
    if not 1<=a.interval<=60:p.error('interval must be between1 and60 seconds')
    while True:
        try:
            instance=e.read(a.instance);result=run_once(instance)
            import video_tasks
            video_tasks.run_once(instance)
            if a.once:print(json.dumps(result));return
        except Exception as error:
            # No raw exception, account/group ids, payload or provider output in service logs.
            if a.once:raise
            try:
                config=e.read(instance['transcription_config']);root=e.private_root(Path(instance['state_root'])/'wakeups');report=failures.from_exception(error,'controller');signature=e.digest({k:report.get(k) for k in ('code','exception_type','frames')});path=root/('controller-fault-'+signature+'.json')
                if not path.exists():
                    failures.persist(report,path);notice=failures.format_notice(report);print(notice,flush=True)
                    try:send(config,path,notice)
                    except Exception:pass
            except Exception:pass
        time.sleep(a.interval)
if __name__=='__main__':failures.cli(main,'controller')
