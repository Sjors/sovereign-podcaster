#!/usr/bin/env python3
"""One encrypted voice sample + one registered question; authenticate replies without model polling."""
import argparse
import fcntl
from datetime import datetime,timedelta,timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import episodes as e
import failures
ROOT=Path(__file__).resolve().parents[1]
OPEN_STATES={'waiting','reply-received','provisional'}
UNRESOLVED_STATES={'sending','waiting','reply-received'}

def replies(question):
    return question.get('reply_history',[])+([question['reply']] if question.get('reply') else [])

def remember_reply(question):
    reply=question.get('reply')
    if reply and reply not in question.get('reply_history',[]):
        question.setdefault('reply_history',[]).append(reply)

def control():
    spec=importlib.util.spec_from_file_location('wn_control',ROOT/'skills/marmot-whitenoise/scripts/wn_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def question_text(episode,question):
    def clock(seconds):
        minutes,seconds=divmod(int(seconds),60)
        return f'{minutes}:{seconds:02d}'
    start=question['start'];end=start+question.get('duration',10)
    return (f'Episode {episode["number"]}, {clock(start)}–{clock(end)}. '
        +question['question']+'\nProvisional: '+question['provisional']
        +'\nReply here, or react 👍 to confirm the provisional wording.')

def send(config,folder,question_path):
    question=e.read(question_path);episode=e.read(folder/'episode.json')
    if set(question)-{'start','duration','question','provisional','minor','test_required'}:raise ValueError('Unknown question field')
    start=question['start'];duration=question.get('duration',10)
    if type(start) not in (int,float) or not 0<=start or not 3<=duration<=30:raise ValueError('Require a bounded source excerpt')
    if type(question['minor']) is not bool or not question['question'].strip() or not question['provisional'].strip():raise ValueError('Question, provisional interpretation and decision class are required')
    if e.file_record(folder/'published.mp3')['sha256']!=episode['final_audio_sha256']:raise ValueError('Question source changed')
    root=e.private_root(Path(config['feedback_root']));key=e.digest({'episode_guid':episode['guid'],'question':question})
    path=root/(key+'.json')
    if path.exists():return e.read(path) # Never manufacture a new send/deadline.
    pending=[e.read(p) for p in root.glob('*.json') if e.read(p).get('state') in UNRESOLVED_STATES]
    if pending:raise ValueError('Resolve the existing question before another sample')
    token=uuid.uuid4().hex[:12];staging=e.private_root(Path(config['marmot_home'])/'media-uploads'/('transcript-'+token));clip=staging/'sample.m4a'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-ss',str(start),'-i',str(folder/'published.mp3'),'-t',str(duration),'-vn','-ac','1','-ar','48000','-c:a','aac','-b:a','96k',str(clip)],check=True)
    asset=e.file_record(clip);text=question_text(episode,question)
    media=dict(account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],caption=None,idempotency_key='transcript-'+token+'-voice',attachments=[dict(path=str(clip),media_type='audio/mp4',file_name='sample.m4a',sha256=asset['sha256'],size=asset['size'])])
    message=dict(account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],text=text,idempotency_key='transcript-'+token+'-question')
    e.save(staging/'media.json',media);e.save(staging/'text.json',message)
    record=dict(id=token,state='sending',episode_guid=episode['guid'],episode=episode['number'],folder=str(folder),question=question,text=text,source_audio_sha256=episode['final_audio_sha256'],clip=asset,account=config['account_id_hex'],group=config['group_id_hex'],trusted_sender=config['trusted_hex'],created_at=e.now())
    e.save(path,record)
    for mode,name in [('send-media','media'),('send-text','text')]:
        raw=subprocess.check_output([sys.executable,str(ROOT/'skills/marmot-whitenoise/scripts/wn_control.py'),'--home',config['marmot_home'],'--'+mode,str(staging/(name+'.json'))],stderr=subprocess.DEVNULL)
        record[name+'_receipt']=json.loads(raw);e.save(path,record)
    sent=datetime.now(timezone.utc);record.update(state='waiting',sent_at=sent.isoformat(),deadline=(sent+timedelta(minutes=15)).isoformat() if question['minor'] else None,message_ids=record['text_receipt']['response']['message_ids_hex'])
    e.save(path,record);return record

