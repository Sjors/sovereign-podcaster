#!/usr/bin/env python3
"""Serial chapter backfill from an explicit operator grant and a fixed feed snapshot."""
import argparse
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'tools'))
import chapters
import episodes as e
import failures
spec = importlib.util.spec_from_file_location('chapter_queue_backend',HERE/'marmot-backend.py')
b = importlib.util.module_from_spec(spec);spec.loader.exec_module(b)


def config(instance):
    path = Path(instance['chapters_config'])
    return dict(e.read(path),config_path=str(path))


def create(instance, root, authorization):
    cfg = config(instance); grant = e.read(authorization)
    if grant.get('source') != 'explicit-maintainer-user-request' or grant.get('scope') != dict(operation='chapters-backfill',show=cfg['show'],feed=cfg['feed']):
        raise ValueError('An explicit chapter backfill authorization for this feed is required')
    if cfg.get('paused') is not False or cfg.get('allow_published_source_intake') is not True:
        raise ValueError('Chapter backfill intake is paused or disabled')
    if root.exists():
        raise ValueError('Queue already exists; inspect saved state instead of creating another')
    feed,_ = chapters.get(cfg['feed']); items = ET.fromstring(feed).findall('./channel/item')
    journal = Path(instance['work_root'])/'episodes.json'
    tracked = e.read(journal)['episodes'] if journal.exists() else {}
    selected=[]; skipped=[]; excluded=[]; identities=set(); guids=set()
    exclude_guids=grant.get('exclude_guids',[])
    if not isinstance(exclude_guids,list) or any(not isinstance(g,str) or not g for g in exclude_guids):
        raise ValueError('Explicit queue exclusions must be feed GUIDs')
    for item in items:
        native = item.findtext('{http://www.itunes.com/dtds/podcast-1.0.dtd}episode')
        guid=item.findtext('guid'); url=item.findtext('link'); title=item.findtext('title')
        number = native
        if number is None:
            match = re.match(r'^Bitcoin, Explained ([1-9][0-9]*):',title or '')
            number = match[1] if match else 'special-'+hashlib.sha256((guid or '').encode()).hexdigest()[:16]
        e.slug(number)
        if not guid or not url or number in identities or guid in guids:
            raise ValueError('Feed identities are missing or ambiguous')
        identities.add(number);guids.add(guid)
        if guid in exclude_guids:
            excluded.append(dict(guid=guid,title=title,url=url));continue
        existing=tracked.get(e.key(cfg['show'],number),{}).get('chapters')
        if existing and chapters.completion(existing['directory']):
            if e.read(Path(existing['directory'])/'episode.json')['guid'] != guid:
                raise ValueError('Completed chapter identity differs from the feed')
            skipped.append(number);continue
        if existing or item.findall('{'+chapters.NS+'}chapters'):
            raise ValueError('Existing chapter work needs inspection before queueing')
        date=item.findtext('pubDate');parsed=parsedate_to_datetime(date)
        if parsed.tzinfo is None:
            raise ValueError('Feed publication dates need timezones')
        selected.append(dict(number=number,native_number=native,guid=guid,url=url,title=title,
            slug=url.rstrip('/').rsplit('/',1)[-1],pubDate=date,enclosure=dict(item.find('enclosure').attrib)))
    if set(exclude_guids) != {x['guid'] for x in excluded}:
        raise ValueError('Explicit queue exclusion was not found in the selected feed')
    selected.sort(key=lambda x:parsedate_to_datetime(x['pubDate']),reverse=True)
    root=e.private_root(root);e.private_root(root/'items')
    (root/'feed.xml').write_bytes(feed)
    e.save(root/'authorization.json',grant)
    manifest=dict(schema=1,show=cfg['show'],feed=cfg['feed'],selected=selected,skipped=skipped,excluded=excluded,
        account=instance['account_id_hex'],group=cfg['group_id_hex'],created_at=e.now(),
        authorization_sha256=chapters.sha(root/'authorization.json'),feed_sha256=chapters.sha(root/'feed.xml'))
    e.save(root/'manifest.json',manifest)
    e.save(root/'state.json',dict(manifest_sha256=chapters.sha(root/'manifest.json'),phase='queued',completed=[]))
    e.save(root/'control.json',dict(paused=False))
    return manifest


def checked(instance, root):
    cfg=config(instance);manifest=e.read(root/'manifest.json');state=e.read(root/'state.json')
    if (state['manifest_sha256'] != chapters.sha(root/'manifest.json') or
            manifest['authorization_sha256'] != chapters.sha(root/'authorization.json') or
            manifest['feed_sha256'] != chapters.sha(root/'feed.xml') or manifest['show'] != cfg['show'] or
            manifest['feed'] != cfg['feed'] or manifest['account'] != instance['account_id_hex'] or
            manifest['group'] != cfg['group_id_hex']):
        raise ValueError('Queue authorization, snapshot or destination changed')
    return cfg,manifest,state


