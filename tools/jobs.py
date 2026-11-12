#!/usr/bin/env python3
"""Bounded background production jobs with durable, token-free Marmot completion notices."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import time
import uuid
import episodes as e
import failures

HERE=Path(__file__).resolve().parent
KINDS={
 'transcript-analyze':('transcribe.py','analyze',{'config','folder','clusters'}),
 'transcript-recognize':('transcription_review.py','recognize',{'config','folder','out','windows','model'}),
 'transcript-speakers':('transcription_review.py','speakers',{'config','folder','out','windows','references'}),
 'draft-upload':('episodes.py','draft-upload',{'root','show','episode','revision','config','authorization'}),
 'draft-cleanup':('episodes.py','draft-cleanup',{'root','show','episode','config'}),
 'render':('produce.py','render',{'revision'}),
 'package':('produce.py','package',{'revision','out'}),
 'review-fragment':('review_media.py','fragment',{'input','home','id','start','duration','account','group','caption'}),
 'nostr':('publish.py','nostr',{'root','show','episode','revision','config'}),
 'youtube-private':('publish.py','youtube-private',{'root','show','episode','revision','config'}),
 'youtube-public':('publish.py','youtube-public',{'root','show','episode','revision','config'}),
}

def command(request):
    kind=request['kind']
    if kind not in KINDS:raise ValueError('Unsupported production job kind')
    script,action,fields=KINDS[kind];values=request['parameters']
    if set(values)!=fields or any(not isinstance(v,str) or not v or '\0' in v for v in values.values()):raise ValueError('Unexpected job parameters')
    result=[sys.executable,str(HERE/script),action,*[x for k,v in values.items() for x in ('--'+k,v)]]
    if script=='transcription_review.py':
        runtime=e.read(values['config'])['python']
        if not Path(runtime).is_absolute() or not os.access(runtime,os.X_OK):raise ValueError('Configured transcription Python must be an executable absolute path')
        result=[runtime,str(HERE/script),*[x for k in ('config','folder','out') for x in ('--'+k,values[k])],action,*[x for k,v in values.items() if k not in ('config','folder','out') for x in ('--'+k,v)]]
    if kind=='transcript-analyze':
        runtime=e.read(values['config'])['python']
        if not Path(runtime).is_absolute() or not os.access(runtime,os.X_OK):raise ValueError('Configured transcription Python must be an executable absolute path')
        result=['nice','-n','10',runtime,str(HERE/script),'--config',values['config'],action,'--folder',values['folder'],'--clusters',values['clusters']]
    if script=='episodes.py':
        result=[sys.executable,str(HERE/script),'--root',values['root'],action,*[x for k,v in values.items() if k!='root' for x in ('--'+k,v)]]
    if request.get('apply') is True:
        if not kind.startswith('youtube') and kind!='nostr' and not kind.startswith('draft-'):raise ValueError('Apply only belongs to publishing jobs')
        result.append('--apply')
    return result

def clean_env():
    home=Path.home();user=pwd.getpwuid(os.getuid()).pw_name
    return dict(HOME=str(home),USER=user,LOGNAME=user,PATH=str(home/'.local/bin')+':/usr/bin:/bin',SHELL='/bin/bash',LANG='C.UTF-8')

def process_identity(pid):
    try:return dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),start=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19])
    except OSError:return None

def start(root,identifier,request):
    root=e.private_root(root);e.slug(identifier);command(request)
    folder=root/identifier;folder.mkdir(mode=0o700,exist_ok=True);path=folder/'job.json'
    with (folder/'.launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists():
            old=e.read(path)
            if old['request']!=request:raise ValueError('Job ID is bound to a different request')
            return old
        state=dict(schema=1,id=identifier,request=request,request_sha256=e.digest(request),state='queued',created_at=e.now())
        e.save(path,state)
        with (folder/'launcher.log').open('ab') as log:
            child=subprocess.Popen([sys.executable,str(HERE/'jobs.py'),'worker','--job',str(folder)],env=clean_env(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        e.save(folder/'launcher.json',dict(pid=child.pid,identity=process_identity(child.pid)))
        return state

def failure_stage(kind):
    return 'prepare' if kind=='review-fragment' else 'transcript' if kind.startswith('transcript-') else kind

def notify(folder):
    state=e.read(folder/'job.json')
    if state['state'] not in ('completed','failed'):raise ValueError('Job has no terminal result to notify')
    target=state['request'].get('notify')
    if not target:return dict(state='not_configured')
    with (folder/'.notify.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=folder/'notification.json'
        if path.exists() and e.read(path).get('state') in ('confirmed','suppressed'):return e.read(path)
        manifest=folder/'notice.send.json'
        text=f'Podcast job {state["id"]}: {state["state"]}. Kind: {state["request"]["kind"]}. Saved result: {folder}/job.json. '
        if state['request']['kind'] in ('nostr','youtube-private','youtube-public','draft-upload','draft-cleanup') and state['request'].get('apply') is not True:text+='Plan only: no mutation requested. '
        if state['state']=='completed':
            instance=Path(target['home'])/'podcaster-instance.json'
            automatic=state['request']['kind'].startswith('transcript-') and instance.exists() and e.read(instance).get('transcription_wakeups') is True
            video=False
            if instance.exists() and e.read(instance).get('video_tasks_enabled') is True:
                # Video workers live only under their explicitly selected episode.
                task=folder.parent.parent/'video-task.json'
                video=task.exists() and e.read(task).get('phase') in ('queued','active')
            # Internal stages resume the controller through saved state, not chat.
            # Preserve any existing immutable send intent, including uncertain sends.
            if (automatic or video) and not manifest.exists() and not path.exists():
                result=dict(state='suppressed',reason='internal-video-stage' if video else 'internal-transcript-stage',finished_at=e.now())
                e.save(path,result);return result
            text+=('Transcript review will continue automatically. I will ask here if I need your feedback.' if automatic else 'Ready for the next production step. Send podcast status or ask to continue.')
        else:
            report_path=folder/'failure.json'
            if not report_path.exists():e.save(report_path,failures.report(stage=failure_stage(state['request']['kind']),context={'job':state['id']}))
            value=e.read(report_path)
            text=failures.save_notice(value,report_path)
        message=dict(account_id_hex=target['account'],group_id_hex=target['group'],text=text,idempotency_key='job-'+state['nonce'])
        if manifest.exists():
            previous=e.read(manifest)
            if any(previous.get(k)!=message[k] for k in ('account_id_hex','group_id_hex','idempotency_key')):raise ValueError('Notification routing or identity changed')
            # A formatter change must neither rewrite an uncertain send nor
            # deliver a legacy full report after switching to UUID-only notices.
            if state['state']=='failed' and previous!=message:raise ValueError('Existing failure notification differs; inspect delivery before replacing its immutable send intent')
            message=previous
        e.save(manifest,message)
        e.save(path,dict(state='pending',manifest_sha256=e.digest(message)))
        try:
            raw=subprocess.check_output([sys.executable,str(HERE.parent/'skills/marmot-whitenoise/scripts/wn_control.py'),'--home',target['home'],'--send-text',str(manifest)],env=clean_env(),stderr=subprocess.DEVNULL)
            result=dict(state='confirmed',receipt=json.loads(raw));e.save(path,result);return result
        except BaseException as error:
            e.save(path,dict(state='unresolved',error_type=type(error).__name__,instruction='Inspect the wn_control send ledger/timeline before retrying. Re-running notify never re-runs production.'));raise

def preflight(request):
    kind=request['kind'];params=request['parameters']
    context={k:params[k] for k in ('show','episode','revision') if k in params and k!='revision'}
    def missing(code,component):return failures.report(code,failure_stage(kind),component,context,effects='not-started')
    if kind in ('render','package','review-fragment'):
        for tool in (('ffmpeg','ffprobe','fc-match') if kind=='render' else ('ffmpeg','ffprobe')):
            if shutil.which(tool) is None:return missing('missing-tool',tool)
        if kind=='render' and importlib.util.find_spec('PIL') is None:return missing('missing-module','PIL')
        if kind=='review-fragment':
            if not Path(params['input']).is_file():return missing('missing-input','revision')
        else:
            revision=Path(params['revision'])
            for file in (('prepared.json',) if kind=='render' else ('prepared.json','render.json')):
                if not (revision/file).is_file():return missing('missing-input','revision')
    else:
        path=Path(params['config'])
        if not path.is_file():return missing('configuration-required','configuration')
        try:
            config=e.read(path)
            if request.get('apply') is True:e.guard(config,{'draft-cleanup':'draft-delete'}.get(kind,kind))
        except Exception as error:return failures.from_exception(error,failure_stage(kind),context,effects='not-started')
    return None

def save_failure(folder,value):
    path=folder/'failure.json'
    try:failures.persist(value,path)
    except (OSError,ValueError):
        if not path.exists():e.save(path,value)

def worker(folder):
    with (folder/'.worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=folder/'job.json';state=e.read(path)
        if state['state']!='queued':raise ValueError('Worker already attempted; inspect saved state before recovery')
        if state['request_sha256']!=e.digest(state['request']):raise ValueError('Job request changed')
        state.update(state='running',started_at=e.now(),pid=os.getpid(),identity=process_identity(os.getpid()),nonce=uuid.uuid4().hex);e.save(path,state)
        try:
            prerequisite=preflight(state['request'])
            if prerequisite:
                prerequisite['context']['job']=failures.safe_id(state['id']);save_failure(folder,prerequisite)
                state.update(state='failed',exit_code=None)
            else:
                env=clean_env();env['SP_FAILURE_REPORT']=str(folder/'failure.json')
                with (folder/'production.log').open('xb') as log:
                    result=subprocess.run(command(state['request']),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
                state.update(state='completed' if result.returncode==0 else 'failed',exit_code=result.returncode)
                if result.returncode and not (folder/'failure.json').exists():
                    save_failure(folder,failures.report(stage=failure_stage(state['request']['kind']),context={'job':state['id']}))
        except BaseException as error:
            state.update(state='failed',error_type=type(error).__name__)
            if not (folder/'failure.json').exists():save_failure(folder,failures.from_exception(error,failure_stage(state['request']['kind']),{'job':state['id']}))
        state['finished_at']=e.now();e.save(path,state)
    # Publication/render outcome is committed before touching chat transport.
    try:notify(folder)
    except Exception:pass
    return state

def status(folder):
    state=e.read(folder/'job.json')
    if state['state']=='running' and process_identity(state['pid'])!=state['identity']:state=dict(state,state='interrupted',recovery='No worker is running. Inspect stage receipts and partial outputs before an explicit recovery job.')
    if (folder/'failure.json').exists():state['failure']=e.read(folder/'failure.json')
    if (folder/'notification.json').exists():state['notification']=e.read(folder/'notification.json')['state']
    return state

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('start');q.add_argument('--root',type=Path,required=True);q.add_argument('--id',required=True);q.add_argument('--request',type=Path,required=True)
    for name in ('worker','status','notify','report'):
        q=s.add_parser(name);q.add_argument('--job',type=Path,required=True)
    a=p.parse_args()
    if a.action=='report':print(failures.format_report(e.read(a.job/'failure.json')));return
    result=start(a.root,a.id,e.read(a.request)) if a.action=='start' else {'worker':worker,'status':status,'notify':notify}[a.action](a.job.resolve())
    print(json.dumps(result,indent=2))
if __name__=='__main__':failures.cli(main)
