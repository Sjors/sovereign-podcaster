#!/usr/bin/env python3
"""Register one authenticated chapter task, without starting other episodes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import chapters
import episodes as e
import failures
from transcription_intake import messages


def enroll(instance, show, number, environ, authenticate=messages.authenticated):
    config_path = Path(instance['chapters_config']); config = dict(e.read(config_path),config_path=str(config_path))
    chapters.requested_source(config,show,number)
    route = {key:environ.get(env,'') for key,env in [('account','MARMOT_ACCOUNT_ID_HEX'),
        ('group','MARMOT_GROUP_ID_HEX'),('sender','MARMOT_SENDER_ACCOUNT_ID_HEX'),('message_id','MARMOT_MESSAGE_ID_HEX')]}
    key = hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()
    request = Path(instance['state_root'])/'inbox'/(key+'.json'); saved = e.read(request)
    incoming = authenticate(instance,environ,saved['incoming']['text'])
    if incoming != saved['incoming'] or incoming['group'] != config['group_id_hex']:
        raise ValueError('Task differs from its authenticated paired conversation')
    binding = saved['route']; identifier = hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
    routing = e.read(Path(instance['state_root'])/'routing'/(identifier+'.json'))
    if routing['binding'] != binding or routing['selected'] != e.key(show,number):
        raise ValueError('Select the requested chapter episode first')
    entry = chapters.acquire_source(config,show,number)
    with e.journal(Path(instance['work_root'])) as (_,data):
        item = e.episode(data,show,number)
        if item.get('chapters'): return item['chapters']
        directory = Path(item['directory']); folder = directory/'chapters'; task_path = directory/'chapters-task.json'
        if folder.exists() or task_path.exists():
            raise ValueError('Earlier chapter artifacts are unresolved; inspect before retrying')
        e.private_root(folder)
        task = dict(operation='chapters',show=show,episode=number,episode_guid=entry['episode']['guid'],
            directory=str(folder),config=str(config_path),feed=config['feed'],source=entry,
            authorization=dict(request_path=str(request),incoming_sha256=e.digest(incoming),
                message_id=incoming['message_id'],sender=incoming['sender']))
        e.save(task_path,task); item['chapters'] = dict(directory=str(folder),task=str(task_path))
        return item['chapters']


def main():
    os.umask(0o077); parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance',type=Path,required=True); parser.add_argument('--show',required=True)
    parser.add_argument('--episode',required=True); args = parser.parse_args()
    print(json.dumps(enroll(e.read(args.instance),args.show,args.episode,os.environ),indent=2))


if __name__=='__main__': failures.cli(main,'chapters')