def receive(config,incoming):
    root=Path(config['feedback_root'])
    if not root.exists():return None
    text=incoming['text'].strip()
    if re.fullmatch(r'(?i)(?:/?help|episodes|transcribe \S+ \S+|podcast (?:help|status|episodes|(?:new|use|history) \S+ \S+))',text):return None
    records=[(path,e.read(path)) for path in root.glob('*.json')]
    used=[(path,q,reply) for path,q in records for reply in replies(q) if reply.get('message_id')==incoming['message_id']]
    if used:
        owners={path for path,q,reply in used}
        return used[0][1] if len(owners)==1 and all(reply==incoming for path,q,reply in used) else None
    candidates=[]
    for path,q in records:
        if q['state'] not in OPEN_STATES or any(q[k]!=incoming[k] for k in ('account','group')) or q['trusted_sender']!=incoming['sender']:continue
        explicit=incoming.get('reply_to') in q.get('message_ids',[]) or bool(re.search(r'(?<![a-z0-9])'+re.escape(q['id'])+r'(?![a-z0-9])',text,re.I))
        if incoming['recorded_at']<datetime.fromisoformat(q['sent_at']).timestamp()-1:continue
        candidates.append((path,q,explicit))
    matched=[x for x in candidates if x[2]]
    if not matched and not incoming.get('reply_to') and not re.fullmatch(r'(?i)approve(?: [0-9a-f]{12})?|yes [0-9a-f]{12}',text):
        matched=[x for x in candidates if x[1]['state'] in ('waiting','reply-received')]
    if len(matched)!=1:return None
    path,q,_=matched[0]
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);q=e.read(path)
        if q['state'] not in OPEN_STATES:return q if q.get('reply')==incoming else None
        remember_reply(q)
        # Transport receipt alone says nothing about whether the text answers
        # the question. The active agent classifies it after reading its meaning.
        q.update(state='reply-received',reply=incoming,received_at=e.now());e.save(path,q);return q

def classify(config,question_id,reply_id,kind):
    """Bind the agent's semantic decision to one exact authenticated text reply."""
    if kind not in ('answer','context'):raise ValueError('Expected answer or context classification')
    matches=[p for p in Path(config['feedback_root']).glob('*.json') if e.read(p).get('id')==question_id]
    if len(matches)!=1:raise ValueError('Cannot uniquely identify the feedback question')
    path=matches[0]
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);q=e.read(path);reply=q.get('reply',{})
        for key,expected in [('account',config['account_id_hex']),('group',config['group_id_hex']),('trusted_sender',config['trusted_hex'])]:
            if q[key]!=expected:raise ValueError('Feedback route differs from this configuration')
        if (reply.get('message_id')!=reply_id or reply.get('source')=='connector-timeline-reaction'
                or any(reply.get(k)!=q[v] for k,v in [('account','account'),('group','group'),('sender','trusted_sender')])):
            raise ValueError('Classification does not match the current authenticated text reply')
        previous=[x for x in q.get('reply_classifications',[]) if x['message_id']==reply_id]
        if previous:
            if previous[-1]['kind']!=kind:raise ValueError('Reply classification already differs; inspect before changing it')
            return q
        if q['state']!='reply-received':raise ValueError('No unclassified text reply is pending')
        q.setdefault('reply_classifications',[]).append(dict(message_id=reply_id,kind=kind,classified_at=e.now(),previous_deadline=q.get('deadline')))
        if kind=='context':
            # A request for more audio is still an open human question, not an
            # answer or permission to expire while the context is being supplied.
            q.update(state='waiting',deadline=None)
        else:q['state']='answered'
        e.save(path,q);return q

