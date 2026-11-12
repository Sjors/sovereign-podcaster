#!/usr/bin/env python3
"""Receipt-driven production Nostr and private-first YouTube publication."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import episodes as e
import failures
import blossom
import reviews
from video import hls
from video.nostr import metadata as nostr_metadata

HERE=Path(__file__).resolve().parent

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def context(args,verify=True):
    with e.journal(args.root) as (root,data):
        item=e.episode(data,args.show,args.episode);r=e.verified_revision(item,args.revision) if verify else item['revisions'][args.revision]
        if item['current_revision']!=args.revision:raise ValueError('Publication requires the current reviewed revision')
        if args.stage=='nostr' and item.get('video_task'):
            task=e.read(item['video_task']['path']);meta=nostr_metadata(e.read(r['files']['nostr_metadata']['path']))
            if task.get('announce') is False and meta.get('announce') is not False:raise ValueError('This video task forbids announcements')
        sha=r['nostr_manifest_sha256'] if args.stage=='nostr' else r['manifest_sha256']
        config=e.read(args.config)
        if args.stage=='youtube-public':reviews.bind_public(item,args.revision,config)
        approval=reviews.require(item,args.stage,sha,config)
        private=e.published(item,'youtube-private',r['manifest_sha256'])
        if args.stage.startswith('youtube') and not e.published(item,'nostr',r['nostr_manifest_sha256']):raise ValueError('Nostr publication must be verified first')
        if args.stage=='youtube-public' and (not private or approval.get('youtube_video_id')!=private['receipt']['video_id']):raise ValueError('Public approval must bind the private video ID')
        return root,item,r,sha,private

def nostr(config,r,sha,folder,check,phase='all',castopod_receipt=None):
    if phase not in ('all','video','announcement'):raise ValueError('Unknown Nostr phase')
    if not {'nostr_bundle','nostr_metadata'}<=r['files'].keys():raise ValueError('Register the complete HLS bundle and Nostr metadata in this revision')
    bundle_path=Path(r['files']['nostr_bundle']['path']);directory=bundle_path.parent
    if bundle_path.name!='bundle.json':raise ValueError('Nostr bundle artifact must be bundle.json')
    bundle=hls.validate_bundle(directory)
    if bundle.get('version')!=2 or bundle.get('policy')!='av1-15fps-aac64-mono-6s':raise ValueError('Production publication requires the verified AV1 bundle policy')
    verification=e.read(directory/'media-verification.json')
    if verification.get('complete') is not True or any(not x.get('full_hls_decode_passed') for x in verification.get('variants',[])):raise ValueError('Full HLS verification is required')
    if bundle['fallback_sha256']!=r['files']['fallback']['sha256']:raise ValueError('Packaged fallback is not the registered revision')
    signer=module(blossom.SIGNER,'nostr_signer');identity=signer.load_identity(Path(config['identity_file']))
    if identity['pubkey']!=config['expected_pubkey']:raise ValueError('Nostr destination identity mismatch')
    servers=[blossom.normalize_server(x) for x in config['publication_servers']]
    if not servers or len(set(servers))!=len(servers):raise ValueError('Explicit distinct publication servers are required')
    relays=signer.relay_urls(config['publication_relays'])
    meta=nostr_metadata(e.read(r['files']['nostr_metadata']['path']))
    announce=meta.get('announce',True)
    if phase=='announcement' and not announce:raise ValueError('This reviewed packet forbids announcements')
    # Exact signed events are saved before sending. Retrying publishes identical IDs.
    stamp_path=folder/'events.json'
    if stamp_path.exists():events=e.read(stamp_path)
    else:
        stamp=int(time.time());published=meta.get('published_at',stamp)
        found=[]
        for relay in relays:
            check();existing=signer.query_relay(relay,{'authors':[identity['pubkey']],'kinds':[34235],'#d':[meta['d']]})
            if not existing.get('complete'):raise RuntimeError('Cannot establish current video address state; inspect relay before publishing')
            found.extend(existing['events'])
        if found:
            latest=max(found,key=lambda event:(event['created_at'],event['id']))
            if meta.get('previous_event_id')!=latest['id']:raise ValueError('Existing Nostr video address requires its explicit previous_event_id in reviewed metadata')
            old_published=[tag[1] for tag in latest['tags'] if tag[0]=='published_at' and len(tag)>1]
            if old_published and str(meta.get('published_at'))!=old_published[0]:raise ValueError('Preserve the existing video published_at')
            stamp=max(stamp,latest['created_at']+1)
        elif meta.get('previous_event_id'):raise ValueError('Expected previous Nostr video event was not found')
        tags=[['d',meta['d']],['title',meta['title']],['published_at',str(published)],['alt',meta['description']],*hls.media_tags(bundle,servers)]
        if meta.get('source_url'):
            tags.append(['r',meta['source_url']])
        tags += [['t',x] for x in meta.get('hashtags',[])]
        tags += [['p',key] for key in meta.get('participants',[])]
        video=signer.sign_event(Path(config['identity_file']),dict(pubkey=identity['pubkey'],created_at=stamp,kind=34235,tags=tags,content=meta['description']))
        address=f'34235:{identity["pubkey"]}:{meta["d"]}'
        identifier=meta['d'].encode()
        if len(identifier)>255:raise ValueError('Video d identifier exceeds NIP-19 TLV size')
        tlv=bytes([0,len(identifier)])+identifier+bytes([2,32])+bytes.fromhex(identity['pubkey'])+bytes([3,4])+(34235).to_bytes(4,'big')
        for relay in relays[:2]:
            encoded=relay.encode()
            if len(encoded)<=255:tlv+=bytes([1,len(encoded)])+encoded
        note_id=signer.bech32_encode('naddr',signer.convertbits(tlv,8,5))
        note=signer.sign_event(Path(config['identity_file']),dict(pubkey=identity['pubkey'],created_at=stamp,kind=1,tags=[['a',address],['e',video['id']],*hls.media_tags(bundle,servers),*(['p',key] for key in meta.get('announcement_mentions',[]))],content=meta['announcement']+'\n\nnostr:'+note_id)) if announce else None
        events=dict(manifest_sha256=sha,servers=servers,relays=relays,video=video,announcement=note,identifier=note_id);e.save(stamp_path,events)
    if events['manifest_sha256']!=sha or events['servers']!=servers or events['relays']!=relays:raise ValueError('Saved signed publication belongs to different artifacts/destinations')
    if bool(events.get('announcement'))!=announce:raise ValueError('Saved announcement policy differs from the reviewed metadata')
    for event in (events['video'],events['announcement']):
        if event is None:continue
        signer.verify(event)
        if event['pubkey']!=config['expected_pubkey']:raise ValueError('Saved event identity differs')
    video_path=folder/'video-receipt.json'
    if phase=='announcement':
        native=e.read(video_path)
        link=e.read(castopod_receipt) if castopod_receipt else {}
        naddr=events['announcement']['content'].rsplit('nostr:',1)[-1]
        if (native.get('verified') is not True or native.get('manifest_sha256')!=sha or native.get('video_event_id')!=events['video']['id'] or
                link.get('verified') is not True or link.get('manifest_sha256')!=sha or
                link.get('video_event_id')!=events['video']['id'] or link.get('identifier')!=naddr or
                link.get('episode_url')!=meta.get('source_url')):
            raise ValueError('Announcement requires verified native video and matching Castopod linkage')
        receipt=dict(native)
    else:
        receipt=nostr_assets(config,bundle,directory,folder,servers,check)
        receipt.update(manifest_sha256=sha,relays={})
    for role in (('announcement',) if phase=='announcement' else ('video',) if phase=='video' or not announce else ('video','announcement')):
        event=events[role];checks={}
        for relay in relays:
            check();result=signer.publish_and_check(relay,event);checks[relay]=result
            e.save(folder/(role+'-relays.json'),checks)
        if not all(x.get('retrieved') for x in checks.values()):raise RuntimeError('Nostr relay readback incomplete; resume these saved event IDs')
        receipt['relays'][role]=checks;receipt[role+'_event_id']=event['id']
    receipt.update(verified=True,verified_at=e.now())
    receipt['identifier']=events.get('identifier') or events['announcement']['content'].rsplit('nostr:',1)[-1]
    if not announce:receipt['announcement_skipped']=True
    if phase=='video':e.save(video_path,receipt)
    return receipt

def nostr_assets(config,bundle,directory,folder,servers,check):
    blobs=[]
    def upload_one(task):
        server,asset=task
        check();receipt=folder/'blobs'/(e.digest(server)[:16]+'-'+asset['sha256']+'.json');receipt.parent.mkdir(mode=0o700,exist_ok=True)
        args=e.blossom_args(config,server,receipt,'upload')+['--file',str(directory/asset['path']),'--mime',asset['mime'].split(';',1)[0],'--apply']
        for origin in config['playback_origins']:args+=['--origin',origin]
        subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
        saved=e.read(receipt)
        if saved.get('state')!='verified' or saved.get('sha256')!=asset['sha256'] or saved.get('server')!=server:raise ValueError('Asset readback receipt mismatch')
        return dict(server=server,sha256=asset['sha256'])
    # Independent leaves have separate durable receipts. Wait for every leaf
    # before publishing playlists; retain original playlist dependency order.
    leaves=[(server,asset) for server in servers for asset in bundle['assets'] if asset['role'] not in ('playlist','master')]
    with ThreadPoolExecutor(max_workers=4) as workers:blobs.extend(workers.map(upload_one,leaves))
    for server in servers:
        for asset in bundle['assets']:
            if asset['role'] in ('playlist','master'):blobs.append(upload_one((server,asset)))
    # Verify the exact advertised master URL and every extensionless child URL
    # used when a player resolves relative playlist references.
    public_checks=[]
    def verify_asset(task):
        server,asset=task
        client=blossom.opener(config.get('server_options',{}).get(server,{}).get('read_redirect_origins',[]))
        local=dict(asset,file=str(directory/asset['path']),mime=asset['mime'].split(';',1)[0])
        urls=[server+'/'+asset['sha256']]
        if asset['role']=='master':urls.append(urls[0]+'.m3u8')
        checked=[]
        for url in urls:
            for origin in config['playback_origins']:
                check();result=blossom.remote_check(client,url,local,origin,30)
                if result is None:raise ValueError('Advertised HLS URL is not retrievable')
                checked.append(dict(result,url=url,origin=origin))
        return checked
    tasks=[(server,asset) for server in servers for asset in bundle['assets'] if asset['role']!='fallback']
    with ThreadPoolExecutor(max_workers=4) as workers:
        for result in workers.map(verify_asset,tasks):public_checks.extend(result)
    e.save(folder/'hls-public-readback.json',public_checks)
    return dict(blobs=blobs,hls_public_readback=public_checks)

def publish(args,config):
    root,item,r,sha,private=context(args)
    folder=Path(item['directory'])/'publication'/args.revision/args.stage;folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    phase=getattr(args,'nostr_phase','all')
    path=folder/('video-receipt.json' if args.stage=='nostr' and phase=='video' else 'receipt.json')
    binding=dict(manifest_sha256=sha,stage=args.stage,config_sha256=e.digest(config))
    with (folder/'.stage.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        bound=folder/'binding.json'
        if bound.exists() and e.read(bound)!=binding:raise ValueError('Stage configuration/destination changed; inspect before resuming')
        if not args.apply:return dict(dry_run=True,stage=args.stage,manifest_sha256=sha,folder=str(folder))
        e.save(bound,binding)
        snapshots={name:(Path(v['path']).stat().st_dev,Path(v['path']).stat().st_ino,Path(v['path']).stat().st_size,Path(v['path']).stat().st_mtime_ns) for name,v in r['files'].items()}
        def check():
            context(args,False);e.guard(config,args.stage)
            if e.read(args.config)!=config:raise ValueError('Publishing configuration changed during the stage')
            for name,v in r['files'].items():
                st=Path(v['path']).stat()
                if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=snapshots[name]:raise ValueError('Approved source changed during publication')
        check()
        if path.exists():receipt=e.read(path)
        elif args.stage=='nostr':receipt=nostr(config,r,sha,folder,check,phase,getattr(args,'castopod_receipt',None));e.save(path,receipt)
        else:
            from video import youtube
            if 'captions' not in r['files']:raise ValueError('Reviewed captions are required for YouTube')
            packet=dict(manifest_sha256=sha,files=r['files'],channel_id=config['youtube_channel_id'],metadata=e.read(r['files']['metadata']['path']))
            youtube.metadata(packet['metadata'])
            if args.stage=='youtube-private':
                candidates=[x['receipt'] for x in reversed(item['publications']) if x['stage']=='youtube-private' and x['receipt'].get('channel_id')==packet['channel_id'] and x['receipt'].get('video_source',{}).get('sha256')==r['files']['video']['sha256']]
                if candidates:
                    previous=candidates[0];packet['reuse_video_id']=previous['video_id']
                    if previous['metadata']['language']==packet['metadata']['language']:packet['reuse_caption_id']=previous['caption_id']
            access=youtube.sdk()
            with access.channel_service(Path(config['youtube_config_directory']),packet['channel_id'],mutate=True) as (service,channel):
                receipt=youtube.private(service,packet,folder,check) if args.stage=='youtube-private' else youtube.public(service,packet,private['receipt'],folder,check)
            receipt.update(manifest_sha256=sha,verified_at=e.now());e.save(path,receipt)
        check()
        if args.stage=='nostr' and phase=='video':return dict(stage='nostr-video',verified=True,receipt=str(path),video_event_id=receipt['video_event_id'])
        with e.journal(root) as (root,data):
            live=e.episode(data,args.show,args.episode)
            old=e.published(live,args.stage,sha)
            if old is None:e.record_publication(live,args.revision,args.stage,path)
            elif old['receipt']!=receipt:raise ValueError('Recorded receipt differs; inspect before replacement')
        return dict(stage=args.stage,verified=True,receipt=str(path),video_id=receipt.get('video_id'))

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['nostr','youtube-private','youtube-public'])
    for name in ('root','config'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('show','episode','revision'):p.add_argument('--'+name,required=True)
    p.add_argument('--nostr-phase',choices=['all','video','announcement'],default='all')
    p.add_argument('--castopod-receipt',type=Path)
    p.add_argument('--apply',action='store_true');args=p.parse_args();config=e.read(args.config)
    runtime=Path(config['nostr_python' if args.stage=='nostr' else 'youtube_python']).absolute()
    if Path(sys.executable).absolute()!=runtime:os.execv(str(runtime),[str(runtime),str(Path(__file__).resolve()),*sys.argv[1:]])
    print(json.dumps(publish(args,config),indent=2))
if __name__=='__main__':failures.cli(main,sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in failures.STAGES else 'unknown')
