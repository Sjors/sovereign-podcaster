#!/usr/bin/env python3
"""Explicit video tasks; wake only on initial assignment, job completion or review approval."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[1]/'tools'))
import episodes as e
import failures
import episode_routing
spec=importlib.util.spec_from_file_location('video_backend',HERE/'marmot-backend.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


def instructions(task_path):
    announce=e.read(task_path)['announce']
    policy=('This task explicitly requests NO announcement: set announce:false, announcement:"", announcement_mentions:[] in reviewed Nostr metadata. Publish only the native video for nostu.be. No kind-1 or other announcement. '
        'After approval use publish.py nostr with its default all phase and announce:false, then verify/link the native video on Castopod. ' if not announce else
        'This task requests the normal announcement flow: prepare the exact native video and announcement for review. After approval use the video phase, verify/link the native video on Castopod, then use the announcement phase with the matching linkage receipt. ')
    return ('Continue ONLY the explicitly authorized video task at '+str(task_path)+'. Read that task, its actual saved human request and docs/production.md, docs/episode-flow.md, skills/video-production/SKILL.md and relevant publishing skills. '
        'Use the selected existing episode current final audio, native transcript, canonical chapters and description; preserve original media, GUID, pubDate and unrelated notes. Source paths in the task are leads, not editorial authority over current published corrections. '
        "For public Castopod browser-page checks explicitly request Accept: text/html, using tools.transcribe.get(url, accept='text/html') or an equivalent explicit header. Castopod negotiates other representations; a 404 without the HTML Accept header does not establish that its public page is broken. Correct that read-only request before reporting a hosting blocker. An episode without a native video need not have a working video tab yet: inspect the existing native identifier and verify that tab after authorized linkage. Never change hosting routes merely to recover from a missing Accept header. "
        'Create a polished full-length slide video with useful technical source captures, verify scene frames/captions/chapters/audio clock, and send the preview and focused questions to the task verified White Noise route through encrypted attachments. '
        'Before approval use encrypted preview attachments only; do not upload a public draft. Inspect existing native Nostr/YouTube video references before creating anything, preserving known IDs and asking a focused question if a new upload would duplicate an existing release. '
        'Use episode-directory/jobs for ALL durable work (render/package/draft/publication), not a foreground encode. Job completions and exact review approvals wake this task automatically. Never poll jobs or a person; return WAITING_FOR_JOB or WAITING_FOR_REVIEW after a tool already sent the question/offer. Do not send duplicate progress. '
        'Prepare encrypted review clips using a review-fragment job: parameters are input, home, id, start, duration, account, group, caption (all strings, explicit task route, duration at most 120 seconds). It only stages media and send.json; it sends nothing. After job completion inspect the manifest and existing send ledger, then use wn_control.py --send-media once for that exact manifest. Return WAITING_FOR_REVIEW after the attachment/question was sent. '
        +policy+
        'Before any final upload/publication request an exact nostr review with --include-youtube-public. The offer must explicitly cover native Nostr video, the same verified YouTube private ID becoming public after inspection, and adding that native video to this existing Castopod episode. Wait for actual authenticated approval. '
        'Verify storage/native event and nostu.be; use the installed Castopod episode-video interface and verify the matching public link without replacing audio/transcript/notes. Save castopod-link.json beside the task with verified:true, manifest_sha256, video_event_id, identifier, episode_url and preserved-identity evidence. '
        'Then use youtube-private, inspect that exact ID/captions/thumbnail/metadata, and youtube-public: the full-release offer already grants this, so no redundant approval is needed unless the packet/destinations changed. Public release still rechecks that exact ID. '
        'Use deterministic receipts and readback; inspect effects before retries. Never invent approval, receipts, source clearance or publication success. Do not bypass an explicit maintenance pause. Missing prerequisites require tools/failures.py and only a UUID notice. '
        'After full verification run video_tasks.py finish --instance INSTANCE --show SHOW --episode NUMBER (substitute the task values), then give the verified links. Never start another episode or backfill queue.')


def route_for(instance):
    group=instance.get('video_group_id_hex')
    if not group and instance.get('transcription_config'):group=e.read(instance['transcription_config'])['group_id_hex']
    records=[e.read(p) for p in (Path(instance['state_root'])/'routing').glob('*.json')]
    matches=[r for r in records if r['binding']['account']==instance['account_id_hex'] and r['binding']['group']==group]
    if len(matches)!=1:raise ValueError('Require exactly one explicitly configured verified video conversation')
    if not Path(matches[0]['binding']['cwd']).resolve().is_relative_to(Path(instance['workspace_root']).resolve()):raise ValueError('Video route is outside the configured workspace')
    return matches[0]


def enroll(instance,show,number,authorization):
    grant=b.read(authorization)
    scope=grant.get('scope',{})
    if (grant.get('source')!='explicit-maintainer-user-request' or type(scope.get('announce')) is not bool or
            scope!=dict(operation='video',show=show,episode=number,announce=scope['announce']) or not grant.get('human_request')):
        raise ValueError('Require an explicit selected-episode video request and announcement choice')
    record=route_for(instance)
    with e.journal(Path(instance['work_root'])) as (root,data):
        item=data['episodes'].get(e.key(show,number)) or e.initialize(root,data,show,number)
        if item.get('video_task'):raise ValueError('Video task already exists; inspect/resume it rather than enrolling again')
        folder=Path(item['directory']);path=folder/'video-task.json'
        if path.exists():raise ValueError('Existing video task needs inspection')
        evidence=e.evidence_copy(item,authorization,'video-task')
        task=dict(schema=1,id=str(uuid.uuid4()),source='explicit-user-task',operation='video',show=show,episode=number,announce=scope['announce'],
            directory=str(folder),authorization=evidence,route=record['binding'],public_handle=record['public_handle'],
            source_references=grant.get('source_references',[]),instance=str(Path(instance['marmot_home'])/'podcaster-instance.json'),
            publication_config=grant['publication_config'],created_at=e.now(),phase='queued',handled_events=[])
        e.save(path,task);item['video_task']=dict(path=str(path))
        return task


def events(item,task):
    import jobs
    found=['initial:'+task['id']]
    for path in (Path(item['directory'])/'jobs').glob('*/job.json'):
        job=jobs.status(path.parent)
        if job['state'] in ('running','queued'):return []
        if job['state'] in ('failed','interrupted'):raise RuntimeError('A video job failed or was interrupted; inspect its effects before continuing')
        if job['state']=='completed':
            if job.get('exit_code')!=0 or e.digest(job['request'])!=job['request_sha256']:raise ValueError('Video job completion evidence changed')
            found.append('job:'+e.digest(dict(path=str(path),nonce=job['nonce'],request=job['request_sha256'])))
    for packet in item.get('reviews',{}).values():
        if packet['state']=='approved':found.append('approval:'+packet['id']+':'+packet['approval_message_id'])
    return sorted(set(found)-set(task['handled_events']))


def send(instance,task_path,identifier,text):
    task=e.read(task_path);folder=e.private_root(task_path.parent/'video-notices');path=folder/(identifier+'.json')
    value=dict(account_id_hex=task['route']['account'],group_id_hex=task['route']['group'],text=text,idempotency_key='video-'+task['id']+'-'+identifier)
    if path.exists():
        if e.read(path)!=value:raise ValueError('Video notice changed; inspect its delivery')
    else:e.save(path,value)
    raw=subprocess.check_output([sys.executable,str(HERE.parents[1]/'skills/marmot-whitenoise/scripts/wn_control.py'),'--home',instance['marmot_home'],'--send-text',str(path)],stderr=subprocess.DEVNULL)
    e.save(path.with_suffix('.receipt.json'),json.loads(raw))


def invoke(instance,path,batch):
    task=e.read(path);route=task['route'];record=route_for(instance)
    if record['binding']!=route:raise ValueError('Original video route changed')
    with episode_routing.select(instance,task['public_handle'],'podcast use '+task['show']+' '+task['episode'],route):pass
    with episode_routing.select(instance,task['public_handle'],'',route) as selected:
        scoped=dict(instance,state_root=str(selected.state_root),nonblocking_lock=True,turn_timeout_seconds=600,
            operator_submission=dict(source='job-completion',id=batch['submission'],authorization_file=str(path)),episode_instructions=instructions(path))
        for key,value in [('MARMOT_ACCOUNT_ID_HEX',route['account']),('MARMOT_GROUP_ID_HEX',route['group']),('MARMOT_AGENT_SOCKET',str(Path(instance['marmot_home'])/'dev/wn-agent.sock'))]:os.environ[key]=value
        for key in ('MARMOT_MESSAGE_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX'):os.environ.pop(key,None)
        if scoped.get('allow_timeout_only') is not True:raise ValueError('No accepted bounded-turn spending policy')
        scoped,api,restricted=b.model_client(scoped)
        b.emit=lambda _:None
        return b.conversation(scoped,selected.backend_handle,batch['prompt'],route,api,restricted,emit_event=lambda event:selected.observe(event,lambda _:None))[0]


def run_once(instance,run=invoke,deliver=send):
    if instance.get('video_tasks_enabled') is not True:return
    root=e.private_root(Path(instance['state_root'])/'video-tasks')
    with (root/'.watch.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        journal=Path(instance['work_root'])/'episodes.json'
        if not journal.exists():return
        for item in e.read(journal)['episodes'].values():
            if not item.get('video_task'):continue
            path=Path(item['video_task']['path']);task=e.read(path)
            if task['phase'] in ('blocked','paused') or (task['phase']=='completed' and not task.get('batch')):continue
            # Human foreground work owns the same lock/active checkpoint.
            if any(Path(instance['state_root']).rglob('*.active.json')):continue
            try:
                if e.file_record(task['authorization']['path'])!=task['authorization']:raise ValueError('Video authorization evidence changed')
                current=events(item,task)
                pending=task.get('batch')
                if not current and not pending:continue
                if not pending:
                    submission=str(uuid.uuid4());pending=dict(submission=submission,events=current,phase='queued',
                        prompt=instructions(path)+'\nVerified new controller events: '+json.dumps(current))
                    task['batch']=pending;e.save(path,task)
                # Persist the batch before invoking; conversation deduplication
                # owns uncertain calls, so a restart can only inspect/reuse them.
                if pending['phase']!='model-completed':
                    pending['answer']=run(instance,path,pending);pending['phase']='model-completed'
                    current_task=e.read(path);current_task['batch']=pending;e.save(path,current_task)
                answer=pending['answer'].strip()
                if answer not in ('WAITING_FOR_JOB','WAITING_FOR_REVIEW'):
                    deliver(instance,path,pending['submission'],answer)
                task=e.read(path);task['handled_events']=sorted(set(task['handled_events']+pending['events']))
                task.pop('batch',None)
                failure=re.search(r'Report UUID: ([0-9a-f-]{36})',answer)
                if failure:task.update(phase='blocked',failure_uuid=failure[1])
                if task['phase']=='queued':task['phase']='active'
                e.save(path,task)
            except b.ConversationBusy:continue
            except Exception as error:
                report=failures.from_exception(error,'controller');notice=failures.save_notice(report)
                task=e.read(path);task.update(phase='blocked',failure_uuid=report['id']);e.save(path,task)
                try:deliver(instance,path,report['id'],notice)
                except Exception:pass


def finish(instance,show,number):
    with e.journal(Path(instance['work_root'])) as (_,data):
        item=e.episode(data,show,number);task_path=Path(item['video_task']['path']);task=e.read(task_path)
        r=e.verified_revision(item,item['current_revision'])
        if not e.complete(item):raise ValueError('Video publication is not completely verified')
        native=e.published(item,'nostr',r['nostr_manifest_sha256'])['receipt'];link=e.read(task_path.parent/'castopod-link.json')
        if ((native.get('announcement_skipped') is True)!= (not task['announce']) or link.get('verified') is not True or
            link.get('manifest_sha256')!=r['nostr_manifest_sha256'] or link.get('video_event_id')!=native['video_event_id'] or
            link.get('identifier')!=native.get('identifier') or not link.get('episode_url')):raise ValueError('Require matching verified announcement policy, native video and Castopod linkage')
        task.update(phase='completed',finished_at=e.now());e.save(task_path,task)


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['enroll','finish'])
    p.add_argument('--instance',type=Path,required=True);p.add_argument('--show',required=True);p.add_argument('--episode',required=True);p.add_argument('--authorization',type=Path)
    a=p.parse_args();instance=b.read(a.instance)
    if a.action=='enroll':
        if not a.authorization:p.error('enroll requires an explicit private authorization')
        enroll(instance,a.show,a.episode,a.authorization)
    else:finish(instance,a.show,a.episode)
    print('Video task '+('enrolled.' if a.action=='enroll' else 'verified complete.'))

if __name__=='__main__':failures.cli(main,'controller')
