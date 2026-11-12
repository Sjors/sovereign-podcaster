#!/usr/bin/env python3
"""Final-audio intake, local Whisper analysis and bounded transcript review commands."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import wave
import xml.etree.ElementTree as ET
import episodes as e
import asr
import captions
import failures

ROOT=Path(__file__).resolve().parents[1]

def transport():
    spec=importlib.util.spec_from_file_location('castopod_client',ROOT/'skills/castopod-publishing/scripts/publish.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def sha(path):return e.file_record(path)['sha256']
def get(url,accept=None):
    if not url.startswith('https://'):raise ValueError('Require HTTPS source delivery')
    headers={'Cache-Control':'no-cache','User-Agent':'sovereign-podcaster/1'}
    if accept is not None:headers['Accept']=accept
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as r:return r.read(),dict(r.headers)

def scope(config,episode):
    if config.get('paused') is not False:raise ValueError('Transcription experiment is paused')
    allowed=config['episodes'].get(episode['guid'])
    if not allowed or allowed['number']!=episode['number']:raise ValueError('Episode is outside the explicit transcription task scope')
    if allowed['final_audio_sha256']!=episode['final_audio_sha256']:raise ValueError('Final-audio clearance differs')
    return allowed

def prepare(config,episode_path,folder):
    episode=e.read(episode_path);scope(config,episode)
    cp=transport();cfg=cp.load_config(Path(config['castopod_config']))
    before=cp.inspect(cfg,config['show'],episode['slug']);live=before['episode']
    if not live or live['guid']!=episode['guid'] or live['transcript_id'] or live['transcript_url']:raise ValueError('Existing episode identity/transcript requires inspection')
    body,_=get(config['feed']);item=captions.target(body,episode['guid'])
    if item.findtext('link')!=episode['url'] or item.findtext('pubDate')!=episode['pubDate'] or item.find('enclosure').get('url')!=live['audio_url']:raise ValueError('Canonical feed episode identity differs from selected target')
    folder.mkdir(mode=0o700,parents=True)
    e.save(folder/'episode.json',episode);e.save(folder/'episode-before.json',before);(folder/'feed-before.xml').write_bytes(body)
    audio=folder/'published.mp3';data,headers=get(live['audio_url'])
    if hashlib.sha256(data).hexdigest()!=episode['final_audio_sha256']:raise ValueError('Served audio differs from audited final audio; wait for its audio owner')
    audio.write_bytes(data);e.save(folder/'download.json',dict(url=live['audio_url'],sha256=sha(audio),bytes=audio.stat().st_size))
    # Decode once at the native rate, then derive the recognition clock from it.
    for source,destination,args in [(audio,folder/'audio-native.wav',[]),(folder/'audio-native.wav',folder/'audio-16k.wav',['-ac','1','-ar','16000'])]:
        subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-i',str(source),'-map','0:a:0',*args,'-c:a','pcm_s16le',str(destination)],check=True)
    clocks={}
    for name in ('audio-native.wav','audio-16k.wav'):
        with wave.open(str(folder/name)) as f:clocks[name]=dict(samples=f.getnframes(),rate=f.getframerate(),channels=f.getnchannels(),seconds=f.getnframes()/f.getframerate())
    e.save(folder/'clock.json',clocks)
    e.save(folder/'intake.json',dict(source=e.file_record(audio),episode_guid=episode['guid'],source_clearance=config['episodes'][episode['guid']],native_clock=clocks['audio-native.wav'],recognition_clock=clocks['audio-16k.wav']))
    return dict(folder=str(folder),seconds=clocks['audio-native.wav']['seconds'])

def analyze(config,folder,clusters):
    episode=e.read(folder/'episode.json');scope(config,episode)
    if sha(folder/'published.mp3')!=episode['final_audio_sha256']:raise ValueError('Source changed')
    with (folder/'.analysis.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=folder/'analysis.json'
        if state.exists():
            old=e.read(state)
            if old['state']=='completed':return old
            raise ValueError('Earlier analysis is unresolved; do not restart its worker')
        e.save(state,dict(state='running',pid=os.getpid(),started_at=e.now()))
        asr.CONFIG=config
        try:
            asr.transcribe(folder,'primary');asr.transcribe(folder,'secondary');asr.diarize(folder,clusters);asr.review_material(folder)
            result=dict(state='completed',finished_at=e.now(),ready=e.read(folder/'ready-for-review.json'),approval=False)
            e.save(state,result);return result
        except BaseException as error:
            e.save(state,dict(state='failed',exception_type=type(error).__name__,approval=False));raise

def inspect(folder,start,end):
    words=e.read(folder/'words-for-review.json');result={}
    for name in ('primary-segments.jsonl','secondary-segments.jsonl'):
        result[name]=[s for s in map(json.loads,(folder/name).read_text().splitlines()) if s['end']>=start and s['start']<=end]
    result['words']=[dict(index=i,**w) for i,w in enumerate(words) if w['end']>=start and w['start']<=end]
    return result

def render(folder,preview=False):
    publication,vtt,expected=captions.render(folder,preview)
    return dict(cues=len(expected),vtt_sha256=hashlib.sha256(vtt).hexdigest(),path=str(publication/'transcript.vtt'),preview=preview)

def prepublish(config,folder):
    episode=e.read(folder/'episode.json');scope(config,episode)
    verdict=e.read(folder/'review-verdict.json');review=e.read(folder/'review.json')
    if verdict.get('publication_ready') is not True or review.get('publication_ready') is not True or verdict.get('no_unresolved_actual_participant_names') is not True:raise ValueError('Reviewed transcript and resolved participant identities are required')
    for kind in ('primary','secondary'):
        if e.read(folder/(kind+'-complete.json'))['segments_sha256']!=sha(folder/(kind+'-segments.jsonl')):raise ValueError('Original recognition evidence changed')
    if verdict['source_audio_sha256']!=episode['final_audio_sha256'] or verdict['review_sha256']!=sha(folder/'review.json'):raise ValueError('Review binding changed')
    vtt=(folder/'publication/transcript.vtt').read_bytes();expected=e.read(folder/'publication/expected-captions.json')
    if verdict['vtt_sha256']!=hashlib.sha256(vtt).hexdigest() or verdict['cue_count']!=len(expected):raise ValueError('Reviewed captions changed')
    import transcription_feedback
    transcription_feedback.require_for_publication(config,episode)
    cp=transport();cfg=cp.load_config(Path(config['castopod_config']));before=cp.inspect(cfg,config['show'],episode['slug'])
    if before['episode']['guid']!=episode['guid']:raise ValueError('Episode GUID changed')
    audio,_=get(before['episode']['audio_url'])
    if hashlib.sha256(audio).hexdigest()!=episode['final_audio_sha256']:raise ValueError('Served audio changed; realignment required')
    php='require '+json.dumps(cfg['app']+'/modules/Media/TranscriptParser.php')+'; echo (new \\Modules\\Media\\TranscriptParser())->loadString(stream_get_contents(STDIN))->parseVtt();'
    import shlex
    result=subprocess.run(cp.transport_args(cfg,shlex.join(['php','-r',php])),input=vtt,capture_output=True,check=True)
    parsed=json.loads(result.stdout);captions.compare_captions(parsed,expected);e.save(folder/'publication/parser.json',parsed)
    return cp,cfg,episode,before,expected,vtt

def publish(config,folder,apply):
    cp,cfg,episode,before,expected,vtt=prepublish(config,folder)
    if not apply:return dict(parser_verified=True,cues=len(expected),apply=False)
    # The signed-in operator has authorized this exact existing episode task.
    # User-maintained pauses, exact source/review checks and locked receipts apply.
    receipt=folder/'publication/transport.json'
    result=cp.run_episode(cfg,config['show'],'update',episode['slug'],transcript=folder/'publication/transcript.vtt',apply=True,receipt=receipt)
    return verify(config,folder,before,result['episode'],expected,vtt)

def verify(config,folder,before=None,after=None,expected=None,vtt=None):
    cp=transport();cfg=cp.load_config(Path(config['castopod_config']));episode=e.read(folder/'episode.json')
    before=before or e.read(folder/'episode-before.json');after=after or cp.inspect(cfg,config['show'],episode['slug'])['episode']
    expected=expected or e.read(folder/'publication/expected-captions.json');vtt=vtt or (folder/'publication/transcript.vtt').read_bytes()
    for field,value in before['episode'].items():
        if not field.startswith('transcript_') and after[field]!=value:raise ValueError('Unrelated episode field changed: '+field)
    public,headers=get(after['transcript_url'])
    if public!=vtt or next(v for k,v in headers.items() if k.lower()=='content-type').split(';')[0]!='text/vtt':raise ValueError('Public VTT hash/MIME mismatch')
    body,_=get(after['transcript_json_url']);captions.compare_captions(json.loads(body),expected)
    page,_=get(after['link']+'/transcript',accept='text/html');parser=captions.PageText();parser.feed(page.decode());visible=' '.join(' '.join(parser.parts).split())
    if any(c['text'] not in visible for c in expected):raise ValueError('Rendered page omits a caption')
    paragraphs=captions.compare_paragraphs(page.decode(),expected)
    e.save(folder/'publication/page-paragraph-verification.json',paragraphs)
    feed,_=get(config['feed']);old=captions.target((folder/'feed-before.xml').read_bytes(),episode['guid']);new=captions.target(feed,episode['guid'])
    ns='https://podcastindex.org/namespace/1.0';tags=new.findall('{'+ns+'}transcript')
    if not any(x.get('url')==after['transcript_url'] and x.get('type')=='text/vtt' and x.get('rel')=='captions' for x in tags):raise ValueError('RSS transcript attachment missing')
    for item in (old,new):
        for child in list(item):
            if child.tag=='{'+ns+'}transcript':item.remove(child)
    if ET.tostring(old)!=ET.tostring(new):raise ValueError('Non-transcript feed fields changed')
    audio,_=get(after['audio_url'])
    if hashlib.sha256(audio).hexdigest()!=episode['final_audio_sha256']:raise ValueError('Audio changed during attachment')
    report=dict(verified=True,verified_at=e.now(),episode_guid=episode['guid'],transcript_id=after['transcript_id'],transcript_url=after['transcript_url'],vtt_sha256=hashlib.sha256(vtt).hexdigest(),cues=len(expected),all_public_captions=True,episode_fields_preserved=True,feed_preserved=True,audio_preserved=True)
    e.save(folder/'publication/verification.json',report);return report

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    s=p.add_subparsers(dest='action',required=True)
    q=s.add_parser('prepare');q.add_argument('--episode',type=Path,required=True);q.add_argument('--folder',type=Path,required=True)
    for name in ('analyze','inspect','render','publish','verify'):
        q=s.add_parser(name);q.add_argument('--folder',type=Path,required=True)
        if name=='analyze':q.add_argument('--clusters',type=int,required=True)
        if name=='inspect':q.add_argument('--start',type=float,required=True);q.add_argument('--end',type=float,required=True)
        if name=='render':q.add_argument('--preview',action='store_true')
        if name=='publish':q.add_argument('--apply',action='store_true')
    a=p.parse_args();config=e.read(a.config);folder=a.folder.resolve()
    if a.action=='prepare':result=prepare(config,a.episode,folder)
    elif a.action=='analyze':result=analyze(config,folder,a.clusters)
    elif a.action=='inspect':result=inspect(folder,a.start,a.end)
    elif a.action=='render':result=render(folder,a.preview)
    elif a.action=='publish':result=publish(config,folder,a.apply)
    else:result=verify(config,folder)
    print(json.dumps(result,indent=2))
if __name__=='__main__':failures.cli(main,'transcript')
