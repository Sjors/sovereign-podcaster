#!/usr/bin/env python3
"""Prepare, render, revise and package a podcast video. Local files only."""
import argparse
import html
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import episodes as e
import failures
import slides
from video import hls, av1_packaging, verify_hls
from video.verify_mp4 import mp4_atoms, alignment

COLOR = ('format=gbrpf32le,zscale=matrixin=gbr:transferin=iec61966-2-1:primariesin=709:rangein=full:'
         'matrix=709:transfer=709:primaries=709:range=limited,format=yuv420p')
SIZES = {1080:1920,720:1280,480:854,360:640}

def run(args, log=None):
    with open(log or os.devnull,'ab') as output:
        subprocess.run([str(x) for x in args],stdin=subprocess.DEVNULL,stdout=output,stderr=output,check=True)

def ff(*args, log=None):
    run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-n',*args],log)

def norm(text):return ''.join(c.lower() for c in text if c.isalnum())
def finite(value):return type(value) in (int,float) and math.isfinite(value)
def ass_time(t):
    n=round(t*100);return f'{n//360000}:{n//6000%60:02d}:{n//100%60:02d}.{n%100:02d}'
def vtt_time(t):
    n=round(t*1000);return f'{n//3600000:02d}:{n//60000%60:02d}:{n//1000%60:02d}.{n%1000:03d}'
def ass_escape(text):return text.replace('\\','\\\\').replace('{','\\{').replace('}','\\}').replace('\n',r'\N')
def ffmeta(text):
    for c in '\\=;#\n':text=text.replace(c,'\\'+c)
    return text

def font(size):
    from PIL import ImageFont
    path=subprocess.check_output(['fc-match','-f','%{file}','Ubuntu Sans'],text=True).strip()
    return ImageFont.truetype(path,size)

def wrap(text, selected, width, scale=1):
    lines=[];line=''
    for word in text.split():
        if selected.getlength(word)*scale>width:raise ValueError('A word cannot fit the caption/card area')
        candidate=(line+' '+word).strip()
        if line and selected.getlength(candidate)*scale>width:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines

