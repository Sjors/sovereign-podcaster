#!/usr/bin/env python3
"""Inspect a stopped request and acknowledge its terminal outcome without replaying input."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('backend',HERE/'marmot-backend.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def reconcile(config,root,api,apply=False):
    root=root.resolve()
    if not root.is_relative_to(Path(config['state_root']).resolve()):raise ValueError('State must belong to this instance')
    active=list(root.glob('*.active.json'))
    if len(active)!=1:raise ValueError('Require exactly one unresolved request in the selected state directory')
    marker=active[0]
    with marker.with_name(marker.name.replace('.active.json','.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record=b.read(marker);cursor=root/'cursors'/(record['handle']+'.json');state=b.read(cursor)
        if record.get('session_id')!=state.get('session_id') or not state.get('session_id'):raise ValueError('Session identity is unresolved')
        folder=Path(record['folder']).resolve()
        if folder.parent!=root:raise ValueError('Unexpected request folder')
        pending=[r for r in state['requests'].values() if r.get('folder')==str(folder) and r['phase']=='pending']
        if len(pending)!=1:raise ValueError('Cannot identify the pending input')
        request=pending[0];turns=b.paged(api,'sessions/'+state['session_id']+'/turns')
        if any(t['status'] not in ('completed','failed','cancelled') for t in turns):raise ValueError('Provider still has active work; do not clear its checkpoint')
        baseline=request.get('baseline_turn_ids')
        if baseline is None:baseline=[r['turn_id'] for r in state['requests'].values() if r.get('turn_id')]
        new=[t for t in turns if t['id'] not in baseline and not t.get('subagent_id')]
        if len(new)!=1:raise ValueError('Cannot unambiguously identify the stopped turn')
        turn=new[0];items=b.paged(api,'sessions/'+state['session_id']+'/items')
        # The API may return tool output; keep it private and redact both key values.
        raw=json.dumps({'data':items})
        if state.get('provider','codex')=='ppq':raw=api.clean(raw)
        else:
            keys=Path(config['openai_key_directory'])
            for name in ('application.key','environment.key'):raw=raw.replace(b.transport.private_read(keys/name).strip(),'[redacted-key]')
        b.transport.save(folder/'items.json',json.loads(raw));b.transport.save(folder/'recovered-turns.json',{'data':turns})
        result={'session_id':state['session_id'],'turn_id':turn['id'],'status':turn['status'],'usage':turn.get('usage'),'applied':apply}
        if apply:
            request.update(phase=turn['status'],turn_id=turn['id'],usage=turn.get('usage'),reconciled=True)
            if turn['status']=='completed':request['answer']=b.reply_for(items,turn['id'])
            b.transport.save(cursor,state);b.transport.save(folder/'reconciliation.json',result)
            marker.unlink()
        return result

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--instance',type=Path,required=True);p.add_argument('--state-root',type=Path,required=True)
    p.add_argument('--acknowledge-terminal',action='store_true',help='After inspecting saved effects, permit a new input; never resend the old input')
    a=p.parse_args();cfg=b.read(a.instance);_,api,_=b.model_client(dict(cfg,state_root=str(a.state_root)))
    print(json.dumps(reconcile(cfg,a.state_root,api,a.acknowledge_terminal),indent=2))
if __name__=='__main__':main()
