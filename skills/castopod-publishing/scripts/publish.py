#!/usr/bin/env python3
"""Castopod episode transport over SSH. No narration or licensing defaults."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
import stat
import tempfile
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

CONFIG = Path.home() / '.config/castopod-publishing/config.json'

def ensure_database_writes_allowed(config):
    """Honor the operator's maintenance state. Operator/executor share this UID."""
    value=config.get('maintenance_pause')
    if not isinstance(value,str) or not value.startswith('/'):
        raise RuntimeError('Configure an absolute maintenance_pause file before writes')
    path=Path(value)
    try:
        if path.is_symlink() or not path.is_file():raise RuntimeError('Required maintenance pause file is unavailable')
        paused=json.loads(path.read_text()).get('paused')
    except (OSError,ValueError,AttributeError) as exc:
        raise RuntimeError('Cannot verify Castopod maintenance pause; refusing to publish') from exc
    if paused is not False:
        raise RuntimeError('Castopod writes are paused or their status is unknown; user resume required')


def private_directory(path):
    path=Path(path).expanduser().absolute()
    for item in (path,*path.parents):
        if item.is_symlink() or (item/'.git').is_file() or (item/'.git/HEAD').is_file():
            raise ValueError('Private state must be outside Git and contain no symlink components')
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.stat().st_uid!=os.getuid() or stat.S_IMODE(path.stat().st_mode)!=0o700:
        raise ValueError('Private state directory must be owned by this user with mode 0700')
    return path


def save(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o600);json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def private_read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600:
            raise ValueError('Private config/receipt must be an owned regular file with mode 0600')
        return json.load(f)


@contextmanager
def episode_lock(config,podcast,slug):
    root=private_directory(config.get('state_dir',Path.home()/'.local/state/sovereign-podcaster/castopod'))
    binding=json.dumps([config.get('transport','ssh'),config.get('ssh'),config['app'],podcast,slug])
    path=root/(hashlib.sha256(binding.encode()).hexdigest()+'.lock')
    with path.open('a') as lock:
        os.chmod(path,0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another operation is working on this episode') from None
        yield


def load_config(path=CONFIG):
    config = private_read(path)
    if not isinstance(config,dict):raise ValueError('Instance configuration must be a JSON object')
    for key in ('app', 'user', 'incoming', 'cli'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f'Missing config value: {key}')
    if config.get('transport','ssh') not in ('ssh','local'):raise ValueError('transport must be ssh or local')
    if config.get('transport','ssh')=='ssh' and (not isinstance(config.get('ssh'),str) or not re.fullmatch(r'[A-Za-z0-9_@.-]+', config['ssh']) or config['ssh'].startswith('-')):
        raise ValueError('ssh must be a host alias or user@host')
    for key in ('app', 'incoming', 'cli'):
        if not config[key].startswith('/'):
            raise ValueError(f'{key} must be an absolute server path')
    if 'php_bin' in config and (not isinstance(config['php_bin'],str) or not config['php_bin']):raise ValueError('php_bin must be a command or executable path')
    for key in ('ssh_config','identity_file','maintenance_pause','state_dir'):
        if key in config and (not isinstance(config[key],str) or not config[key].startswith('/')):raise ValueError(key+' must be an absolute path')
    return config


def command(config, helper, podcast=None, slug=None, **options):
    args = [config.get('php_bin','php'), f"{config['cli']}/{helper}", f"--app={config['app']}",
            f"--user={config['user']}"]
    if podcast is not None:
        args.append(f'--podcast={podcast}')
    if slug is not None:
        args.append(f'--slug={slug}')
    for key, value in options.items():
        key = key.replace('_', '-')
        if value is True:
            args.append(f'--{key}')
        elif value is not None and value is not False:
            args.append(f'--{key}={value}')
    return shlex.join(args)


def transport_args(config, remote):
    if config.get('transport','ssh')=='local':return ['/bin/bash','-c',remote]
    args=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','IdentitiesOnly=yes',
          '-o','IdentityAgent=none','-o','ForwardAgent=no','-o','ClearAllForwardings=yes',
          '-o','ControlMaster=no','-o','ControlPath=none','-o','StrictHostKeyChecking=yes']
    if config.get('ssh_config'):args+=['-F',config['ssh_config']]
    if config.get('identity_file'):args+=['-i',config['identity_file']]
    return args+[config['ssh'],remote]