def receive_reaction(config,message,reaction):
    """Accept only a currently materialized trusted thumbs-up on this exact question."""
    if message.get('direction')!='sent' or message.get('availability')!='available' or message.get('sender',{}).get('account_id_hex')!=config['account_id_hex']:return None
    if reaction.get('actor',{}).get('account_id_hex')!=config['trusted_hex'] or not re.fullmatch('👍[\U0001f3fb-\U0001f3ff]?\ufe0f?',reaction.get('emoji','')):return None
    identifier=reaction.get('reaction_message_id_hex','')
    if not re.fullmatch('[0-9a-f]{64}',identifier):return None
    for path in Path(config['feedback_root']).glob('*.json'):
        q=e.read(path)
        if q['state'] not in OPEN_STATES or message['message_id_hex'] not in q.get('message_ids',[]):continue
        if q['account']!=config['account_id_hex'] or q['group']!=config['group_id_hex'] or q['trusted_sender']!=config['trusted_hex']:continue
        when=reaction.get('reacted_at')
        if type(when) is not int or when<datetime.fromisoformat(q['sent_at']).timestamp()-1:continue
        reply=dict(account=q['account'],group=q['group'],message_id=identifier,sender=q['trusted_sender'],text=reaction['emoji'],recorded_at=when,reply_to=message['message_id_hex'],source='connector-timeline-reaction')
        with path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);q=e.read(path)
            if q['state'] not in OPEN_STATES:return None
            remember_reply(q)
            q['reaction_previous_reply']=q.get('reply');q['reaction_previous_received_at']=q.get('received_at')
            q.update(reaction_previous_state=q['state'],state='answered',reply=reply,received_at=e.now());e.save(path,q);return q
    return None

def poll(config):
    m=control();m.MARMOT_DIR=Path(config['marmot_home'])
    page=m.rpc(str(m.MARMOT_DIR/'dev/wn-agent.sock'),dict(type='timeline_list',account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],limit=50),30)
    for msg in sorted(page.get('messages',[]),key=lambda x:(x['recorded_at'],x['message_id_hex'])):
        if msg['direction']=='received' and msg['availability']=='available' and not msg.get('text_truncated') and msg.get('text'):
            receive(config,dict(account=config['account_id_hex'],group=config['group_id_hex'],sender=msg['sender']['account_id_hex'],text=msg['text'],message_id=msg['message_id_hex'],recorded_at=msg['recorded_at'],reply_to=msg.get('reply_to_message_id_hex')))
    # Reactions are attached to their target and do not enter the text harness.
    # Query pending question IDs directly, independently of timeline pagination.
    for path in Path(config['feedback_root']).glob('*.json'):
        question=e.read(path)
        if question['state'] not in OPEN_STATES:continue
        for identifier in question.get('message_ids',[]):
            response=m.rpc(str(m.MARMOT_DIR/'dev/wn-agent.sock'),dict(type='timeline_message_get',account_id_hex=config['account_id_hex'],group_id_hex=config['group_id_hex'],message_id_hex=identifier),30)
            if any(response.get(k)!=v for k,v in [('account_id_hex',config['account_id_hex']),('group_id_hex',config['group_id_hex']),('message_id_hex',identifier)]):raise ValueError('Question timeline identity mismatch')
            message=response.get('message',{})
            if message.get('message_id_hex')!=identifier or message.get('reactions_truncated'):raise ValueError('Question reaction evidence is incomplete')
            for reaction in message.get('reactions',[]):receive_reaction(config,message,reaction)
    result=[]
    for p in Path(config['feedback_root']).glob('*.json'):
        with p.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);q=e.read(p)
            if q['state']=='waiting' and q.get('deadline') and datetime.now(timezone.utc)>=datetime.fromisoformat(q['deadline']):
                q.update(state='provisional',fallback_at=e.now());e.save(p,q)
        result.append(q)
    return result

def require_for_publication(config,episode):
    records=[e.read(p) for p in Path(config['feedback_root']).glob('*.json') if e.read(p).get('episode_guid')==episode['guid']]
    required=config['episodes'][episode['guid']].get('force_feedback',False)
    if required and not records:raise ValueError('Mandatory episode feedback test has not been sent')
    if any(q['state'] not in ('answered','provisional') for q in records):raise ValueError('Feedback is still waiting; do not spend model tokens polling it')
    return records

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('send');q.add_argument('--folder',type=Path,required=True);q.add_argument('--question',type=Path,required=True);s.add_parser('poll')
    q=s.add_parser('classify');q.add_argument('--question-id',required=True);q.add_argument('--reply-id',required=True);q.add_argument('--kind',choices=['answer','context'],required=True)
    a=p.parse_args();cfg=e.read(a.config)
    if a.action=='send':result=send(cfg,a.folder,a.question)
    elif a.action=='classify':result=classify(cfg,a.question_id,a.reply_id,a.kind)
    else:result=poll(cfg)
    print(json.dumps(result,indent=2))
if __name__=='__main__':failures.cli(main)
