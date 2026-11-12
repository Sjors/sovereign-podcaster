#!/usr/bin/env python3
"""Offer an exact publication packet for authenticated Marmot approval."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import episodes as e
import failures
from video.nostr import metadata as nostr_metadata

SCOPES=('nostr','youtube-private','youtube-public','draft-upload')

def manifest(revision,scope):return revision['nostr_manifest_sha256'] if scope=='nostr' else revision['manifest_sha256']

def request(root,data,item,revision,scope,route,config,send=False,include_youtube_private=False,include_youtube_public=False):
    if include_youtube_public:include_youtube_private=True
    r=e.verified_revision(item,revision);sha=manifest(r,scope)
    if include_youtube_private and scope!='nostr':raise ValueError('Combined private upload authorization belongs to a Nostr review')
    if scope not in SCOPES:raise ValueError('Unknown review scope')
    nostr=nostr_metadata(e.read(r['files']['nostr_metadata']['path'])) if scope=='nostr' else None
    if scope=='nostr' and item.get('video_task'):
        task=e.read(item['video_task']['path'])
        if task.get('announce') is False and nostr.get('announce') is not False:raise ValueError('This video task forbids announcements; register matching native metadata')
    private=e.published(item,'youtube-private',r['manifest_sha256'])
    if scope=='youtube-public' and not private:raise ValueError('Review the private upload first')
    if scope=='youtube-private' and not e.published(item,'nostr',r['nostr_manifest_sha256']):raise ValueError('Nostr must be verified first')
    for old in item.setdefault('reviews',{}).values():
        if old['scope']==scope and old['manifest_sha256']==sha and old['route']==route and old.get('include_youtube_private',False)==include_youtube_private and old.get('include_youtube_public',False)==include_youtube_public and old.get('configuration_sha256')==e.digest(config) and old['state']!='superseded':return old
    token=uuid.uuid4().hex[:12]
    packet=dict(include_youtube_private=include_youtube_private,youtube_private_manifest_sha256=r['manifest_sha256'] if include_youtube_private else None,configuration_sha256=e.digest(config),id=token,scope=scope,revision=revision,manifest_sha256=sha,route=route,created_at=e.now(),state='prepared',files=r['files'],
                youtube_video_id=private['receipt']['video_id'] if private else None)
    packet['include_youtube_public']=include_youtube_public
    for old in item['reviews'].values():
        if old['route']==route and old['state'] in ('prepared','sent'):old['state']='superseded'
    item['reviews'][token]=packet
    e.save(root/'episodes.json',data)
    if not send:return packet
    folder=Path(item['directory'])/'reviews';folder.mkdir(mode=0o700,exist_ok=True)
    text=f'Review {item["show"]}/{item["episode"]}, revision {revision}: {scope}.\nPacket SHA256: {sha}\n'
    if include_youtube_public:text+='This approval also authorizes YouTube upload privately, inspection and public release of that same video ID with these exact captions, thumbnail and metadata. Changed content or destinations require a new review. Full packet SHA256: '+r['manifest_sha256']+'\n'
    elif include_youtube_private:text+='This approval also authorizes the following private YouTube upload (not public release). Full packet SHA256: '+r['manifest_sha256']+'\n'
    if private:text+='Private YouTube video: https://www.youtube.com/watch?v='+private['receipt']['video_id']+'\n'
    if scope=='nostr':
        text+='Nostr identity: '+config['expected_pubkey']+'\nStorage: '+', '.join(config['publication_servers'])+'\nRelays: '+', '.join(config['publication_relays'])+'\nNostr title: '+nostr['title']+'\nDescription:\n'+nostr['description']+'\nAnnouncement:\n'+(nostr['announcement'] if nostr.get('announce',True) else 'NONE — native video only; no kind-1 announcement will be created.')+'\n'
        text+='Video participant p tags: '+', '.join(nostr.get('participants',[]))+'\nAnnouncement mention p tags: '+', '.join(nostr.get('announcement_mentions',[]))+'\nSource reference: '+nostr.get('source_url','')+'\nHashtags: '+', '.join(nostr.get('hashtags',[]))+'\n'
        if item.get('video_task'):text+='This approval also authorizes adding this native video to that existing Castopod episode, preserving its audio, transcript and identity.\n'
    if scope.startswith('youtube') or include_youtube_private:text+='YouTube channel: '+config['youtube_channel_id']+'\n'
    meta=e.read(r['files']['metadata']['path'])
    text+='Title: '+meta.get('title','')+'\nDescription:\n'+meta.get('description','')+'\n'
    text+='Inspect the saved video, thumbnail, captions and metadata. Reply "approve '+token+'" to authorize exactly this scope. A quoted reply "yes" to this review also works. Ordinary unquoted "yes" remains production feedback.'
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
