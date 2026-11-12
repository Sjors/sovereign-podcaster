#!/usr/bin/env python3
"""Enroll only a user-selected, source-cleared episode from the current authenticated Marmot task."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import episodes as e
import failures
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('messages',ROOT/'adapters/marmot/messages.py');messages=importlib.util.module_from_spec(spec);spec.loader.exec_module(messages)

def enroll(instance,show,number,environ,authenticate=messages.authenticated):
    cfg=e.read(instance['transcription_config'])
    if cfg.get('paused') is not False or cfg['show']!=show:raise ValueError('Transcription is paused or this show is not configured')
    route={k:environ.get(v,'') for k,v in [('account','MARMOT_ACCOUNT_ID_HEX'),('group','MARMOT_GROUP_ID_HEX'),('sender','MARMOT_SENDER_ACCOUNT_ID_HEX'),('message_id','MARMOT_MESSAGE_ID_HEX')]}
    key=hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest();request=Path(instance['state_root'])/'inbox'/(key+'.json');saved=e.read(request)
    incoming=authenticate(instance,environ,saved['incoming']['text'])
    if incoming!=saved['incoming'] or incoming['group']!=cfg['group_id_hex']:raise ValueError('Task differs from its authenticated paired conversation')
    binding=saved['route'];identifier=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest();routing=e.read(Path(instance['state_root'])/'routing'/(identifier+'.json'))
    if routing['binding']!=binding or routing['selected']!=e.key(show,number):raise ValueError('Select the requested episode first with podcast new/use SHOW NUMBER')
    catalog=e.read(cfg['source_catalog'])
    if catalog['show']!=show:raise ValueError('Source catalog show differs')
    source=catalog['episodes'].get(number)
    if not source:raise ValueError('This episode has no imported source clearance; do not substitute or remove an ad hold')
    episode=source['episode'];clearance=source['clearance']
    if episode['number']!=number or clearance.get('audit_complete') is not True or clearance['final_audio_sha256']!=episode['final_audio_sha256']:raise ValueError('Source clearance does not bind the exact selected episode')
    config_path=Path(instance['transcription_config'])
    with config_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        cfg=e.read(config_path)
        if cfg.get('paused') is not False:raise ValueError('Transcription was paused')
        with e.journal(Path(instance['work_root'])) as (_,data):
            item=e.episode(data,show,number)
            if item.get('transcription'):return item['transcription']
            directory=Path(item['directory']);folder=directory/'transcript';episode_path=directory/'transcription-episode.json';task_path=directory/'transcription-task.json'
            if folder.exists() or episode_path.exists() or task_path.exists():raise ValueError('Earlier intake artifacts need inspection; do not overwrite them')
            task=dict(source='explicit-user-task',operation='transcript',show=show,episode=number,episode_guid=episode['guid'],directory=str(folder),config=str(config_path),authorization=dict(request_path=str(request),incoming_sha256=e.digest(incoming),message_id=incoming['message_id'],sender=incoming['sender']))
            e.save(episode_path,episode);e.save(task_path,task)
            cfg['episodes'][episode['guid']]=dict(number=number,final_audio_sha256=episode['final_audio_sha256'],source_clearance=clearance,force_feedback=False)
            e.save(config_path,cfg);item['transcription']=dict(directory=str(folder),task=str(task_path),episode=str(episode_path))
            return item['transcription']

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--instance',type=Path,required=True);p.add_argument('--show',required=True);p.add_argument('--episode',required=True)
    a=p.parse_args();print(json.dumps(enroll(e.read(a.instance),a.show,a.episode,os.environ),indent=2))
if __name__=='__main__':failures.cli(main,'transcript')
