#!/usr/bin/env python3
"""Deterministic local chapter handoff; no model API or chat notifications."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import chapters
import episodes as e
import failures

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('chapter_queue_registration',ROOT/'adapters/openai-agents/chapter_queue.py')
queue=importlib.util.module_from_spec(spec);spec.loader.exec_module(queue)


def context(instance, root, authorization):
    cfg,manifest,state=queue.checked(instance,root);grant=e.read(authorization)
    if (grant.get('source')!='explicit-maintainer-user-request' or
            grant.get('api_queue_paused') is not True or grant.get('marmot_notifications') is not False or
            e.read(root/'control.json').get('paused') is not True):
        raise ValueError('Explicit local handoff and paused API queue are required')
    selected=[x['number'] for x in manifest['selected'] if x['number'] not in grant['completed_numbers']]
    if selected!=grant['remaining_numbers'] or state['completed']!=grant['completed_numbers']:
        raise ValueError('Local handoff differs from the fixed queue selection')
    path=authorization.parent/'local-progress.json'
    binding=dict(manifest_sha256=chapters.sha(root/'manifest.json'),authorization_sha256=chapters.sha(authorization))
    progress=e.read(path) if path.exists() else dict(binding=binding,completed={})
    if progress['binding']!=binding or any(n not in selected for n in progress['completed']):
        raise ValueError('Local progress authorization changed')
    pending=[n for n in selected if n not in progress['completed']]
    return cfg,manifest,progress,path,pending


def operate(instance, root, authorization, action, number=None):
    with (authorization.parent/'.local-progress.lock').open('a') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        cfg,manifest,progress,path,pending=context(instance,root,authorization)
        if action=='next':
            return dict(next=pending[0] if pending else None,remaining=len(pending),
                completed_locally=len(progress['completed']),completed_before_handoff=len(e.read(authorization)['completed_numbers']))
        if not pending or number!=pending[0]:
            raise ValueError('Operate only on the next explicitly selected episode')
        selected=next(x for x in manifest['selected'] if x['number']==number)
        if action=='prepare':
            registration=queue.register(instance,cfg,root,selected)
            folder=Path(registration['directory'])
            with chapters.locked(folder):prepared=chapters.prepare(cfg,folder)
            return dict(number=number,task=registration['task'],folder=str(folder),config=cfg['config_path'],
                duration=prepared['duration'],transcript_sha256=chapters.sha(folder/'transcript.vtt'))
        with e.journal(Path(instance['work_root'])) as (_,data):
            registration=e.episode(data,manifest['show'],number)['chapters']
        folder=Path(registration['directory']);completion=chapters.completion(folder)
        if not completion or e.read(folder/'transport.json')['phase']!='verified':
            raise ValueError('Record only publicly verified chapter completion')
        if e.read(folder/'episode.json')['guid']!=selected['guid']:
            raise ValueError('Completion belongs to another episode')
        progress['completed'][number]=dict(completion=completion,verified_at=e.now(),
            verification_sha256=chapters.sha(folder/'verification.json'),folder=str(folder))
        e.save(path,progress)
        return dict(number=number,completion=completion,remaining=len(pending)-1,notifications=False)


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance',type=Path,required=True);p.add_argument('--queue',type=Path,required=True)
    p.add_argument('--authorization',type=Path,required=True)
    p.add_argument('action',choices=('next','prepare','record'));p.add_argument('--number')
    a=p.parse_args()
    if a.action!='next' and not a.number:p.error('prepare/record require --number')
    print(json.dumps(operate(e.read(a.instance),a.queue,a.authorization,a.action,a.number),indent=2))


if __name__=='__main__':failures.cli(main,'chapters')
