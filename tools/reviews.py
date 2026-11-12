#!/usr/bin/env python3
"""Offer an exact publication packet for authenticated Marmot approval."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import urllib.request
import blossom
import episodes as e
import failures
from video.nostr import metadata as nostr_metadata, relay_policy

SCOPES=('nostr','youtube-private','youtube-public','draft-upload')

def manifest(revision,scope):return revision['nostr_manifest_sha256'] if scope=='nostr' else revision['manifest_sha256']


def preview(item,revision,config,private=None):
    """Select an exact full-revision preview, never a caller-supplied URL or clip."""
    r=item['revisions'][revision]
    if private:
        receipt=private['receipt']
        if receipt.get('verified') is not True or receipt.get('manifest_sha256')!=r['manifest_sha256'] or receipt.get('privacy_status')!='private' or receipt.get('channel_id')!=config['youtube_channel_id']:
            raise ValueError('The private YouTube preview must match this exact revision')
        return dict(kind='youtube',url='https://www.youtube.com/watch?v='+receipt['video_id'],video_id=receipt['video_id'])
    asset=r['files']['fallback']
    for raw in config['draft_servers']:
        server=blossom.normalize_server(raw)
        for draft in item['drafts'].values():
            if draft.get('revision')!=revision or draft.get('server')!=server or draft.get('sha256')!=asset['sha256']:continue
            receipt_path=Path(draft['receipt'])
            if not receipt_path.exists():continue
            receipt=blossom.receipt_read(receipt_path)
            if any(receipt.get(k)!=v for k,v in dict(server=server,sha256=asset['sha256'],size=asset['size'],mime='video/mp4',pubkey=config['expected_pubkey']).items()):
                raise ValueError('Preview receipt differs from the full registered fallback or destination')
            if receipt.get('state')!='verified':continue
            url=server+'/'+asset['sha256']+'.mp4'
            origins=config['playback_origins']
            if not origins or any(not any(c.get('url')==url and c.get('sha256')==asset['sha256'] and c.get('size')==asset['size'] and c.get('mime')=='video/mp4' and c.get('origin')==origin and c.get('range_verified') is True for c in receipt.get('public_checks',[])) for origin in origins):
                raise ValueError('Full MP4 preview needs verified public hash, MIME, CORS and seeking receipts')
            # Recheck reachability and seeking just before offering the link.
            # Full-byte verification is already saved by the draft uploader.
            origin=origins[0];end=min(1023,asset['size']-1)
            client=blossom.opener(config.get('server_options',{}).get(server,{}).get('read_redirect_origins',[]))
            request=urllib.request.Request(url,headers={'Origin':origin,'Range':f'bytes=0-{end}'})
            with client.open(request,timeout=15) as response,Path(asset['path']).open('rb') as source:
                if (response.status!=206 or response.headers.get('Content-Range')!=f'bytes 0-{end}/{asset["size"]}' or
                        response.headers.get_content_type()!='video/mp4' or response.headers.get('Access-Control-Allow-Origin') not in ('*',origin) or
                        response.read(end+2)!=source.read(end+1)):
                    raise ValueError('Full MP4 preview link is no longer playable; inspect the draft receipt')
            return dict(kind='blossom',url=url,sha256=asset['sha256'],receipt=e.evidence_copy(item,receipt_path,'review-preview'))
    raise ValueError('Upload and verify the full revision fallback with a tracked draft-upload job before sending final approval')


def offer_text(item,revision,scope,packet,config,watch):
    r=item['revisions'][revision];meta=e.read(r['files']['metadata']['path'])
    native=nostr_metadata(e.read(r['files']['nostr_metadata']['path'])) if scope=='nostr' else None
    text=f'{item["show"]} episode {item["episode"]} — final video review ({revision})\n\n'
    if watch:
        label='Watch the full video preview (480p)' if watch['kind']=='blossom' else 'Watch the private video on YouTube'
        text+=label+':\n'+watch['url']+'\n\n'
        if watch['kind']=='blossom':text+='Anyone with the preview link can watch.\n\n'
    text+='If you approve, I will:\n'
    if scope=='draft-upload':text+='• Upload the full video preview to the configured Blossom servers.\n'
    if native:
        text+='• Publish this video on Nostr / Nostube.\n'
        if item.get('video_task'):text+='• Add the video to this existing Castopod episode, preserving its audio and transcript.\n'
        if native.get('announce',True):text+='• Post the announcement shown below.\n'
    if scope=='youtube-public' or packet.get('include_youtube_public'):
        text+='• '+('Upload to YouTube privately, check captions, thumbnail and details, then make that same video public.\n' if scope!='youtube-public' else 'Make this same YouTube video public, with the reviewed captions, thumbnail and details.\n')
    elif scope=='youtube-private' or packet.get('include_youtube_private'):
        text+='• Upload to YouTube privately for inspection. Public release will need a separate approval.\n'
    if native and not native.get('announce',True):text+='\nAnnouncement: none.\n'
    if scope.startswith('youtube') or packet.get('include_youtube_private'):
        text+='YouTube channel: https://www.youtube.com/channel/'+config['youtube_channel_id']+'\n'
    text+='\nTitle: '+(native['title'] if native else meta.get('title',''))+'\nDescription:\n'+(native['description'] if native else meta.get('description',''))+'\n'
    if native:
        if native.get('announce',True):text+='\nAnnouncement:\n'+native['announcement']+'\n'
        for field,label in [('participants','Video participants (Nostr keys)'),('announcement_mentions','Announcement notifications (Nostr keys)')]:
            if native.get(field):text+='\n'+label+': '+', '.join(native[field])+'\n'
        if packet.get('include_youtube_private') and (meta.get('title',''),meta.get('description',''))!=(native['title'],native['description']):
            text+='\nYouTube title: '+meta.get('title','')+'\nYouTube description:\n'+meta.get('description','')+'\n'
    text+='\nReply "approve '+packet['id']+'" to approve these actions, or reply to this message with "yes". For changes, reply normally. Changed content or destinations will need a new review.'
    return text


def request(root,data,item,revision,scope,route,config,send=False,include_youtube_private=False,include_youtube_public=False):
    if include_youtube_public:include_youtube_private=True
    r=e.verified_revision(item,revision);sha=manifest(r,scope)
    if item['current_revision']!=revision:raise ValueError('Final review requires the current revision')
    if include_youtube_private and scope!='nostr':raise ValueError('Combined private upload authorization belongs to a Nostr review')
    if scope not in SCOPES:raise ValueError('Unknown review scope')
    nostr=nostr_metadata(e.read(r['files']['nostr_metadata']['path'])) if scope=='nostr' else None
    if scope=='nostr' and item.get('video_task'):
        task=e.read(item['video_task']['path'])
        if task.get('announce') is False and nostr.get('announce') is not False:raise ValueError('This video task forbids announcements; register matching native metadata')
    private=e.published(item,'youtube-private',r['manifest_sha256'])
    if scope=='youtube-public' and not private:raise ValueError('Review the private upload first')
    if scope=='youtube-private' and not e.published(item,'nostr',r['nostr_manifest_sha256']):raise ValueError('Nostr must be verified first')
    pending=None
    for old in item.setdefault('reviews',{}).values():
        if old['scope']==scope and old['manifest_sha256']==sha and old['route']==route and old.get('include_youtube_private',False)==include_youtube_private and old.get('include_youtube_public',False)==include_youtube_public and old.get('configuration_sha256')==e.digest(config) and old['state']!='superseded':
            if old['state']=='sending' and send:raise ValueError('Review send outcome is uncertain; inspect the existing send receipt before retrying')
            if old['state']=='approved' or (old.get('message_version')==2 and old['state'] in ('sent','sending')):return old
            if old.get('message_version')==2:pending=old
    # A broken/missing preview must not supersede an offer or send a new one.
    watch=preview(item,revision,config,private if scope=='youtube-public' else None) if send and scope!='draft-upload' else None
    token=pending['id'] if pending else uuid.uuid4().hex[:12]
    packet=dict(include_youtube_private=include_youtube_private,youtube_private_manifest_sha256=r['manifest_sha256'] if include_youtube_private else None,configuration_sha256=e.digest(config),id=token,scope=scope,revision=revision,manifest_sha256=sha,route=route,created_at=e.now(),state='prepared',files=r['files'],
                youtube_video_id=private['receipt']['video_id'] if private else None)
    packet['include_youtube_public']=include_youtube_public
    packet['message_version']=2
    if watch:packet['preview']=watch
    if send:
        packet['publication_details']=dict(metadata=e.read(r['files']['metadata']['path']),nostr_metadata=nostr,
            destinations={k:config.get(k) for k in ('expected_pubkey','publication_servers','publication_relays','required_publication_relays','youtube_channel_id')})
        if 'publication_relays' in config:
            relays,required=relay_policy(config)
            packet['publication_details']['destinations'].update(required_publication_relays=required,optional_publication_relays=[relay for relay in relays if relay not in required])
        text=offer_text(item,revision,scope,packet,config,watch)
    for old in item['reviews'].values():
        if old['route']==route and old['state'] in ('prepared','sent'):old['state']='superseded'
    item['reviews'][token]=packet
    e.save(root/'episodes.json',data)
    if not send:return packet
    folder=Path(item['directory'])/'reviews';folder.mkdir(mode=0o700,exist_ok=True)
    msg=dict(account_id_hex=route['account'],group_id_hex=route['group'],text=text,idempotency_key='review-'+token)
    path=folder/(token+'.send.json');e.save(path,msg)
    packet['state']='sending';e.save(root/'episodes.json',data)
    result=subprocess.check_output([sys.executable,str(Path(__file__).resolve().parents[1]/'skills/marmot-whitenoise/scripts/wn_control.py'),'--home',config['marmot_home'],'--send-text',str(path)])
    import json
    sent=json.loads(result);packet.update(state='sent',message_ids=sent['response']['message_ids_hex'],send_receipt=sent)
    e.save(root/'episodes.json',data);return packet

def accept(root,data,incoming):
    text=incoming['text'].strip();explicit=re.fullmatch(r'(?i)(?:approve|yes) ([0-9a-f]{12})',text)
    quoted=text.lower() in ('yes','approve') and incoming.get('reply_to')
    if not explicit and not quoted:return None
    candidates=[]
    for item in data['episodes'].values():
        for packet in item.get('reviews',{}).values():
            if packet['route']!={k:incoming[k] for k in ('account','group')} or packet['state'] not in ('sent','approved'):continue
            if (explicit and packet['id']==explicit[1]) or (quoted and incoming['reply_to'] in packet.get('message_ids',[])):candidates.append((item,packet))
    if len(candidates)!=1:raise RuntimeError('No single active review matches that authenticated reply; request a current review')
    item,packet=candidates[0];r=e.verified_revision(item,packet['revision'])
    if item['current_revision']!=packet['revision'] or manifest(r,packet['scope'])!=packet['manifest_sha256']:raise RuntimeError('That review is stale; inspect the current revision')
    if packet['scope']=='youtube-public':
        p=e.published(item,'youtube-private',r['manifest_sha256'])
        if not p or p['receipt']['video_id']!=packet['youtube_video_id']:raise RuntimeError('The reviewed private video changed')
    if packet['state']=='approved':return f'Review {packet["id"]} was already approved. No action repeated.'
    evidence=Path(item['directory'])/'reviews'/(packet['id']+'.approval.json');evidence.parent.mkdir(mode=0o700,exist_ok=True);e.save(evidence,incoming)
    a=e.approve(item,packet['revision'],packet['scope'],evidence)
    a.update(authenticated=True,message_id=incoming['message_id'],sender=incoming['sender'],review_id=packet['id'],route=packet['route'])
    if packet.get('include_youtube_private'):
        private_approval=e.approve(item,packet['revision'],'youtube-private',evidence)
        private_approval.update(authenticated=True,message_id=incoming['message_id'],sender=incoming['sender'],review_id=packet['id'],route=packet['route'])
    packet.update(state='approved',approval_message_id=incoming['message_id']);e.save(root/'episodes.json',data)
    return f'Approved {packet["scope"]} for {item["show"]}/{item["episode"]}, revision {packet["revision"]} ({packet["id"]}). No upload or publication has run yet; the next production command may use this exact approval.'

def require(item,scope,sha,config=None):
    a=e.approval(item,scope,sha)
    if a and a.get('source')=='explicit-maintainer-user-request':
        if e.file_record(a['evidence']['path'])!=a['evidence']:raise ValueError('Approval evidence changed')
        grant=e.read(a['evidence']['path'])
        r=item['revisions'][a['revision']]
        if (item['current_revision']!=a['revision'] or grant.get('source')!=a['source'] or
                grant.get('show')!=item['show'] or str(grant.get('episode'))!=str(item['episode']) or
                grant.get('revision')!=a['revision'] or scope not in grant.get('scopes',[]) or
                grant.get('manifest_sha256')!=r['manifest_sha256'] or
                grant.get('nostr_manifest_sha256')!=r['nostr_manifest_sha256'] or
                not grant.get('human_request') or not grant.get('approval_context')):
            raise ValueError('Local operator authorization does not bind this exact episode/revision/scope')
        if config is None or grant.get('configuration_sha256')!=e.digest(config):raise ValueError('Publishing destination/configuration changed since review')
        if scope=='youtube-public':
            private=e.published(item,'youtube-private',r['manifest_sha256'])
            if not private or a.get('youtube_video_id')!=private['receipt']['video_id']:raise ValueError('Public approval must bind the inspected private video ID')
        return a
    if not a or a.get('authenticated') is not True:raise ValueError('An authenticated exact-packet Marmot approval is required')
    packet=item.get('reviews',{}).get(a.get('review_id'))
    combined=packet and ((scope=='youtube-private' and packet.get('include_youtube_private')) or (scope=='youtube-public' and packet.get('include_youtube_public')))
    if not packet or packet['state']!='approved' or (packet['youtube_private_manifest_sha256'] if combined else packet['manifest_sha256'])!=sha or packet['approval_message_id']!=a['message_id']:raise ValueError('Approval has no matching consumed review')
    if config is not None and packet.get('configuration_sha256')!=e.digest(config):raise ValueError('Publishing destination/configuration changed since review')
    if e.file_record(a['evidence']['path'])!=a['evidence']:raise ValueError('Approval evidence changed')
    return a


def bind_public(item,revision,config):
    """Bind an existing exact full-release approval to its verified private ID."""
    r=e.verified_revision(item,revision)
    if e.approval(item,'youtube-public',r['manifest_sha256']):return
    private=e.published(item,'youtube-private',r['manifest_sha256'])
    if not private:raise ValueError('Inspect the verified private YouTube upload first')
    original=require(item,'youtube-private',r['manifest_sha256'],config)
    packet=item.get('reviews',{}).get(original.get('review_id'),{})
    if packet.get('include_youtube_public') is not True:raise ValueError('This approval does not authorize public YouTube release')
    if item['current_revision']!=revision or packet['revision']!=revision:raise ValueError('Full-release review is stale')
    a=e.approve(item,revision,'youtube-public',Path(original['evidence']['path']))
    a.update(authenticated=True,message_id=original['message_id'],sender=original['sender'],review_id=original['review_id'],route=original['route'])

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','config'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('show','episode','revision','account','group'):p.add_argument('--'+name,required=True)
    p.add_argument('--scope',choices=SCOPES,required=True);p.add_argument('--send',action='store_true');p.add_argument('--include-youtube-private',action='store_true');p.add_argument('--include-youtube-public',action='store_true');a=p.parse_args()
    with e.journal(a.root) as (root,data):
        item=e.episode(data,a.show,a.episode);packet=request(root,data,item,a.revision,a.scope,dict(account=a.account,group=a.group),e.read(a.config),a.send,a.include_youtube_private,a.include_youtube_public)
        print(packet['id'],packet['state'],packet['manifest_sha256'])
if __name__=='__main__':failures.cli(main,'controller')