def register(instance, cfg, root, selected):
    number=selected['number'];show=cfg['show']
    entry=chapters.acquire_source(cfg,show,number,selected=selected)
    with e.journal(Path(instance['work_root'])) as (work,data):
        item=data['episodes'].get(e.key(show,number)) or e.initialize(work,data,show,number)
        if item.get('chapters'):
            task=e.read(item['chapters']['task'])
            if task['authorization']['request_path'] != str(root/'authorization.json') or task['source'] != entry:
                raise ValueError('Chapter work was registered by another task; inspect it')
            return item['chapters']
        directory=Path(item['directory']);folder=directory/'chapters';task_path=directory/'chapters-task.json'
        if folder.exists() or task_path.exists():
            raise ValueError('Unresolved chapter artifacts; inspect before retrying')
        e.private_root(folder)
        grant=e.read(root/'authorization.json')
        task=dict(operation='chapters',show=show,episode=number,episode_guid=entry['episode']['guid'],
            directory=str(folder),config=cfg['config_path'],feed=cfg['feed'],source=entry,
            authorization=dict(request_path=str(root/'authorization.json'),incoming_sha256=e.digest(grant['incoming'])),
            queue_manifest=str(root/'manifest.json'))
        e.save(task_path,task);item['chapters']=dict(directory=str(folder),task=str(task_path))
        return item['chapters']


def invoke(instance, cfg, root, path, item):
    context=e.private_root(root/'contexts'/item['number'])
    route=b.binding(instance,dict(MARMOT_ACCOUNT_ID_HEX=instance['account_id_hex'],
        MARMOT_GROUP_ID_HEX=cfg['group_id_hex']),Path(instance['repository']).resolve())
    scoped=dict(instance,state_root=str(context),nonblocking_lock=True,followup_steering=False,
        turn_timeout_seconds=instance.get('chapters_turn_timeout_seconds',600),
        operator_submission=dict(source='local-operator',id=item['submission'],authorization_file=str(root/'authorization.json')))
    if instance.get('allow_timeout_only') is not True or not 30<=scoped['turn_timeout_seconds']<=600:
        raise ValueError('No accepted chapter active-turn timeout policy')
    # This is an operator-scheduled task, never a fabricated inbound Marmot message.
    for key in ('MARMOT_MESSAGE_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX'):
        os.environ.pop(key,None)
    os.environ.update(MARMOT_ACCOUNT_ID_HEX=route['account'],MARMOT_GROUP_ID_HEX=route['group'],
        MARMOT_AGENT_SOCKET=str(Path(instance['marmot_home'])/'dev/wn-agent.sock'))
    scoped,api,restricted=b.model_client(scoped)
    b.emit=lambda _:None
    def observe(event):
        if event.get('type')=='thread.started':
            item['handle']=event['thread_id'];e.save(path,item)
    return b.conversation(scoped,item.get('handle'),item['prompt'],route,api,restricted,emit_event=observe)[0]


def send(instance, cfg, path, text):
    manifest=path.with_suffix('.send.json')
    value=dict(account_id_hex=instance['account_id_hex'],group_id_hex=cfg['group_id_hex'],text=text,
        idempotency_key='chapters-queue-'+hashlib.sha256(str(path).encode()).hexdigest())
    if manifest.exists():
        if e.read(manifest)!=value:raise ValueError('Saved chapter notification intent changed')
    else:e.save(manifest,value)
    raw=subprocess.check_output([sys.executable,str(HERE.parents[1]/'skills/marmot-whitenoise/scripts/wn_control.py'),
        '--home',instance['marmot_home'],'--send-text',str(manifest)],stderr=subprocess.DEVNULL)
    e.save(path.with_suffix('.send-receipt.json'),json.loads(raw))


