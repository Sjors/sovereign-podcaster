#!/usr/bin/env python3
"""Private failure reports with UUID-only chat notices and local lookup."""
import argparse
import errno
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import traceback
import uuid
import episodes as e

ROOT=Path(__file__).resolve().parents[1]
STAGES={'prepare','render','package','register','verify','fixture','transcript','chapters','controller','draft-upload','draft-cleanup','nostr','youtube-private','youtube-public','unknown'}
COMPONENTS={'ffmpeg','ffprobe','fc-match','PIL','googleapiclient','google_auth_oauthlib','google','coincurve','bech32','websocket','audio','transcript','slides','portraits','revision','configuration','maintenance-control','OpenAI-application-key','OpenAI-environment-key','executor','storage','unknown'}
CODES={
 'missing-tool':('A required executable is missing.','Install the documented dependency in the isolated account/runtime; then inspect and resume the saved stage.'),
 'missing-module':('A required Python module is missing.','Use the documented Python runtime and dependency pins; do not copy another account\'s environment.'),
 'missing-input':('A required input or saved artifact is missing.','Provide the selected episode\'s missing material, or restore its saved artifact. Do not choose a substitute episode.'),
 'configuration-required':('Required configuration is missing or invalid.','Check the private instance configuration and production runbook; keep credentials out of chat.'),
 'authorization-required':('Required access, approval or maintenance permission is unavailable.','Inspect the intended account, exact review and operator control. Do not bypass the guard or broaden permissions.'),
 'permission-denied':('The isolated account cannot access a required resource.','Inspect the exact local permission/access check privately; grant only the minimum needed access.'),
 'storage-full':('The artifact filesystem has insufficient space.','Check free space and retain original media, current revisions and unresolved receipts.'),
 'uncertain-outcome':('Earlier work has an unresolved outcome.','Inspect saved input, provider receipts and remote state before retrying. Do not create a replacement upload or announcement.'),
 'provider-unavailable':('The API/provider is unavailable or rejected the request.','Check the account/provider status and quota privately. Inspect saved receipts before an explicit retry.'),
 'interrupted':('The task was interrupted.','Inspect the saved job/stage and any remaining worker before resuming.'),
 'task-failed':('The stage failed; its safe diagnostic did not identify a missing prerequisite.','Inspect the private log and saved state locally. Share only a reviewed, redacted excerpt if further diagnosis needs it.')}

def safe_id(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',value):return 'unspecified'
    if value.lower().startswith(('sk-','sk_','nsec1','bearer')) or re.fullmatch('[0-9a-fA-F]{64}',value):return 'unspecified'
    return value

def source_revision():
    try:
        result=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],stderr=subprocess.DEVNULL,text=True,timeout=3).strip()
        return result if re.fullmatch('[0-9a-f]{40,64}',result) else 'unknown'
    except (OSError,subprocess.SubprocessError):return 'unknown'

def report(code='task-failed',stage='unknown',component='unknown',context=None,effects='unknown',error=None):
    if code not in CODES or stage not in STAGES or component not in COMPONENTS or effects not in ('not-started','unknown'):raise ValueError('Unknown failure report field')
    context=context or {}
    frames=[]
    if error:
        for f in traceback.extract_tb(error.__traceback__):
            path=Path(f.filename)
            if path.is_relative_to(ROOT):frames.append(f'{path.relative_to(ROOT)}:{f.lineno}')
    return dict(schema=1,id=str(uuid.uuid4()),utc=e.now(),code=code,stage=stage,component=component,
        context={k:safe_id(context[k]) for k in ('show','episode','revision','job') if k in context},
        source_revision=source_revision(),python='.'.join(map(str,sys.version_info[:3])),effects=effects,
        exception_type=safe_id(type(error).__name__) if error else 'unspecified',frames=frames[-4:])

