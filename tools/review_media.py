#!/usr/bin/env python3
"""Encode the established fallback, or stage a short encrypted-chat review clip."""
import argparse
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from episodes import file_record, private_root, save


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def inspect_fallback(path):
    info=probe(path);video=[x for x in info['streams'] if x['codec_type']=='video'];audio=[x for x in info['streams'] if x['codec_type']=='audio']
    if len(video)!=1 or len(audio)!=1:raise ValueError('Fallback requires exactly one video and one audio stream')
    v,a=video[0],audio[0]
    if (v['codec_name'],v['width'],v['height'],Fraction(v['avg_frame_rate']))!=('av1',854,480,Fraction(15)):raise ValueError('Fallback must be 854x480 AV1 at 15 fps')
    if a['codec_name']!='aac' or a.get('profile')!='LC' or int(a['sample_rate'])!=48000 or a['channels']!=1:raise ValueError('Fallback audio must be AAC-LC, 48 kHz, mono')
    return {'video_codec':'av1','width':854,'height':480,'fps':15,'audio_codec':'aac','duration':float(info['format']['duration'])}

def encode(source,out,fragment=None):
    original=file_record(source);source=Path(original['path']);out=Path(out).absolute()
    if out.exists():raise ValueError('Output directory exists; keep revisions immutable')
    private_root(out.parent);out.mkdir(mode=0o700)
    dest=out/('clip.mp4' if fragment else 'fallback.mp4')
    cmd=['ffmpeg','-nostdin','-v','error','-n']
    if fragment:cmd+=['-ss',str(fragment[0])]
    cmd+=['-i',str(source)]
    if fragment:cmd+=['-t',str(fragment[1])]
    cmd+=['-map','0:v:0','-map','0:a:0','-vf','scale=854:480:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=15']
    if fragment:cmd+=['-c:v','libx264','-preset','medium','-crf','23','-pix_fmt','yuv420p']
    else:cmd+=['-c:v','libsvtav1','-preset','5','-crf','32','-g','90','-svtav1-params','lp=4:tune=0:scd=0','-pix_fmt','yuv420p']
    cmd+=['-c:a','aac','-b:a','64k','-ac','1','-ar','48000','-map_metadata','-1','-movflags','+faststart',str(dest)]
    save(out/'job.json',{'state':'running','source':original,'command':cmd,'fragment':fragment})
    try:
        with (out/'ffmpeg.log').open('w') as log:
            subprocess.run(cmd,stderr=log,check=True)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(dest),'-map','0:v:0','-map','0:a:0','-f','null','-'],stderr=log,check=True)
        if file_record(source)!=original:raise ValueError('Source changed during encode; preserve output for inspection')
        info=probe(dest);duration=float(info['format']['duration']);expected=fragment[1] if fragment else float(probe(source)['format']['duration'])
        if abs(duration-expected)>.25:raise ValueError('Encoded duration differs from selected interval')
        if not fragment:inspect_fallback(dest)
        result={'state':'verified','source':original,'output':file_record(dest),'command':cmd,'duration':duration,'fragment':fragment,'full_decode_passed':True}
        save(out/'job.json',result);return result
    except BaseException as error:
        save(out/'job.json',{'state':'failed','source':original,'command':cmd,'fragment':fragment,'error_type':type(error).__name__})
        raise


def stage_fragment(home,identifier,source,start,duration,account,group,caption):
    from episodes import slug
    slug(identifier)
    if not re.fullmatch('[0-9a-f]{64}',account) or not re.fullmatch('(?:[0-9a-f]{2})+',group):raise ValueError('Supply the exact trusted account and group')
    if start<0 or not 0<duration<=120:raise ValueError('Review clip must be 0–120 seconds, with a nonnegative start')
    home=private_root(home);staging=private_root(home/'media-uploads')
    result=encode(source,staging/identifier,(start,duration));f=result['output']
    manifest={'account_id_hex':account,'group_id_hex':group,'caption':caption,
              'idempotency_key':'review-'+identifier,'attachments':[{'path':f['path'],'media_type':'video/mp4','file_name':'clip.mp4','sha256':f['sha256'],'size':f['size']}]}
    path=staging/identifier/'send.json';save(path,manifest)
    return {'manifest':str(path),'video':f,'sent':False}

def background_fallback(source,out):
    """One durable encode process; no daemon, model polling or inherited API key."""
    source=Path(source).resolve(strict=True);out=Path(out).absolute()
    private_root(out.parent)
    launch=out.with_name(out.name+'.launcher.json');log=out.with_name(out.name+'.launcher.log')
    if out.exists() or launch.exists() or log.exists():raise ValueError('Render launch already exists; inspect it instead of launching twice')
    cmd=[sys.executable,str(Path(__file__).resolve()),'fallback','--input',str(source),'--out',str(out)]
    fd=os.open(launch,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump({'state':'starting','command':cmd,'output_directory':str(out)},f);f.flush();os.fsync(f.fileno())
    # Detach the encode from a bounded model turn. Never inherit API credentials.
    with log.open('x') as output:
        child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
            env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True)
    result={'state':'launched','pid':child.pid,'command':cmd,'output_directory':str(out),'result':str(out/'job.json')}
    save(launch,result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    f=s.add_parser('fallback');f.add_argument('--input',type=Path,required=True);f.add_argument('--out',type=Path,required=True);f.add_argument('--background',action='store_true',help='Detach the logged encode so it survives the model-turn timeout')
    c=s.add_parser('fragment');c.add_argument('--input',type=Path,required=True);c.add_argument('--home',type=Path,required=True);c.add_argument('--id',required=True)
    c.add_argument('--start',type=float,required=True);c.add_argument('--duration',type=float,required=True);c.add_argument('--caption',required=True)
    c.add_argument('--account',default=os.environ.get('MARMOT_ACCOUNT_ID_HEX'));c.add_argument('--group',default=os.environ.get('MARMOT_GROUP_ID_HEX'))
    args=p.parse_args();os.umask(0o077)
    if args.command=='fallback':result=background_fallback(args.input,args.out) if args.background else encode(args.input,args.out)
    else:result=stage_fragment(args.home,args.id,args.input,args.start,args.duration,args.account or '',args.group or '',args.caption)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