def remote_json(config, remote):
    result = subprocess.run(transport_args(config, remote), capture_output=True, text=True, check=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Expected JSON from server; raw output suppressed because it may contain private application details') from exc


def inspect(config, podcast=None, slug=None):
    result=remote_json(config, command(config, 'castopod-inspect.php', podcast, slug))
    if podcast is not None and result.get('podcast',{}).get('handle')!=podcast:raise RuntimeError('Readback selected a different podcast')
    if result.get('episode') and result['episode'].get('slug')!=slug:raise RuntimeError('Readback selected a different episode')
    return result


def _run_episode(config, podcast, action, slug, *, title=None, audio=None, notes=None, transcript=None, chapters=None, expected_state=None,
                season=None, number=None, publish=False, apply=False, receipt=None):
    if apply:
        ensure_database_writes_allowed(config)
    if not podcast or not re.fullmatch(r'[a-z0-9-]{1,128}', slug or ''):
        raise ValueError('An explicit podcast and a lowercase ASCII slug are required')
    if action not in ('create', 'update', 'publish'):
        raise ValueError('Action must be create, update or publish')
    if publish and action != 'create':
        raise ValueError('--publish is only used with create; use the publish action for a draft')
    if any(n is not None and n < 1 for n in (season, number)):
        raise ValueError('Season and number must be positive')
    if season is not None and action != 'create':
        raise ValueError('Season is currently supported only on create')
    if number is not None and action not in ('create','update'):
        raise ValueError('Episode number requires create or a conditional update')
    audio = Path(audio).resolve() if audio is not None else None
    notes = Path(notes).resolve() if notes is not None else None
    transcript = Path(transcript).resolve() if transcript is not None else None
    chapters = Path(chapters).resolve() if chapters is not None else None
    expected_state = Path(expected_state).resolve() if expected_state is not None else None
    if number is not None and action == 'update' and (expected_state is None or
            any(v is not None for v in (title,audio,notes,transcript,chapters))):
        raise ValueError('Episode numbering requires a separate number-only conditional update')
    if chapters is not None and any(value is not None for value in (audio, transcript, title)):
        raise ValueError('Chapter updates may change only chapters and notes')
    for path in (chapters, expected_state):
        if path is not None:
            if action != 'update' or not isinstance(json.loads(path.read_text()), dict):
                raise ValueError('Chapter/conditional attachments require update and JSON objects')
    if transcript is not None:
        if action != 'update' or not transcript.is_file() or transcript.suffix.lower() not in ('.vtt', '.srt'):
            raise ValueError('Attach an existing VTT or SRT transcript using update')
        transcript.read_text(encoding='utf-8')
    if audio is not None and (not audio.is_file() or audio.suffix.lower() not in ('.mp3', '.m4a')):
        raise ValueError('Audio must be an existing MP3 or M4A file')
    if notes is not None:
        notes.read_text(encoding='utf-8')  # fail before any upload
    if action == 'create' and (not title or audio is None or notes is None):
        raise ValueError('Create requires title, audio and a UTF-8 Markdown notes file')
    if action == 'update' and title is None and audio is None and notes is None and transcript is None and chapters is None and number is None:
        raise ValueError('Update requires title, audio, notes, transcript or chapters')
    if action == 'publish' and any(v is not None for v in (title, audio, notes)):
        raise ValueError('Publish changes status only; update the draft first')

    stage = f"{config['incoming'].rstrip('/')}/castopod-{uuid.uuid4().hex}"
    files = {}
    if audio is not None:
        files['audio'] = (audio, stage + '/audio' + audio.suffix.lower())
    if notes is not None:
        files['description_file'] = (notes, stage + '/notes.md')
    if transcript is not None:
        files['transcript'] = (transcript, stage + '/transcript' + transcript.suffix.lower())
    if chapters is not None:
        files['chapters'] = (chapters, stage + '/chapters.json')
    if expected_state is not None:
        files['expected_state'] = (expected_state, stage + '/expected-state.json')
    helper = {'create': 'castopod-publish-episode.php', 'update': 'castopod-update-episode.php',
              'publish': 'castopod-publish-draft.php'}[action]
    remote = command(config, helper, podcast, slug, title=title,
                     **{key: dst for key, (_, dst) in files.items()},
                     season=season, number=number, publish=publish)
    if not apply:
        return {'dry_run': True, 'transport':config.get('transport','ssh'), 'ssh': config.get('ssh'), 'podcast': podcast, 'action': action,
                'command': remote, 'uploads': {str(src): dst for src, dst in files.values()}}

    receipt['staging_directory']=stage
    before = inspect(config, podcast, slug)
    if not before.get('user_exists'):
        raise RuntimeError('Configured publishing user does not exist')
    if before.get('helper_api')!=1:raise RuntimeError('Install the matching reviewed server helper cohort before mutations; legacy helpers remain usable for reads')
    old = before['episode']
    for feature, supplied in (('chapters', chapters), ('conditional-update', expected_state),
                              ('episode-number',number if action == 'update' else None)):
        if supplied is not None and feature not in before.get('features', []):
            raise RuntimeError('Install the matching reviewed server helpers for '+feature)
    if expected_state is not None and old != json.loads(expected_state.read_text()):
        raise RuntimeError('Episode changed since inspection; inspect before retrying')
    if action == 'create' and old is not None:
        raise RuntimeError('Episode already exists; inspect or update it')
    if action != 'create' and old is None:
        raise RuntimeError('Episode not found in selected podcast')
    if (publish or action == 'publish') and before['podcast']['status'] != 'published':
        raise RuntimeError('Podcast must already be published')
    if action == 'publish' and old['status'] != 'draft':
        raise RuntimeError('Episode is not a draft; inspect instead of republishing')
    if action == 'update' and audio is not None:
        if Path(old['audio_file_key']).suffix.lower() != audio.suffix.lower():
            raise RuntimeError('Replacement must use the current audio container to preserve its URL')

    try:
        ensure_database_writes_allowed(config)
        receipt['phase']='staging';save(Path(receipt['_path']),{k:v for k,v in receipt.items() if k!='_path'})
        if files:
            subprocess.run(transport_args(config, 'mkdir -m 700 -- ' + shlex.quote(stage)), check=True)
            for src, dst in files.values():
                with src.open('rb') as stream:
                    subprocess.run(transport_args(config, 'cat > ' + shlex.quote(dst)), stdin=stream,
                                   capture_output=True, check=True)
        ensure_database_writes_allowed(config)
        for role,record in receipt['inputs'].items():
            if fingerprint(record['path'])!=record:raise RuntimeError('Input changed during staging; inspect retained files before continuing')
        receipt['phase']='applying';save(Path(receipt['_path']),{k:v for k,v in receipt.items() if k!='_path'})
        result = remote_json(config, remote)  # never automatically retry a mutation
        after = inspect(config, podcast, slug)
        episode = after['episode']
        if not episode or episode['id'] != result['id'] or episode['slug'] != slug:
            raise RuntimeError('Readback did not match the mutated episode')
        if old is not None and episode['id'] != old['id']:
            raise RuntimeError('Readback episode identity changed')
        wanted_status = 'published' if publish or action == 'publish' else ('draft' if action == 'create' else old['status'])
        if episode['status'] != wanted_status:
            raise RuntimeError(f"Readback status {episode['status']} differs from {wanted_status}")
        if title is not None and episode['title'] != title:
            raise RuntimeError('Readback title differs')
        if notes is not None and episode['description_sha256'] != hashlib.sha256(notes.read_bytes()).hexdigest():
            raise RuntimeError('Readback description differs')
        if audio is not None and episode['audio_file_size'] != audio.stat().st_size:
            raise RuntimeError('Readback audio size differs')
        if old is not None and episode['audio_url'] != old['audio_url']:
            raise RuntimeError('Existing audio URL changed')
        if number is not None and episode.get('number') != number:
            raise RuntimeError('Readback episode number differs')
        if number is not None and old is not None:
            for field,value in old.items():
                if field != 'number' and episode.get(field) != value:
                    raise RuntimeError('Episode numbering changed '+field)
        if chapters is not None:
            if not episode.get('chapters_id') or not episode.get('chapters_url'):
                raise RuntimeError('Chapter attachment missing in readback')
            for field, value in old.items():
                if field.startswith('chapters_') or (notes is not None and field.startswith('description_')):
                    continue
                if episode.get(field) != value:
                    raise RuntimeError('Chapter attachment changed '+field)
        if transcript is not None:
            if not episode.get('transcript_id') or not episode.get('transcript_url'):
                raise RuntimeError('Transcript attachment missing in readback')
            for field in ('guid', 'published_at', 'audio_file_key'):
                if episode.get(field) != old.get(field):
                    raise RuntimeError(f'Transcript attachment changed {field}')
            if audio is None and episode['audio_file_size'] != old['audio_file_size']:
                raise RuntimeError('Transcript attachment changed audio size')
            if title is None and episode['title'] != old['title']:
                raise RuntimeError('Transcript attachment changed title')
            if notes is None and episode['description_sha256'] != old['description_sha256']:
                raise RuntimeError('Transcript attachment changed description')
    except Exception:
        print('Operation not verified. Inspect this podcast/slug before retrying.' +
              (f' Staging, if created, retained at {stage}' if files else ''), file=sys.stderr)
        raise
    if files:
        # Remove only our exact staged files. Never recursively remove the incoming directory.
        cleanup = 'rm -f -- ' + shlex.join([dst for _, dst in files.values()]) + ' && rmdir -- ' + shlex.quote(stage)
        cleaned = subprocess.run(transport_args(config, cleanup), capture_output=True, text=True)
        if cleaned.returncode:
            print(f'Episode verified; staging cleanup failed at {stage}: see private server state', file=sys.stderr)
    return after


def fingerprint(path):
    path=Path(path).resolve(strict=True)
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'size':path.stat().st_size,'sha256':sha}