def from_exception(error,stage='unknown',context=None,effects='unknown'):
    code='task-failed';component='unknown'
    status=getattr(getattr(error,'resp',None),'status',None) or getattr(error,'code',None)
    status=status if type(status) is int and 100<=status<=599 else None
    if isinstance(error,RuntimeError):
        match=re.search(r'API HTTP ([1-5][0-9]{2})\b',str(error))
        if match:status=int(match[1])
    if status is not None:code='authorization-required' if status in (401,403) else 'provider-unavailable'
    elif isinstance(error,json.JSONDecodeError):code='configuration-required';component='configuration'
    elif isinstance(error,ModuleNotFoundError):
        code='missing-module';name=(error.name or '').split('.')[0];component=name if name in COMPONENTS else 'unknown'
    elif isinstance(error,FileNotFoundError):
        name=Path(error.filename or '').name
        if name in ('ffmpeg','ffprobe','fc-match'):code='missing-tool';component=name
        elif name in ('application.key','environment.key'):code='configuration-required';component='OpenAI-'+name.replace('.key','-key')
        elif name in ('prepared.json','render.json'):code='missing-input';component='revision'
        elif Path(name).suffix.lower() in ('.wav','.mp3','.flac','.m4a'):code='missing-input';component='audio'
        elif Path(name).suffix.lower()=='.vtt':code='missing-input';component='transcript'
        elif name in ('config.json','publication.json','podcaster-instance.json'):code='configuration-required';component='configuration'
        else:code='missing-input'
    elif isinstance(error,PermissionError):code='permission-denied'
    elif isinstance(error,OSError) and error.errno in (errno.ENOSPC,errno.EDQUOT):code='storage-full';component='storage'
    elif isinstance(error,(KeyboardInterrupt,InterruptedError)):code='interrupted'
    # Only use exception text internally for fixed classification. It never
    # becomes a report field or chat text, including when it contains a key/URL.
    elif isinstance(error,(ValueError,RuntimeError,KeyError)):
        text=str(error).lower()
        if any(s in text for s in ('uncertain','unresolved','inspect before retry','pending/uncertain')):code='uncertain-outcome'
        elif any(s in text for s in ('maintenance guard','maintenance control')):code='authorization-required';component='maintenance-control'
        elif any(s in text for s in ('approval','trusted contact','authenticated incoming','authorization','api http 401','api http 403')):code='authorization-required'
        elif isinstance(error,KeyError) or any(s in text for s in ('configuration','configur','spending-limit policy')):code='configuration-required';component='configuration'
    value=report(code,stage,component,context,effects,error)
    if status is not None:value['http_status']=status
    return value

def format_report(value):
    # Read only structured allowlisted fields, even for a tampered report file.
    code=value['code'];stage=value['stage'];component=value['component']
    if value.get('schema')!=1 or code not in CODES or stage not in STAGES or component not in COMPONENTS:raise ValueError('Invalid failure report')
    summary,action=CODES[code]
    lines=['PODCAST FAILURE REPORT',f'Reference: {safe_id(value["id"])}',f'UTC: {value["utc"]}' if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})',value.get('utc','')) else 'UTC: unavailable',f'Stage: {stage}',f'Code: {code}',f'Component: {component}']
    for k in ('show','episode','revision','job'):
        if k in value.get('context',{}):lines.append(k.capitalize()+': '+safe_id(value['context'][k]))
    revision=value.get('source_revision','unknown');revision=revision if re.fullmatch('[0-9a-f]{40,64}',revision) else 'unknown'
    python=value.get('python','unknown');python=python if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',python) else 'unknown'
    if value.get('exception_type','unspecified')!='unspecified':lines.append('Exception: '+safe_id(value['exception_type']))
    lines.append('Python: '+python)
    if type(value.get('http_status')) is int and 100<=value['http_status']<=599:lines.append('HTTP status: '+str(value['http_status']))
    if code=='missing-tool' and component in ('ffmpeg','ffprobe','fc-match'):
        package='fontconfig' if component=='fc-match' else 'ffmpeg'
        action='Ask the administrator to install apt package '+package+'; keep the agent without sudo. Inspect the saved stage before resuming.'
    lines += ['Source: '+revision,'Problem: '+summary,'Next: '+action]
    lines.append('External actions: not started.' if value.get('effects')=='not-started' else 'External actions: may be partial. Inspect saved receipts before retrying.')
    lines.append('Private diagnostic record. Share only its report UUID in chat.')
    return '\n'.join(lines)

