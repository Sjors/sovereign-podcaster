"""Literal, local Marmot episode commands and independent resumable contexts."""
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import episodes

HELP = """Podcast commands

help — show this menu (also: podcast help).
transcribe SHOW EPISODE — transcribe, review and publish a cleared existing episode; repeat to resume.
chapters SHOW EPISODE — review and publish chapters plus description timestamps for one existing episode; repeat to resume.
episodes — list episode projects tracked here (also: podcast episodes).
podcast new SHOW EPISODE — start a video project with fresh context.
podcast use SHOW EPISODE — resume a saved episode.
podcast status — show the selected episode's progress and render jobs.
podcast history SHOW EPISODE — locate saved earlier conversation context.
approve REVIEW_ID — approve the exact offered publication packet (no model call).
A quoted yes to a review also works; an ordinary yes is fresh production feedback.

Help/status/list/selection commands use no model calls. The transcribe and chapters commands start or resume model-assisted work. Chapters require no manual approval. The episode list covers local projects; it does not scan the published YouTube/Nostr back catalogue.

After selecting an episode, send its audio/transcript paths and ordinary production instructions. Use this chat to discuss revisions and receive short encrypted review clips. Nostr publication and YouTube public publication require the corresponding review/approval; YouTube is uploaded privately first.

/help shows the White Noise bridge commands. Select /src/podcast first if a workspace is needed. Local Whisper transcription and existing-episode transcript attachment are available through the configured transcription task workflow; raw-audio editing remains planned."""


@dataclass
class Selection:
    record: dict
    path: Path
    context: str | None
    reply: str | None
    state_root: Path
    work_root: Path
    route: dict

    @property
    def public_handle(self):return self.record['public_handle']
    @property
    def backend_handle(self):return self.record['contexts'].get(self.context,{}).get('handle')
    def observe(self,event,emit):
        if event.get('type')=='thread.started':
            entry=self.record['contexts'].setdefault(self.context,{})
            entry['handle']=event['thread_id'];entry['state_root']=str(self.state_root)
            episodes.save(self.path,self.record)
            event=dict(event,thread_id=self.public_handle)
        emit(event)


def command(prompt):
    # The pinned bridge may append its own group-control instruction footer.
    text=prompt.partition('\n\nConnector-provided Marmot control instructions:')[0].strip()
    if text in ('help','podcast help'):return ('help',None,None)
    if text=='episodes':return ('episodes',None,None)
    match=re.fullmatch(r'(transcribe|chapters) ([A-Za-z0-9][A-Za-z0-9_-]{0,79}) ([A-Za-z0-9][A-Za-z0-9_-]{0,79})',text)
    if match:return match.groups()
    match=re.fullmatch(r'podcast (new|use|history) ([A-Za-z0-9][A-Za-z0-9_-]{0,79}) ([A-Za-z0-9][A-Za-z0-9_-]{0,79})',text)
    if match:return match.groups()
    if text in ('podcast status','podcast episodes'):return (text.split()[1],None,None)
    return None


def summary(item):
    renders=[]
    for p in Path(item['directory']).rglob('*.launcher.json'):
        launch=episodes.read(p);result=Path(launch['result']) if launch.get('result') else None
        renders.append({'job':p.stem,'state':episodes.read(result).get('state') if result and result.exists() else launch['state']})
    import jobs
    production_jobs=[]
    for p in (Path(item['directory'])/'jobs').glob('*/job.json'):
        status=jobs.status(p.parent);entry={'job':p.parent.name,'state':status['state']}
        if 'failure' in status:entry['failure_notice']=jobs.failures.save_notice(status['failure'],p.parent/'failure.json')
        production_jobs.append(entry)
    transcript=None
    if item.get('transcription'):
        folder=Path(item['transcription']['directory'])
        receipt=folder/'publication/verification.json';publication=episodes.read(receipt) if receipt.exists() else None
        if receipt.exists() and not isinstance(publication,dict):raise RuntimeError('Transcript completion receipt is malformed; inspect before repeating work')
        if publication is not None:
            source=episodes.read(folder/'episode.json')
            if publication.get('verified') is not True or publication.get('episode_guid')!=source['guid'] or source['number']!=item['episode'] or publication.get('vtt_sha256')!=episodes.file_record(folder/'publication/transcript.vtt')['sha256']:
                raise RuntimeError('Transcript completion receipt differs from its source/artifact; inspect before repeating work')
        transcript={'directory':str(folder),'analysis':episodes.read(folder/'analysis.json').get('state') if (folder/'analysis.json').exists() else 'not_started','published':publication is not None,'publication':publication}
    chapter_status=None
    if item.get('chapters'):
        import chapters
        folder=Path(item['chapters']['directory']);notice=chapters.completion(folder)
        chapter_status={'published':notice is not None,'completion':notice}
    return {'chapters':chapter_status,'transcription':transcript,'jobs':production_jobs,'show':item['show'],'episode':item['episode'],'revision':item.get('current_revision'),
            'fully_published':bool(episodes.complete(item)), 'drafts':len(item['drafts']), 'renders':renders,
            'publication_stages':[p['stage'] for p in item['publications']]}