def run_once(instance, root, run=invoke, deliver=send):
    cfg,manifest,state=checked(instance,root)
    if cfg.get('paused') is not False or e.read(root/'control.json').get('paused') is not False:
        return dict(paused=True)
    if state['phase'] in ('completed','blocked'):
        return dict(phase=state['phase'])
    with (root/'.queue.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(busy=True)
        cfg,manifest,state=checked(instance,root)
        if list(Path(instance['state_root']).rglob('*.active.json')):
            return dict(busy=True)
        pending=[s for s in manifest['selected'] if s['number'] not in state['completed']]
        if not pending:
            state.update(phase='completed',finished_at=e.now());e.save(root/'state.json',state)
            return dict(phase='completed')
        selected=pending[0];number=selected['number'];path=root/'items'/(number+'.json')
        try:
            if path.exists():
                item=e.read(path)
                if item['phase'] == 'continuation-approved':
                    recovery=item['recovery'];approval=e.read(recovery['path'])
                    if (chapters.sha(recovery['path']) != recovery['sha256'] or
                            approval['submission'] != item['submission'] or approval['handle'] != item['handle'] or
                            approval['task'] != item['registration']['task'] or
                            approval['prompt_sha256'] != hashlib.sha256(item['prompt'].encode()).hexdigest()):
                        raise ValueError('Inspected continuation authorization differs')
                    item['phase']='running';e.save(path,item)
                    item['answer']=run(instance,cfg,root,path,item)
                    item['phase']='model-completed';e.save(path,item)
                elif item['phase'] not in ('model-completed','verified'):
                    raise RuntimeError('Earlier chapter queue attempt is unresolved; inspect before retrying')
            else:
                item=dict(number=number,phase='registering',submission=str(uuid.uuid4()),created_at=e.now())
                e.save(path,item)
                registration=register(instance,cfg,root,selected)
                item.update(registration=registration,phase='running',prompt=(
                    'Perform the existing-episode chapter task registered at '+registration['task']+'. '
                    'The owner explicitly authorized this fixed backfill queue via the saved operator grant. '
                    'This is one selected episode, not a newly received chat message. Do not re-enroll it. '
                    'Read docs/chapters.md. Review the full published transcript; choose 3–10 useful chapters '
                    '(short announcements may have fewer); verify boundaries with the configured bounded local runtime. '
                    'Use canonical Podcasting 2.0 JSON and derive description timestamps before sponsor/contact details, '
                    'preserving all wording and other notes. Publish and publicly verify with tools/chapters.py. '
                    'Serialize chapter CLI operations for this episode. When a tool returns a running session ID, '
                    'wait for that exact process to finish using write_stdin before starting render, check, publish or verify. '
                    'Do not background a check or run a second chapter command while it holds the episode lock. '
                    'No manual approval step. Preserve original audio, transcript, GUID, publication date and unrelated fields. '
                    'For legacy timestamps identify only the exact old timestamp list before replacement. '
                    'This task grants no video, Nostr, YouTube or other episode operation. Do not queue another episode. '
                    'Finish within this bounded turn; if blocked, save a private failure report and return only its UUID notice. '
                    'Return the deterministic chapter completion; the queue controller sends the single final Marmot reply. '
                    'Do not send an acknowledgement or standalone final message through a send tool.'))
                e.save(path,item)
                item['answer']=run(instance,cfg,root,path,item)
                item['phase']='model-completed';e.save(path,item)
            notice=chapters.completion(item['registration']['directory'])
            if not notice:
                match=re.search(r'Report UUID: ([0-9a-f-]{36})',item.get('answer',''))
                if match:
                    item.update(phase='blocked',failure_uuid=match[1]);e.save(path,item)
                    state.update(phase='blocked',episode=number,failure_uuid=match[1]);e.save(root/'state.json',state)
                    deliver(instance,cfg,path.with_name(number+'-failure-'+item['submission']+'.json'),'Podcast task needs attention.\nReport UUID: '+match[1])
                    return dict(phase='blocked',episode=number)
                raise RuntimeError('Model returned without a verified chapter completion')
            item.update(phase='verified',completion=notice);e.save(path,item)
            deliver(instance,cfg,path,notice)
            item.update(phase='delivered',finished_at=e.now());e.save(path,item)
            state['completed'].append(number);state['phase']='queued';e.save(root/'state.json',state)
            return dict(phase='delivered',episode=number)
        except Exception as error:
            report=failures.from_exception(error,'chapters',dict(show=manifest['show'],episode=number))
            notice=failures.save_notice(report,root/('failure-'+number+'.json'))
            state.update(phase='blocked',episode=number,failure_uuid=report['id']);e.save(root/'state.json',state)
            deliver(instance,cfg,path.with_name(number+'-failure-'+item.get('submission','unregistered')+'.json'),notice)
            return dict(phase='blocked',episode=number)


def install(instance_path, root):
    instance=e.read(instance_path);checked(instance,root)
    def quote(value):
        value=str(value)
        if any(c in value for c in ('\n','\r','\0','%')):
            raise ValueError('Unsupported systemd path')
        return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
    units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    path=units/'sovereign-podcaster-chapters.service'
    text=('[Unit]\nDescription=Sovereign podcaster authorized chapter backfill\nAfter=sovereign-podcaster-marmot.service\n\n'
        '[Service]\nType=simple\nUMask=0077\nExecStart='+quote(sys.executable)+' '+quote(Path(__file__).resolve())+
        ' --instance '+quote(instance_path.resolve())+' --queue '+quote(root.resolve())+
        '\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=30\n\n[Install]\nWantedBy=default.target\n')
    if path.exists() and path.read_text()!=text:
        raise ValueError('Existing chapter service differs; inspect before replacing it')
    path.write_text(text);path.chmod(0o600)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--now',path.name],check=True)
    return path


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance',type=Path,required=True);p.add_argument('--queue',type=Path,required=True)
    p.add_argument('--create',action='store_true');p.add_argument('--authorization',type=Path)
    p.add_argument('--install',action='store_true');p.add_argument('--once',action='store_true');a=p.parse_args()
    if a.create:
        if not a.authorization:p.error('--create needs --authorization')
        result=create(e.read(a.instance),a.queue,a.authorization)
        print(json.dumps(dict(queued=len(result['selected']),skipped=len(result['skipped']))));return
    if a.install:
        install(a.instance,a.queue);print('Authorized chapter queue service installed.');return
    while True:
        result=run_once(e.read(a.instance),a.queue)
        if a.once:print(json.dumps(result));return
        if result.get('phase') in ('blocked','completed'):return
        time.sleep(5)


if __name__=='__main__':failures.cli(main,'chapters')