def layout(card, show, number, output):
    from PIL import Image, ImageDraw, ImageOps
    image=Image.new('RGB',(1920,1080),'#091423');d=ImageDraw.Draw(image)
    d.text((61,25),f'{show}  ·  {number}',font=font(38),fill='#f7931a')
    d.line((61,82,1859,82),fill='#415066',width=2)
    title=wrap(card['title'],font(62),1700)
    if len(title)>3:raise ValueError('Slide title exceeds three lines')
    top=122
    for line in title:d.text((90,top),line,font=font(62),fill='white');top+=78
    if card.get('image'):
        capture=Image.open(card['image']).convert('RGB')
        capture=ImageOps.contain(capture,(1710,max(80,600-top)))
        image.paste(capture,((1920-capture.width)//2,top+10))
    else:
        text=card.get('body') or card.get('source',{}).get('excerpt','')
        lines=wrap(text,font(40),1700)
        if len(lines)>max(1,(620-top)//51):raise ValueError('Slide body exceeds source area; split the slide')
        for line in lines:d.text((90,top+20),line,font=font(40),fill='#c1ccd9');top+=51
    if card.get('source'):
        label=card['source']['url'];lines=wrap(label,font(23),1700)
        if len(lines)>2:raise ValueError('Source URL does not fit')
        for i,line in enumerate(lines):d.text((90,649+i*27),line,font=font(23),fill='#a2b1c5')
    d.line((61,769,1859,769),fill='#415066',width=2)
    image.save(output)

def timeline(config, duration):
    edits=config.get('edit', [{'source_start':0,'source_end':duration}]);result=[];out=0;previous=0
    for edit in edits:
        if set(edit)=={'source_start','source_end'}:
            a,b=edit['source_start'],edit['source_end']
            if not all(map(finite,(a,b))) or not 0<=a<b<=duration or a<previous:raise ValueError('Keep intervals must be finite, ordered and within audio')
            result.append(dict(start=out,end=out+b-a,source_start=a,source_end=b));out+=b-a;previous=b
        elif set(edit)=={'silence_duration','title'}:
            n=edit['silence_duration']
            if not finite(n) or not 0<n<=120 or not edit['title']:raise ValueError('Silence card requires title and duration 0..120')
            result.append(dict(start=out,end=out+n,title=edit['title']));out+=n
        else:raise ValueError('Unknown edit fields')
    if not result:raise ValueError('Empty edit')
    return result,out

def map_cues(cues, segments):
    result=[];expected=[]
    for cue in cues:
        overlaps=[s for s in segments if 'source_start' in s and cue['end']>s['source_start'] and cue['start']<s['source_end']]
        if not overlaps:continue
        if len(overlaps)!=1 or cue['start']<overlaps[0]['source_start'] or cue['end']>overlaps[0]['source_end']:
            raise ValueError('An edit crosses a transcript cue; split/review its word timing first')
        s=overlaps[0];result.append(dict(cue,start=cue['start']-s['source_start']+s['start'],end=cue['end']-s['source_start']+s['start']))
        expected.append(cue['text'])
    if not result:raise ValueError('Edit retains no transcript')
    if norm(' '.join(expected))!=norm(' '.join(c['text'] for c in result)):raise ValueError('Edited words changed')
    return result

def map_slides(plan,segments):
    result=[]
    for s in segments:
        if 'title' in s:result.append(dict(start=s['start'],end=s['end'],title=s['title'],kind='topic'));continue
        for card in plan['slides']:
            a=max(card['start'],s['source_start']);b=min(card['end'],s['source_end'])
            if a<b:result.append(dict(card,start=a-s['source_start']+s['start'],end=b-s['source_start']+s['start']))
    if not result or result[0]['start']!=0 or any(abs(a['end']-b['start'])>.001 for a,b in zip(result,result[1:])) or abs(result[-1]['end']-segments[-1]['end'])>.001:
        raise ValueError('Slides must cover the entire edited timeline without gaps')
    return result

def prepare(config_path, out, parent=None, feedback=None):
    config_path=config_path.resolve();config=e.read(config_path)
    def resolve(p):return (config_path.parent/p).resolve(strict=True)
    audio=resolve(config['audio']);transcript_path=resolve(config['transcript']);plan_path=resolve(config['slides'])
    transcript=e.read(transcript_path);plan=e.read(plan_path);slides.validate(transcript,plan)
    duration=float(hls.probe(audio)['format']['duration'])
    if abs(duration-transcript['duration'])>.25:raise ValueError('Transcript duration differs from full source audio')
    segments,edited_duration=timeline(config,transcript['duration']);cues=map_cues(transcript['cues'],segments)
    if any(a['end']>b['start']+.001 for a,b in zip(cues,cues[1:])):raise ValueError('Caption cues overlap; review timing before rendering')
    cards=map_slides(plan,segments)
    sources={'config':e.file_record(config_path),'audio':e.file_record(audio),'transcript':e.file_record(transcript_path),'slides':e.file_record(plan_path)}
    if feedback:sources['feedback']=e.file_record(feedback)
    if parent:
        verify_prepared(parent);sources['parent']=e.file_record(parent/'prepared.json')
        if not feedback:raise ValueError('A revision requires saved feedback')
    speakers=config['speakers']
    if set(c['speaker'] for c in cues)-set(speakers):raise ValueError('Missing speaker portrait configuration')
    for name,value in speakers.items():sources['portrait:'+name]=e.file_record(resolve(value))
    for i,card in enumerate(cards):
        if card.get('image'):
            card['image']=str(resolve(card['image']));sources['image:'+str(i)]=e.file_record(card['image'])
    selected=font(52);scale=52/sum(selected.getmetrics());lines=[]
    for cue in cues:
        wrapped=wrap(cue['text'],selected,1549,scale)
        if len(wrapped)>4:raise ValueError('Caption exceeds four lines; revise cue boundaries using word timing')
        lines.append(wrapped)
    out=e.private_root(out.parent)/out.name;out.mkdir(mode=0o700)
    for name in ('assets','scenes','output'): (out/name).mkdir(mode=0o700)
    if feedback:shutil.copyfile(feedback,out/'feedback.txt')
    e.save(out/'transcript.json',transcript);e.save(out/'slides.json',plan)
    for i,card in enumerate(cards):layout(card,config['show'],str(config['episode']),out/'scenes'/f'{i:04d}.png')
    for i,name in enumerate(speakers):
        from PIL import Image, ImageOps
        ImageOps.fit(Image.open(sources['portrait:'+name]['path']).convert('RGB'),(180,180)).save(out/'assets'/f'portrait-{i}.png')
    chapters=config.get('chapters',[{'start':0,'title':transcript.get('title',config['show'])}])
    mapped=[]
    for chapter in chapters:
        t=chapter['start']
        if not finite(t) or not 0<=t<transcript['duration'] or not chapter['title']:raise ValueError('Invalid chapter')
        for s in segments:
            if 'source_start' in s and s['source_start']<=t<s['source_end']:mapped.append(dict(start=t-s['source_start']+s['start'],title=chapter['title']))
    mapped.sort(key=lambda c:c['start'])
    if not mapped or mapped[0]['start']!=0 or any(a['start']>=b['start'] for a,b in zip(mapped,mapped[1:])):raise ValueError('Edited chapters must start at zero and have unique times')
    meta=[';FFMETADATA1']
    for i,c in enumerate(mapped):meta += ['[CHAPTER]','TIMEBASE=1/1000',f'START={round(c["start"]*1000)}',f'END={round((mapped[i+1]["start"] if i+1<len(mapped) else edited_duration)*1000)}','title='+ffmeta(c['title'])]
    (out/'assets/chapters.ffmeta').write_text('\n'.join(meta)+'\n');e.save(out/'chapters.json',mapped)
    (out/'chapters.txt').write_text('\n'.join(vtt_time(c['start']).split('.')[0]+' '+c['title'] for c in mapped)+'\n')
    vtt=['WEBVTT',''];ass=['[Script Info]','ScriptType: v4.00+','PlayResX: 1920','PlayResY: 1080','WrapStyle: 2','[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        'Style: Default,Ubuntu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00142309,&H00142309,0,0,0,0,100,100,0,0,1,1,0,7,290,61,792,1',
        '[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    for cue,wrapped in zip(cues,lines):
        vtt += [vtt_time(cue['start'])+' --> '+vtt_time(cue['end']),html.escape(cue['text']),'']
        ass.append(f'Dialogue: 0,{ass_time(cue["start"])},{ass_time(cue["end"])},Default,,0,0,0,,{ass_escape(chr(10).join(wrapped))}')
    (out/'captions.vtt').write_text('\n'.join(vtt)+'\n');(out/'assets/captions.ass').write_text('\n'.join(ass)+'\n')
    e.save(out/'edited-cues.json',cues)
    prepared=dict(schema=1,show=config['show'],episode=str(config['episode']),duration=edited_duration,segments=segments,cues=cues,cards=cards,speakers=list(speakers),sources=sources,chapters=mapped,metadata=config.get('metadata'),
        font=e.file_record(Path(selected.path)),tools={str(x.relative_to(Path(__file__).parent)):e.file_record(x) for x in [Path(__file__),*Path(__file__).parent.joinpath('video').glob('*.py')]},ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],status='prepared')
    prepared['files']={str(p.relative_to(out)):e.file_record(p) for p in out.rglob('*') if p.is_file()}
    e.save(out/'prepared.json',prepared);verify_prepared(out);return prepared

def verify_prepared(out):
    p=e.read(out/'prepared.json')
    for record in [*p['sources'].values(),*p['files'].values(),p['font']]:
        if e.file_record(record['path'])!=record:raise ValueError('A prepared input or intermediate changed; create a new revision')
    return p

def audio_edit(out,p):
    dest=out/'assets/audio.wav'
    if dest.exists():raise ValueError('Partial audio exists; inspect and create a fresh revision directory')
    graph=[];labels=[]
    for i,s in enumerate(p['segments']):
        if 'source_start' in s:graph.append(f'[0:a]atrim=start={s["source_start"]}:end={s["source_end"]},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]')
        else:graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={s["end"]-s["start"]}[a{i}]')
        labels.append(f'[a{i}]')
    graph.append(''.join(labels)+f'concat=n={len(labels)}:v=0:a=1[a]')
    ff('-i',p['sources']['audio']['path'],'-filter_complex',';'.join(graph),'-map','[a]','-c:a','pcm_s16le',dest,log=out/'audio.log')

def render_video(out,p,height=1080):
    master=height==1080;fps=30 if master else 15
    dest=out/'output'/('master.mp4' if master else f'{height}p.mp4');concat=[]
    for i,c in enumerate(p['cards']):
        name=f'{i:04d}.nut'
        if not (out/'scenes'/name).exists():ff('-i',out/'scenes'/f'{i:04d}.png','-vf',COLOR,'-frames:v',1,'-r',30,'-c:v','ffv1',out/'scenes'/name)
        concat += [f"file '{name}'",f'duration {c["end"]-c["start"]:.6f}']
    concat.append(f"file '{len(p['cards'])-1:04d}.nut'");(out/'scenes/concat.txt').write_text('\n'.join(concat)+'\n')
    args=['-filter_complex_threads','2','-f','concat','-safe','1','-i',out/'scenes/concat.txt','-i',out/'assets/audio.wav','-i',out/'assets/chapters.ffmeta']
    graph=[f'[0:v]fps={fps},setsar=1[base]', '[1:a]asplit=2[audio][wavein]',
        f'[wavein]showwaves=s=1340x54:mode=cline:rate={fps}:colors=white,format=rgba,colorchannelmixer=rr=0.969:gg=0.576:bb=0.102,colorkey=0x000000:0.16:0.08,format=yuva420p[wave]',
        '[base][wave]overlay=290:712:shortest=1[background]']
    prev='background'
    for i,name in enumerate(p['speakers']):
        args+=['-loop','1','-i',out/'assets'/f'portrait-{i}.png']
        windows=[c for c in p['cues'] if c['speaker']==name]
        enable='+'.join(f'gte(t,{c["start"]})*lt(t,{c["end"]})' for c in windows) or '0'
        graph += [f'[{i+3}:v]{COLOR}[p{i}]',f"[{prev}][p{i}]overlay=61:792:shortest=1:enable='{enable}'[speaker{i}]"];prev=f'speaker{i}'
    # Keep filter paths relative and fixed; user-controlled paths never become filter syntax.
    graph.append(f"[{prev}]subtitles=assets/captions.ass:original_size=1920x1080,format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]")
    if not master:graph[-1]=graph[-1].replace('[v]',f',scale={SIZES[height]}:{height}[v]')
    args+=['-filter_complex',';'.join(graph),'-map','[v]','-map','[audio]','-map_metadata','2','-map_chapters','2','-t',p['duration'],'-r',fps]
    if master:args+=['-c:v','libx264','-threads','4','-preset','medium','-crf','18','-profile:v','high','-level','4.2','-g','15','-sc_threshold','0']
    else:args+=['-c:v','libsvtav1','-preset','5','-crf','32','-g','90','-svtav1-params','lp=4:scd=0']
    args+=['-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv',
        '-c:a','aac','-profile:a','aac_low','-b:a','384k' if master else '64k','-ar','48000','-ac','2' if master else '1','-avoid_negative_ts','disabled','-movflags','+faststart','-use_editlist','0',dest]
    stem='master' if master else f'{height}p'
    e.save(out/(stem+'-command.json'),[str(x) for x in args])
    with (out/(stem+'.log')).open('wb') as log:subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','warning','-n',*map(str,args)],cwd=out,stdout=log,stderr=log,check=True)
    verify_media(dest,p,master=master)

def verify_media(path,p,master=False):
    info=hls.probe(path);v=hls.stream(info,'video');a=hls.stream(info,'audio');duration=float(info['format']['duration'])
    if abs(duration-p['duration'])>.15 or v['codec_name']!=('h264' if master else 'av1') or a['codec_name']!='aac':raise ValueError('Rendered codec/duration mismatch')
    if any(v.get(k)!='bt709' for k in ('color_space','color_transfer','color_primaries')) or v.get('color_range')!='tv':raise ValueError('Incorrect output colour metadata')
    chapters=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_chapters','-of','json',str(path)]))['chapters']
    if len(chapters)!=len(p['chapters']) or any(c['tags']['title']!=expected['title'] or abs(float(c['start_time'])-expected['start'])>.15 for c,expected in zip(chapters,p['chapters'])):raise ValueError('Rendered chapter metadata differs')
    audio_check=alignment(path.parent.parent/'assets/audio.wav',path,p['duration'],max_delay=.15)
    atoms=mp4_atoms(path);top={x['type']:x for x in atoms if '/' not in x['type']}
    if top['moov']['offset']>top['mdat']['offset'] or any(x['type'].endswith('/elst') for x in atoms):raise ValueError('MP4 must fast-start without edit lists')
    ff('-threads','2','-i',path,'-map','0:v:0','-map','0:a:0','-f','null','-',log=path.with_suffix('.decode.log'))
    packets=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts_time,flags','-of','json',str(path)]))['packets']
    keys=[float(x['pts_time']) for x in packets if 'K' in x['flags']]
    gaps=[b-a for a,b in zip(keys,keys[1:])]+[duration-keys[-1]]
    r=e.file_record(path);report=dict(file=str(path),sha256=r['sha256'],bytes=r['size'],full_decode_passed=True,fast_start=True,no_edit_lists=True,
        normalized_retained_spoken_words_preserved=True,transcript_sha256=p['sources']['transcript']['sha256'],source_audio_sha256=p['sources']['audio']['sha256'],video_edit=p['segments'],max_keyframe_gap_seconds=max(gaps),probe=info,audio_alignment=audio_check)
    e.save(path.with_suffix('.verification.json'),report);return report

def verify_render(out):
    result=e.read(out/'render.json')
    for record in [*result['files'].values(),result['av1']]:
        if e.file_record(record['path'])!=record:raise ValueError('Completed render artifact changed; prepare a new revision')
    return result

def render(out):
    p=verify_prepared(out)
    # A completed stage is reusable only after all saved bytes are revalidated.
    manifest=out/'render.json'
    if manifest.exists():
        return verify_render(out)
    audio_edit(out,p);render_video(out,p)
    renditions=[]
    for height,width in list(SIZES.items())[1:]:
        path=out/'output'/f'{height}p.mp4'
        render_video(out,p,height);renditions.append(dict(label=f'{height}p',path=str(path),verification=str(path.with_suffix('.verification.json'))))
    # The fallback is the independently downloadable exact 480p rendition.
    fallback=dict(next(x for x in renditions if x['label']=='480p'))
    av1=dict(version=1,expected_duration_seconds=p['duration'],renditions=renditions,fallback=fallback)
    e.save(out/'av1.json',av1)
    thumbnail(out,p)
    if p.get('metadata') is not None:
        from video.youtube import metadata
        meta=dict(p['metadata']);meta['description']=meta['description'].rstrip()+'\n\n'+(out/'chapters.txt').read_text().strip()
        metadata(meta);e.save(out/'output/metadata.json',meta)
    verify_prepared(out)
    result=dict(schema=1,status='rendered',files={str(x.relative_to(out)):e.file_record(x) for x in (out/'output').glob('*') if x.is_file()},av1=e.file_record(out/'av1.json'))
    e.save(manifest,result);return result

def thumbnail(out,p):
    from PIL import Image, ImageDraw, ImageOps
    image=Image.new('RGB',(1280,720),'#091423');d=ImageDraw.Draw(image)
    d.text((45,40),p['show'],font=font(54),fill='#f7931a')
    title=e.read(out/'transcript.json').get('title','Episode '+p['episode']);lines=wrap(title,font(74),1180)
    if len(lines)>4:raise ValueError('Thumbnail title too long; provide a shorter transcript title')
    for i,line in enumerate(lines):d.text((45,140+i*90),line,font=font(74),fill='white')
    for i,_ in enumerate(p['speakers'][:5]):image.paste(ImageOps.fit(Image.open(out/'assets'/f'portrait-{i}.png'),(150,150)),(45+i*180,540))
    image.save(out/'output/thumbnail.jpg',quality=93)

def package(out,destination):
    p=verify_prepared(out);verify_render(out)
    av1_packaging.prepare(SimpleNamespace(manifest=out/'av1.json',output=destination),hls)
    verify_hls.verify(destination,True)

def fixture(out):
    from PIL import Image
    out=e.private_root(out)
    for i,name in enumerate(('Host','Guest')):Image.new('RGB',(220,220),('#f7931a','#23abb8')[i]).save(out/f'{name}.png')
    ff('-f','lavfi','-i','aevalsrc=0.22*sin(2*PI*(180*t+80*t*t))*(0.4+0.6*sin(2*PI*1.37*t)^2):s=48000:d=20','-ar','48000','-ac','2',out/'audio.wav')
    examples=Path(__file__).resolve().parent.parent/'examples'
    for name in ('transcript.json','slides.json'):shutil.copyfile(examples/name,out/name)
    config=dict(show='Synthetic Podcast',episode='fixture',audio='audio.wav',transcript='transcript.json',slides='slides.json',speakers={x:x+'.png' for x in ('Host','Guest')},metadata=dict(title='Synthetic workflow demonstration',description='Local validation fixture.',category_id='28',language='en',tags=['fixture'],made_for_kids=False,contains_synthetic_media=False),chapters=[dict(start=0,title='Sources'),dict(start=10,title='Review')])
    e.save(out/'production.json',config);return out/'production.json'

def register(args):
    out=args.revision.resolve();p=verify_prepared(out);verify_render(out)
    if p['episode']!=args.episode:raise ValueError('Prepared episode ID differs from journal selection')
    bundle=hls.validate_bundle(args.bundle)
    if bundle['fallback_sha256']!=hls.digest(out/'output/480p.mp4'):raise ValueError('Bundle fallback differs from render')
    paths=dict(video=out/'output/master.mp4',fallback=out/'output/480p.mp4',thumbnail=out/'output/thumbnail.jpg',metadata=out/'output/metadata.json',
        captions=out/'captions.vtt',slides=out/'slides.json',transcript=out/'transcript.json',audio=Path(p['sources']['audio']['path']),nostr_metadata=args.nostr_metadata.resolve(),nostr_bundle=args.bundle.resolve()/'bundle.json')
    with e.journal(args.root) as (root,data):
        item=e.episode(data,args.show,args.episode);result=e.revision(item,args.id,{k:str(v) for k,v in paths.items()})
    return result

def main():
    os.umask(0o077);ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('fixture');p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('register');p.add_argument('--root',type=Path,required=True);p.add_argument('--revision',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--nostr-metadata',type=Path,required=True)
    for name in ('show','episode','id'):p.add_argument('--'+name,required=True)
    p=sub.add_parser('prepare');p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--parent',type=Path);p.add_argument('--feedback',type=Path)
    for name in ('render','verify','package'):
        p=sub.add_parser(name);p.add_argument('--revision',type=Path,required=True)
        if name=='package':p.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if args.command=='fixture':print(fixture(args.out.resolve()));return
    if args.command=='register':print(json.dumps(register(args),indent=2));return
    if args.command=='prepare':prepare(args.config,args.out.resolve(),args.parent.resolve() if args.parent else None,args.feedback);print(args.out/'prepared.json');return
    out=args.revision.resolve()
    # One writer per immutable revision; a background worker uses this same CLI.
    import fcntl
    with (out/'.render.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='render':render(out)
        elif args.command=='verify':verify_prepared(out);print('Prepared inputs and intermediates unchanged')
        elif args.command=='package':package(out,args.out.resolve())

if __name__=='__main__':failures.cli(main,sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in failures.STAGES else 'unknown')