def episode_list(data):
    items=sorted(data['episodes'].values(),key=lambda x:(x['show'],x['episode']))
    if not items:
        return 'No episode projects are tracked here yet. Start one with: podcast new SHOW EPISODE. Published YouTube/Nostr episodes are not imported automatically.'
    lines=['Episode projects tracked here:']
    for item in items:
        status=summary(item)
        stage='published' if status['fully_published'] else (status['publication_stages'][-1] if status['publication_stages'] else 'in preparation')
        if status['transcription']:
            transcript='transcript published' if status['transcription']['published'] else 'transcript '+status['transcription']['analysis']
            stage=transcript if not status['publication_stages'] and not status['revision'] else stage+'; '+transcript
        if status['chapters']:
            stage+='; '+('chapters published' if status['chapters']['published'] else 'chapters in preparation')
        lines.append('- '+item['show']+'/'+item['episode']+' — '+(status['revision'] or 'no revision yet')+'; '+stage)
    lines.append('Resume with: podcast use SHOW EPISODE. This is the local project list, not the published back catalogue.')
    return '\n'.join(lines)


@contextmanager
def select(config,handle,prompt,route):
    root=episodes.private_root(Path(config['state_root'])/'routing')
    work=Path(config.get('work_root',str(Path.home()/'.local/share/sovereign-podcaster/work')))
    identifier=hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()
    path=root/(identifier+'.json')
    with (root/(identifier+'.lock')).open('a') as lock:
        os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        record=episodes.read(path) if path.exists() else {'binding':route,'public_handle':handle or 'spapi_'+uuid.uuid4().hex,'selected':None,'contexts':{}}
        if record['binding']!=route or (handle and record['public_handle']!=handle):raise RuntimeError('Conversation routing differs; inspect before selecting an episode')
        cmd=command(prompt);reply=None
        if path.exists() and handle is None and cmd is None:
            raise RuntimeError('Harness session was reset. Send podcast use SHOW EPISODE to resume, or podcast new SHOW EPISODE for a new episode')
        if cmd and cmd[0] in ('new','use','transcribe','chapters'):
            active_name=identifier+'.active.json'
            roots=[Path(config['state_root'])]+[Path(x['state_root']) for x in record['contexts'].values() if x.get('state_root')]
            if any((p/active_name).exists() for p in roots):
                raise RuntimeError('Earlier model work has an unresolved outcome; inspect it before switching episodes')
        if cmd:
            action,show,number=cmd
            if action in ('new','transcribe','chapters'):snapshot=episodes.journal(work)
            else:
                work=episodes.private_root(work);journal_path=work/'episodes.json'
                snapshot=nullcontext((work,episodes.read(journal_path) if journal_path.exists() else {'schema':1,'episodes':{}}))
            with snapshot as (work,data):
                if action=='help':reply=HELP
                elif action=='chapters':
                    import chapters
                    settings=episodes.read(config['chapters_config'])
                    chapters.requested_source(settings,show,number)
                    if route['group']!=settings['group_id_hex']:raise RuntimeError('Select the configured chapter conversation')
                    k=episodes.key(show,number)
                    if k not in data['episodes']:episodes.initialize(work,data,show,number)
                    record['selected']=k
                    item=data['episodes'][k]
                    if item.get('chapters'):reply=chapters.completion(item['chapters']['directory'])
                elif action=='transcribe':
                    k=episodes.key(show,number)
                    if k not in data['episodes']:
                        settings=episodes.read(config['transcription_config']);catalog=episodes.read(settings['source_catalog'])
                        if settings.get('paused') is not False or settings['show']!=show or catalog['show']!=show or number not in catalog['episodes']:raise RuntimeError('No current source clearance for this episode; do not substitute another target')
                        episodes.initialize(work,data,show,number)
                    record['selected']=k
                    status=summary(data['episodes'][k])
                    if status['transcription'] and status['transcription']['published']:
                        publication=status['transcription']['publication']
                        reply='Transcript already published and verified for '+k+': '+publication['transcript_url']+'. No new transcription or publication started.'
                elif action=='new':
                    item=episodes.initialize(work,data,show,number)
                    record['selected']=episodes.key(show,number)
                    reply='Started '+record['selected']+' with fresh context. Send the episode audio/transcript paths and production instructions.'
                elif action=='use':
                    episodes.episode(data,show,number)
                    record['selected']=episodes.key(show,number)
                    reply='Resuming '+record['selected']+'.'
                elif action=='episodes':reply=episode_list(data)
                elif action=='history':
                    item=episodes.episode(data,show,number);k=episodes.key(show,number)
                    reply=json.dumps({'episode':summary(item),'saved_context':record['contexts'].get(k),
                                      'note':'Saved history is private source data. Retrieve only the relevant prior work; it is not automatically added to another episode.'},indent=2)
                elif record['selected']:
                    show,number=record['selected'].split('/');reply=json.dumps(summary(episodes.episode(data,show,number)),indent=2)
                else:reply='No episode selected. Send: podcast new SHOW EPISODE, or podcast use SHOW EPISODE.'
        episodes.save(path,record)
        context=record['selected']
        state_root=Path(config['state_root'])/'episode-contexts'/identifier/hashlib.sha256(context.encode()).hexdigest() if context else Path(config['state_root'])
        if context is None:
            # Preserve the pre-routing conversation and any completed requests.
            if '_unassigned' not in record['contexts']:
                exists=handle and (state_root/'cursors'/(handle+'.json')).is_file()
                if handle and not exists and cmd is None:raise RuntimeError('Saved backend state is missing; inspect before starting another session')
                record['contexts']['_unassigned']={'handle':handle if exists else None}
        episodes.save(path,record)
        yield Selection(record,path,context or '_unassigned',reply,state_root,work,route)
