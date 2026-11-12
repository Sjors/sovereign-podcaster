#!/usr/bin/env python3
"""Private task-scoped token estimates; no inference, billing key or publication."""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import os
from pathlib import Path
import episodes as e


@contextmanager
def locked(root):
    root=e.private_root(root)
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield root


def begin(context, identifier, kind):
    e.slug(identifier);e.slug(kind)
    if identifier=='active':raise ValueError('Cost task ID is reserved')
    with locked(context['root']) as root:
        active=root/'active.json';path=root/(identifier+'.json')
        if active.exists() and e.read(active)['id']!=identifier:raise ValueError('Finish the active cost task before starting another')
        if path.exists():
            old=e.read(path)
            if old['kind']!=kind or old['session_id']!=context['session_id'] or old['state']!='active':raise ValueError('Cost task ID already belongs to another or closed scope')
            return old
        value=dict(schema=1,id=identifier,kind=kind,state='active',created_at=e.now(),session_id=context['session_id'],model=context['model'],
                   baseline_turn_ids=context['baseline_turn_ids'],turns={},pricing=context.get('pricing'))
        e.save(path,value);e.save(active,dict(id=identifier));return value


def finish(context, identifier):
    with locked(context['root']) as root:
        path=root/(e.slug(identifier)+'.json');value=e.read(path)
        if value['session_id']!=context['session_id']:raise ValueError('Cost task session differs')
        if value['state']=='active':value['state']='closing';e.save(path,value)
        return value


def summary(value):
    totals=dict(input_tokens=0,cached_input_tokens=0,output_tokens=0)
    unknown=[]
    for identifier,turn in value['turns'].items():
        u=turn.get('usage') or {};cached=u.get('input_tokens_details') or {};c=cached.get('cached_tokens')
        counts=[u.get('input_tokens'),c,u.get('output_tokens')]
        if any(type(n) is not int or n<0 for n in counts) or c>u.get('input_tokens',0):unknown.append(identifier);continue
        for key,n in zip(totals,counts):totals[key]+=n
    pricing=value.get('pricing');amount=None
    if pricing:
        rates=[Decimal(str(pricing[k])) for k in ('input','cached_input','output')]
        if any(not r.is_finite() or r<0 for r in rates):raise ValueError('Invalid token prices')
        amount=str(((totals['input_tokens']-totals['cached_input_tokens'])*rates[0]+totals['cached_input_tokens']*rates[1]+totals['output_tokens']*rates[2])/Decimal(1000000))
    return dict(tokens=totals,turns=len(value['turns']),missing_usage_turn_ids=unknown,
                estimated_model_usd=amount,complete=bool(value['turns']) and not unknown and pricing is not None,
                billed_cost=None,excludes=['local compute','hosting','tools and third-party services','cache-write charges'])


def notice(value):
    s=value['summary'];amount=s['estimated_model_usd']
    if amount is None:return 'Task cost: unavailable (token pricing not configured).'
    label='Estimated model cost' if s['complete'] else 'Partial model cost estimate (usage missing)'
    return f'{label}: US${Decimal(amount):.2f}.'


def observe(root, session_id, turns, close=True):
    """Called after a turn, including failed turns. Never adds session aggregates."""
    with locked(root) as root:
        active=root/'active.json'
        if not active.exists():return None
        path=root/(e.slug(e.read(active)['id'])+'.json');value=e.read(path)
        if value['session_id']!=session_id:raise ValueError('Cost task session differs')
        baseline=set(value['baseline_turn_ids'])
        for turn in turns:
            if turn['id'] not in baseline:
                # Multi-agent execution is disabled by this adapter. Keep unexpected
                # delegated turns visible, rather than silently discarding charges.
                value['turns'][turn['id']]={k:turn.get(k) for k in ('id','status','usage','subagent_id')}
        value['observed_at']=e.now();value['summary']=summary(value)
        closing=close and value['state']=='closing'
        if closing:value.update(state='closed',finished_at=e.now())
        e.save(path,value)
        if closing:active.unlink()
        return notice(value) if closing else None


def refresh(path, session_id, turns):
    """Refresh only already-attributed turns; later tasks cannot enter a closed report."""
    path=Path(path)
    with locked(path.parent):
        value=e.read(path)
        if value['session_id']!=session_id:raise ValueError('Cost task session differs')
        for turn in turns:
            if turn['id'] in value['turns']:value['turns'][turn['id']]={k:turn.get(k) for k in ('id','status','usage','subagent_id')}
        value['observed_at']=e.now();value['summary']=summary(value);e.save(path,value)
        return value


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['begin','finish']);p.add_argument('--id',required=True);p.add_argument('--kind')
    a=p.parse_args();context=e.read(os.environ['SP_COST_CONTEXT'])
    if a.action=='begin':
        if not a.kind:p.error('begin requires --kind')
        begin(context,a.id,a.kind);print('Cost task started; reuse this ID across handoffs.')
    else:finish(context,a.id);print('Cost report queued for after this model turn finishes.')

if __name__=='__main__':
    import failures
    failures.cli(main,'controller')
