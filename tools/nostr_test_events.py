#!/usr/bin/env python3
"""Prepare/sign a temporary five-second video + kind-1 note; prepare exact-target deletion."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('blossom', ROOT/'tools/blossom.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
FIELDS = ('pubkey', 'created_at', 'kind', 'tags', 'content')
PURPOSE = 'temporary-nostr-access-check'


def signer():
    spec = importlib.util.spec_from_file_location('nostr_publish', b.SIGNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def write_new(path, value):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump(value, f, indent=2); f.write('\n')


def prepare(args):
    if not re.fullmatch('[0-9a-f]{64}', args.pubkey): raise ValueError('Expected lowercase hex public key')
    asset = b.fingerprint(args.file, 'video/mp4')
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                                               '-of', 'json', str(args.file)], text=True))
    duration = float(info['format']['duration'])
    video = next(s for s in info['streams'] if s['codec_type']=='video')
    audio = next(s for s in info['streams'] if s['codec_type']=='audio')
    if not 4.95 <= duration <= 5.05 or video['codec_name']!='av1' or audio['codec_name']!='aac':
        raise ValueError('Test requires a five-second AV1/AAC MP4; do not pass a full episode')
    servers = list(dict.fromkeys(b.normalize_server(s) for s in args.server))
    urls = [s+'/'+asset['sha256']+'.mp4' for s in servers]
    stamp = int(time.time()); d = 'sovereign-podcaster-test-'+uuid.uuid4().hex
    description = 'Temporary sovereign-podcaster access test: five-second excerpt from '+args.source_label+'. Will be deleted after verification.'
    imeta = ['imeta', 'url '+urls[0], 'm video/mp4', 'x '+asset['sha256'], 'size '+str(asset['size']),
             'dim '+str(video['width'])+'x'+str(video['height']), 'duration '+str(duration),
             'bitrate '+str(round(asset['size']*8/duration))]+['fallback '+u for u in urls[1:]]
    native = dict(pubkey=args.pubkey, created_at=stamp, kind=34235, content=description,
                  tags=[['d', d], ['title', 'Temporary 5-second access test — '+args.source_label],
                        ['published_at', str(stamp)], ['alt', description], imeta])
    if args.source_url:
        u = urllib.parse.urlsplit(args.source_url)
        if u.scheme!='https' or not u.hostname or u.username is not None: raise ValueError('Source URL must be public HTTPS')
        native['tags'].append(['r', args.source_url])
    links = ([args.source_url] if args.source_url else [])+[urls[0]]
    note = dict(pubkey=args.pubkey, created_at=stamp, kind=1, content=description+'\n\n'+'\n'.join(links),
                tags=[imeta])
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_new(args.out/'video.unsigned.json', native); write_new(args.out/'note.unsigned.json', note)
    manifest = dict(version=1, purpose=PURPOSE, pubkey=args.pubkey, d=d, asset=asset, servers=servers,
        duration=duration, source_label=args.source_label, probe=info,
        unsigned_sha256={n:hashlib.sha256((args.out/n).read_bytes()).hexdigest() for n in ('video.unsigned.json','note.unsigned.json')})
    write_new(args.out/'manifest.json', manifest)
    return {'bundle': str(args.out), 'purpose': PURPOSE, 'sha256': asset['sha256'], 'd': d, 'urls': urls}


def validated_bundle(folder, m):
    manifest = json.loads((folder/'manifest.json').read_text())
    if manifest.get('purpose')!=PURPOSE or not manifest.get('d','').startswith('sovereign-podcaster-test-'):
        raise ValueError('Only a generated temporary test bundle may be cleaned up')
    events = []
    for stem, kind in [('video',34235),('note',1)]:
        path = folder/(stem+'.unsigned.json')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['unsigned_sha256'][path.name]:
            raise ValueError('Unsigned test event changed after preparation')
        unsigned = json.loads(path.read_text()); signed = json.loads((folder/(stem+'.signed.json')).read_text())
        m.verify(signed)
        if signed['kind']!=kind or signed['pubkey']!=manifest['pubkey'] or any(signed[k]!=unsigned[k] for k in FIELDS):
            raise ValueError('Signed event does not match prepared test')
        if kind==34235 and ['d',manifest['d']] not in signed['tags']: raise ValueError('Test address mismatch')
        events.append(signed)
    return manifest, events


def sign(args):
    m = signer(); manifest = json.loads((args.bundle/'manifest.json').read_text())
    if m.load_identity(args.identity)['pubkey']!=manifest['pubkey']: raise ValueError('Identity mismatch')
    result = []
    for stem in ['video','note','deletion']:
        unsigned = args.bundle/(stem+'.unsigned.json')
        if not unsigned.exists(): continue
        target = args.bundle/(stem+'.signed.json'); value = json.loads(unsigned.read_text())
        if target.exists():
            event = json.loads(target.read_text()); m.verify(event)
            if any(event[k]!=value[k] for k in FIELDS): raise ValueError('Saved signature belongs to different event')
        else:
            event = m.sign_event(args.identity, value); write_new(target, event)
        result.append({'file': target.name, 'kind': event['kind'], 'id': event['id']})
    return result


def deletion(args):
    manifest, events = validated_bundle(args.bundle, signer())
    tags = [['e', e['id']] for e in events]+[['k','34235'],['k','1'],['a',f'34235:{manifest["pubkey"]}:{manifest["d"]}']]
    path = args.bundle/'deletion.unsigned.json'
    value = dict(pubkey=manifest['pubkey'], created_at=max(int(time.time()),max(e['created_at'] for e in events)+1),
                 kind=5, tags=tags, content='Temporary sovereign-podcaster access check completed; remove test events.')
    if path.exists():
        saved = json.loads(path.read_text())
        if any(saved[k]!=value[k] for k in ('pubkey','kind','tags','content')): raise ValueError('Existing deletion has different targets')
        value = saved
    else: write_new(path, value)
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action',required=True)
    q = sub.add_parser('prepare');q.add_argument('--file',type=Path,required=True);q.add_argument('--pubkey',required=True)
    q.add_argument('--server',action='append',required=True);q.add_argument('--source-label',required=True)
    q.add_argument('--source-url');q.add_argument('--out',type=Path,required=True)
    q = sub.add_parser('sign');q.add_argument('--bundle',type=Path,required=True);q.add_argument('--identity',type=Path,required=True)
    q = sub.add_parser('deletion');q.add_argument('--bundle',type=Path,required=True)
    args = p.parse_args();os.umask(0o077)
    try:print(json.dumps({'prepare':prepare,'sign':sign,'deletion':deletion}[args.action](args),indent=2))
    except Exception as error:p.exit(1,f'{type(error).__name__}: {error}\n')


if __name__=='__main__':main()
