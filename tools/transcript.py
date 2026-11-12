#!/usr/bin/env python3
"""Import a reviewed speaker-labelled WebVTT transcript; no transcription service."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import episodes as e
import failures
from video import hls
import slides

def timestamp(value):
    if not re.fullmatch(r'(?:[0-9]{2,}:)?[0-5][0-9]:[0-5][0-9]\.[0-9]{3}',value):raise ValueError('Expected WebVTT timestamp')
    return sum(float(p)*60**i for i,p in enumerate(reversed(value.split(':'))))

def parse(raw,default_speaker=None):
    raw=raw.lstrip('\ufeff').replace('\r\n','\n')
    if not raw.startswith('WEBVTT'):raise ValueError('Expected a complete WEBVTT file')
    cues=[]
    for block in re.split(r'\n\s*\n',raw):
        lines=block.splitlines()
        if not any('-->' in line for line in lines):
            if lines and not (lines[0].startswith(('WEBVTT','NOTE','STYLE','REGION'))):raise ValueError('Unrecognized transcript block; do not silently discard text')
            continue
        timing=[i for i,line in enumerate(lines) if '-->' in line]
        if len(timing)!=1:raise ValueError('Ambiguous cue')
        i=timing[0];match=re.fullmatch(r'(\S+)\s+-->\s+(\S+)(?:\s+.*)?',lines[i])
        if not match:raise ValueError('Malformed cue timing')
        text=' '.join(x.strip() for x in lines[i+1:]).strip();voice=re.match(r'<v\s+([^>]+)>',text)
        speaker=voice[1] if voice else default_speaker
        if not speaker:raise ValueError('Every cue needs a voice label or an explicitly selected default speaker')
        if voice:text=text[voice.end():]
        text=re.sub(r'</?(?:v|b|i|u|c(?:\.[^> ]+)?)>','',text)
        if re.search('<[^>]+>',text):raise ValueError('Unsupported inline markup; review rather than silently dropping it')
        cues.append(dict(start=timestamp(match[1]),end=timestamp(match[2]),speaker=speaker,text=html.unescape(text)))
    if not cues:raise ValueError('No transcript cues')
    return cues

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    for name in ('vtt','audio','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--title',required=True);p.add_argument('--default-speaker');a=p.parse_args()
    cues=parse(a.vtt.read_text(),a.default_speaker);duration=float(hls.probe(a.audio)['format']['duration'])
    for cue in cues:slides.interval(cue,duration)
    if any(x['start']>y['start'] for x,y in zip(cues,cues[1:])):raise ValueError('Cues must be ordered')
    result=dict(title=a.title,duration=duration,cues=cues,source=e.file_record(a.vtt),audio=e.file_record(a.audio))
    # Reserve rather than replacing a reviewed transcript in place.
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(a.out)
if __name__=='__main__':failures.cli(main,'transcript')