def store_root():
    return Path.home()/'.local/share/sovereign-podcaster/failures'

def reference(value):
    # Existing 12-hex references remain readable; new reports use full UUID4s.
    if isinstance(value,str) and re.fullmatch('[0-9a-f]{12}',value):return value
    try:parsed=uuid.UUID(value)
    except (ValueError,TypeError,AttributeError):raise ValueError('Use a complete report UUID') from None
    if str(parsed)!=value or parsed.version!=4:raise ValueError('Use a complete lowercase report UUID4')
    return value

def format_notice(value,stored=True):
    if not stored:return 'Podcast task stopped. The private failure report could not be saved; local inspection is required.'
    identifier=reference(value['id']);label='Report UUID: ' if len(identifier)==36 else 'Report reference: '
    return 'Podcast task needs attention.\n'+label+identifier+'\nGive this reference to the maintainer for diagnosis.'

def private_json(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600:raise ValueError('Expected a private owned report file')
        return json.load(f)

def persist(value,path=None):
    identifier=reference(value['id']);format_report(value)
    path=Path(path).absolute() if path else store_root()/(identifier+'.json')
    e.private_root(path.parent)
    if path.exists():
        value=private_json(path);identifier=reference(value['id']);format_report(value)
    else:e.save(path,value)
    store=e.private_root(store_root())
    index=e.private_root(store/'index')/(identifier+'.json')
    entry=dict(schema=1,report=value,record_path=str(path))
    if index.exists():
        old=private_json(index)
        if old['report']!=value or old['record_path']!=str(path):raise ValueError('Report reference already belongs to another record')
    else:e.save(index,entry)
    return value

def lookup(identifier):
    identifier=reference(identifier)
    entry=private_json(store_root()/'index'/(identifier+'.json'))
    if entry.get('schema')!=1 or entry['report']['id']!=identifier:raise ValueError('Report index does not match the reference')
    format_report(entry['report'])
    # A stale or replaced original record must not be silently diagnosed instead.
    if private_json(Path(entry['record_path']))!=entry['report']:raise ValueError('Original report differs from its indexed snapshot')
    return entry

def save_notice(value,path=None):
    try:value=persist(value,path)
    except (OSError,ValueError):return format_notice(value,stored=False)
    return format_notice(value)

def emit_exception(error,stage='unknown',context=None):
    value=from_exception(error,stage,context)
    print(save_notice(value,os.environ.get('SP_FAILURE_REPORT')),file=sys.stderr);return value

def cli(main,stage='unknown'):
    try:main()
    except (Exception,KeyboardInterrupt) as error:
        emit_exception(error,stage);raise SystemExit(130 if isinstance(error,KeyboardInterrupt) else 1) from None

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('create');q.add_argument('--code',choices=sorted(CODES),required=True);q.add_argument('--stage',choices=sorted(STAGES),required=True);q.add_argument('--component',choices=sorted(COMPONENTS),default='unknown');q.add_argument('--out',type=Path)
    for name in ('show','episode','revision','job'):q.add_argument('--'+name)
    q=s.add_parser('show');q.add_argument('report',type=Path)
    q=s.add_parser('lookup');q.add_argument('uuid');q.add_argument('--json',action='store_true')
    a=p.parse_args();os.umask(0o077)
    if a.action=='lookup':
        entry=lookup(a.uuid)
        print(json.dumps(entry,indent=2) if a.json else format_report(entry['report'])+'\nLocal record: '+entry['record_path']);return
    if a.action=='show':print(format_report(private_json(a.report)));return
    else:value=persist(report(a.code,a.stage,a.component,{k:getattr(a,k) for k in ('show','episode','revision','job') if getattr(a,k)}),a.out)
    print(format_notice(value))
if __name__=='__main__':main()