def run_episode(config,podcast,action,slug,*,receipt=None,**kwargs):
    if not kwargs.get('apply',False):return _run_episode(config,podcast,action,slug,**kwargs)
    _run_episode(config,podcast,action,slug,**dict(kwargs,apply=False)) # validate the offline request before journaling
    if receipt is None:raise ValueError('--apply requires a private --receipt path for inspection/recovery')
    path=Path(receipt).expanduser().absolute();private_directory(path.parent)
    file_options=('audio','notes','transcript','chapters','expected_state')
    inputs={name:fingerprint(kwargs[name]) for name in file_options if kwargs.get(name) is not None}
    packet={'target':{k:config.get(k) for k in ('transport','ssh','app','user','cli')},'podcast':podcast,'slug':slug,'action':action,
            'options':{k:v for k,v in kwargs.items() if k not in (*file_options,'apply')},'inputs':inputs}
    sha=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    with episode_lock(config,podcast,slug):
        if path.exists():
            saved=private_read(path)
            if saved['fingerprint']!=sha:raise RuntimeError('Receipt is bound to different input/target; refusing operation')
            if saved['phase']=='verified':return dict(saved['result'],receipt_replayed=True)
            raise RuntimeError('Prior receipt is unresolved; inspect remote effects and staging before any retry')
        ensure_database_writes_allowed(config)
        record={'fingerprint':sha,'packet':packet,'inputs':inputs,'phase':'prepared','created_at':datetime.now(timezone.utc).isoformat()}
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(record,f);f.flush();os.fsync(f.fileno())
        record['_path']=str(path)
        try:
            result=_run_episode(config,podcast,action,slug,receipt=record,**kwargs)
        except BaseException as error:
            record['error_type']=type(error).__name__
            save(path,{k:v for k,v in record.items() if k!='_path'});raise
        record.update(phase='verified',result=result,verified_at=datetime.now(timezone.utc).isoformat())
        save(path,{k:v for k,v in record.items() if k!='_path'});return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('action', choices=('list', 'inspect', 'create', 'update', 'publish'))
    parser.add_argument('--podcast', help='explicit destination handle, including for mutations')
    parser.add_argument('--slug')
    parser.add_argument('--title')
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--notes', type=Path, help='UTF-8 Markdown show notes')
    parser.add_argument('--transcript', type=Path, help='native VTT/SRT attachment to an existing episode')
    parser.add_argument('--chapters', type=Path, help='canonical Podcasting 2.0 JSON attachment using update')
    parser.add_argument('--expected-state', type=Path, help='exact inspected episode snapshot for a conditional update')
    parser.add_argument('--season', type=int)
    parser.add_argument('--number', type=int)
    parser.add_argument('--publish', action='store_true', help='publish on creation instead of creating a draft')
    parser.add_argument('--receipt',type=Path,help='Private durable operation receipt; required for --apply')
    parser.add_argument('--apply', action='store_true', help='execute the prepared mutation; default is offline dry run')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.action == 'list':
            if args.podcast or args.slug:
                raise ValueError('list takes no podcast or slug; use inspect')
            result = inspect(config)
        elif args.action == 'inspect':
            if not args.podcast or not args.slug:
                raise ValueError('inspect requires podcast and slug')
            result = inspect(config, args.podcast, args.slug)
        else:
            result = run_episode(config, args.podcast, args.action, args.slug, title=args.title,
                                 audio=args.audio, notes=args.notes, season=args.season,
                                 transcript=args.transcript, chapters=args.chapters, expected_state=args.expected_state,
                                 number=args.number, publish=args.publish, apply=args.apply, receipt=args.receipt)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        if isinstance(exc,subprocess.CalledProcessError):parser.exit(1,'Transport failed; inspect the private receipt and remote state before retrying.\n')
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
