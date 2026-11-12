#!/usr/bin/env python3
"""Local episode journal and receipt-bound Blossom draft lifecycle. No model calls."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent


def now():return datetime.now(timezone.utc).isoformat()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def slug(value):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value):raise ValueError('Use a short show/episode/revision ID containing letters, numbers, _ or -')
    return value

def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def file_record(path):
    path=Path(path).expanduser().resolve(strict=True)
    if not path.is_file():raise ValueError('Expected a regular artifact file')
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'sha256':sha,'size':path.stat().st_size}

def private_root(path):
    path=Path(path).expanduser().absolute()
    for p in (path,*path.parents):
        if p.is_symlink():raise ValueError('State path must not contain symlinks')
        if (p/'.git').is_file() or (p/'.git/HEAD').is_file():raise ValueError('Episode state belongs outside Git')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    st=path.stat()
    if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:raise ValueError('Work root must be owned by this user and mode 0700')
    return path

@contextmanager
def journal(root):
    root=private_root(root)
    with (root/'.episodes.lock').open('a') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        path=root/'episodes.json'
        if path.is_symlink():raise ValueError('State symlink refused')
        data=read(path) if path.exists() else {'schema':1,'episodes':{}}
        yield root,data
        save(path,data)

def key(show,episode):return slug(show)+'/'+slug(episode)
def episode(data,show,identifier):
    return data['episodes'][key(show,identifier)]

def initialize(root,data,show,identifier):
    k=key(show,identifier)
    if k in data['episodes']:raise ValueError('Episode already exists; resume it instead')
    folder=root/'episodes'/show/identifier;folder.mkdir(parents=True,mode=0o700)
    item={'show':show,'episode':identifier,'created_at':now(),'directory':str(folder),
          'revisions':{},'drafts':{},'approvals':[],'publications':[]}
    data['episodes'][k]=item
    return item

def revision(item,identifier,manifest):
    slug(identifier)
    if identifier in item['revisions']:raise ValueError('Revision already exists; use a new ID')
    if not {'video','fallback','thumbnail','metadata'}<=manifest.keys():raise ValueError('Manifest requires video, fallback, thumbnail and metadata paths; captions are optional')
    if set(manifest)-{'video','fallback','thumbnail','metadata','captions','slides','transcript','audio','nostr_metadata','nostr_bundle'}:raise ValueError('Unknown artifact role')
    files={name:file_record(path) for name,path in manifest.items()}
    r={'id':identifier,'created_at':now(),'files':files,'manifest_sha256':digest(files)}
    r['nostr_manifest_sha256']=digest({k:v for k,v in files.items() if k in ('video','fallback','nostr_metadata','nostr_bundle')})
    item['revisions'][identifier]=r;item['current_revision']=identifier
    return r

def verified_revision(item,identifier):
    r=item['revisions'][identifier]
    if any(file_record(v['path'])!=v for v in r['files'].values()):raise ValueError('Revision bytes changed; register a new revision and obtain fresh approvals')
    return r

def evidence_copy(item,source,label):
    source=Path(source);record=file_record(source)
    # Evidence may be private chat text; never send its content to a model/API here.
    folder=Path(item['directory'])/'evidence';folder.mkdir(mode=0o700,exist_ok=True)
    path=folder/(label+'-'+record['sha256'])
    if not path.exists():
        with path.open('xb') as f:os.chmod(path,0o600);f.write(source.read_bytes())
    if file_record(path)['sha256']!=record['sha256']:raise ValueError('Evidence changed during snapshot')
    return file_record(path)

def published(item,stage,manifest):
    return next((p for p in reversed(item['publications']) if p['stage']==stage and p['manifest_sha256']==manifest),None)

def approve(item,identifier,scope,evidence):
    r=verified_revision(item,identifier)
    sha=r['nostr_manifest_sha256'] if scope=='nostr' else r['manifest_sha256']
    private=published(item,'youtube-private',r['manifest_sha256'])
    if scope=='youtube-public' and private is None:raise ValueError('Inspect the private YouTube upload before recording public approval')
    a={'scope':scope,'revision':identifier,'manifest_sha256':sha,'recorded_at':now(),
       'evidence':evidence_copy(item,evidence,'approval')}
    if private:a['youtube_video_id']=private['receipt']['video_id']
    item['approvals'].append(a);return a

def approval(item,scope,manifest):
    return next((a for a in reversed(item['approvals']) if a['scope']==scope and a['manifest_sha256']==manifest),None)

def record_publication(item,identifier,stage,receipt_path):
    r=verified_revision(item,identifier);sha=r['nostr_manifest_sha256'] if stage=='nostr' else r['manifest_sha256'];receipt=read(receipt_path)
    if receipt.get('manifest_sha256')!=sha or receipt.get('verified') is not True:raise ValueError('Publication receipt requires verified readback bound to this exact manifest')
    if stage=='nostr':
        if not approval(item,'nostr',sha):raise ValueError('Exact Nostr approval is missing')
        from video.nostr import metadata
        # Legacy revisions without native metadata retain the original requirement.
        meta=metadata(read(r['files']['nostr_metadata']['path'])) if 'nostr_metadata' in r['files'] else {}
        skip=meta.get('announce') is False
        fields=('video_event_id',) if skip else ('video_event_id','announcement_event_id')
        if skip and (receipt.get('announcement_skipped') is not True or receipt.get('announcement_event_id')):raise ValueError('The reviewed packet forbids an announcement')
        if not skip and receipt.get('announcement_skipped'):raise ValueError('Announcement omission was not reviewed')
        if not all(re.fullmatch('[0-9a-f]{64}',receipt.get(k,'') or '') for k in fields) or not receipt.get('blobs'):raise ValueError('Record the reviewed video/announcement policy and all final storage blobs')
        for b in receipt['blobs']:
            import blossom
            if blossom.normalize_server(b['server'])!=b['server']:raise ValueError('Final blob server must be a canonical HTTPS origin')
            if not re.fullmatch('[0-9a-f]{64}',b['sha256']):raise ValueError('Invalid final blob hash')
    else:
        if not published(item,'nostr',r['nostr_manifest_sha256']):raise ValueError('Nostr publication must precede YouTube upload')
        if not receipt.get('video_id') or not receipt.get('channel_id'):raise ValueError('YouTube receipt requires video and channel IDs')
        if receipt.get('privacy_status')!=('private' if stage=='youtube-private' else 'public'):raise ValueError('Unexpected YouTube visibility')
        if stage=='youtube-public':
            a=approval(item,'youtube-public',sha);p=published(item,'youtube-private',sha)
            if not a or not p or a.get('youtube_video_id')!=receipt['video_id'] or p['receipt']['channel_id']!=receipt['channel_id']:raise ValueError('Public approval must bind the same private video ID/channel and reviewed packet')
    result={'stage':stage,'manifest_sha256':sha,'recorded_at':now(),'receipt':receipt,
            'evidence':evidence_copy(item,receipt_path,'publication')}
    item['publications'].append(result);return result

def complete(item):
    if 'current_revision' not in item:return False
    r=item['revisions'][item['current_revision']]
    return bool(published(item,'nostr',r['nostr_manifest_sha256']) and published(item,'youtube-public',r['manifest_sha256']))

def cleanup_plan(data,item):
    if not complete(item):raise ValueError('Draft cleanup waits for verified Nostr and public YouTube publication of the current revision')
    protected=set()
    for other in data['episodes'].values():
        for p in other['publications']:
            for b in p['receipt'].get('blobs',[]):protected.add((b['server'].rstrip('/'),b['sha256']))
        if other is not item and not complete(other):
            for d in other['drafts'].values():protected.add((d['server'],d['sha256']))
    result=[]
    for identifier,d in item['drafts'].items():
        import blossom
        receipt=Path(d['receipt']);s=blossom.receipt_read(receipt) if receipt.exists() else {}
        if s and (s.get('server')!=d['server'] or s.get('sha256')!=d['sha256']):raise ValueError('Draft receipt no longer matches its registered server/hash')
        if (d['server'],d['sha256']) in protected:reason='retained-reference'
        elif s.get('state')=='deleted':reason='already-deleted'
        elif s.get('existed_before') is not False or s.get('upload_acknowledged') is not True or s.get('reused'):reason='retained-reused-or-uncertain'
        else:reason='delete'
        result.append(dict(d,id=identifier,decision=reason))
    return result

def guard(config,action):
    """Operator-maintained pause/action state; not a same-UID security boundary."""
    path=Path(config['maintenance_guard']).absolute()
    if path.is_symlink() or not path.is_file():raise ValueError('Maintenance control is missing')
    state=read(path)
    if state.get('schema')!=1 or state.get('allowed') is not True or action not in state.get('actions',[]):raise ValueError('Maintenance control does not permit this action')


def blossom_args(config,server,receipt,action):
    opts=config.get('server_options',{}).get(server,{})
    cmd=[config['nostr_python'],str(HERE/'blossom.py'),action,'--server',server,
         '--identity',config['identity_file'],'--expected-pubkey',config['expected_pubkey'],
         '--receipt',str(receipt),'--auth-encoding',opts.get('auth_encoding','base64url')]
    for origin in opts.get('read_redirect_origins',[]):cmd+=['--read-redirect-origin',origin]
    return cmd

def upload(root,data,item,identifier,config,evidence,apply):
    import blossom
    from review_media import inspect_fallback
    r=verified_revision(item,identifier);asset=r['files']['fallback']
    inspect_fallback(Path(asset['path']))
    plans=[]
    for raw in config['draft_servers']:
        server=blossom.normalize_server(raw);did=identifier+'-'+digest(server)[:16]
        receipt=Path(item['directory'])/'drafts'/(did+'.json');receipt.parent.mkdir(mode=0o700,exist_ok=True)
        cmd=blossom_args(config,server,receipt,'upload')+['--file',asset['path'],'--mime','video/mp4']
        for origin in config['playback_origins']:cmd+=['--origin',origin]
        if not apply:plans.append({'server':server,'sha256':asset['sha256'],'receipt':str(receipt),'dry_run':True});continue
        if not evidence:raise ValueError('An upload needs the authorized episode request/review evidence')
        guard(config,'draft-upload')
        if did not in item['drafts']:
            item['drafts'][did]={'revision':identifier,'server':server,'sha256':asset['sha256'],'receipt':str(receipt),
                'authorization':evidence_copy(item,evidence,'draft-upload'),'registered_at':now()}
        elif any(item['drafts'][did][k]!=v for k,v in {'revision':identifier,'server':server,'sha256':asset['sha256'],'receipt':str(receipt)}.items()):raise ValueError('Existing draft binding differs')
        save(root/'episodes.json',data) # register before any external side effect
        verified_revision(item,identifier);guard(config,'draft-upload')
        subprocess.run(cmd+['--apply'],check=True,stdout=subprocess.DEVNULL)
        plans.append(read(receipt))
    return plans

def cleanup(root,data,item,config,apply):
    verified_revision(item,item['current_revision'])
    plan=cleanup_plan(data,item)
    if apply:
        for d in plan:
            if d['decision']!='delete':continue
            guard(config,'draft-delete')
            # Low-level receipt binding rechecks identity, origin and new-upload ownership.
            subprocess.run(blossom_args(config,d['server'],d['receipt'],'delete')+['--apply'],check=True,stdout=subprocess.DEVNULL)
        item['last_cleanup_at']=now()
    return cleanup_plan(data,item) if apply else plan

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    for name in ('init','status','revision','approve','record','draft-upload','draft-cleanup'):
        q=sub.add_parser(name);q.add_argument('--show',required=True);q.add_argument('--episode',required=True)
        if name in ('revision','approve','record','draft-upload'):q.add_argument('--revision',required=True)
        if name=='revision':q.add_argument('--manifest',type=Path,required=True)
        if name=='approve':q.add_argument('--scope',choices=['nostr','youtube-public'],required=True);q.add_argument('--evidence',type=Path,required=True)
        if name=='record':q.add_argument('--stage',choices=['nostr','youtube-private','youtube-public'],required=True);q.add_argument('--receipt',type=Path,required=True)
        if name.startswith('draft-'):q.add_argument('--config',type=Path,required=True);q.add_argument('--apply',action='store_true')
        if name=='draft-upload':q.add_argument('--authorization',type=Path)
    args=p.parse_args();os.umask(0o077)
    with journal(args.root) as (root,data):
        if args.command=='list':result=[{'show':x['show'],'episode':x['episode'],'current_revision':x.get('current_revision'),'fully_published':bool(complete(x))} for x in data['episodes'].values()]
        elif args.command=='init':result=initialize(root,data,args.show,args.episode)
        else:
            item=episode(data,args.show,args.episode)
            if args.command=='status':result=item
            elif args.command=='revision':result=revision(item,args.revision,read(args.manifest))
            elif args.command=='approve':result=approve(item,args.revision,args.scope,args.evidence)
            elif args.command=='record':result=record_publication(item,args.revision,args.stage,args.receipt)
            elif args.command=='draft-upload':result=upload(root,data,item,args.revision,read(args.config),args.authorization,args.apply)
            else:result=cleanup(root,data,item,read(args.config),args.apply)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    import failures
    stage=next((x for x in sys.argv[1:] if x in ('draft-upload','draft-cleanup')),'unknown')
    failures.cli(main,stage)
