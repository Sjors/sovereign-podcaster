#!/usr/bin/env python3
"""Bounded local recognition, speaker comparisons and source-clock evidence for transcript review."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import wave
import episodes as e
import failures


def windows(value,seconds):
    if not isinstance(value,list) or not value:raise ValueError('Supply a nonempty window list')
    for item in value:
        start,end=item['start'],item['end']
        if type(start) not in (int,float) or type(end) not in (int,float) or not 0<=start<end<=seconds or end-start>90:raise ValueError('Review windows must be within the source and at most 90 seconds')
    return value


def clock(folder):
    records={}
    for name in ('audio-native.wav','audio-16k.wav'):
        with wave.open(str(folder/name)) as f:records[name]=dict(samples=f.getnframes(),rate=f.getframerate(),channels=f.getnchannels(),seconds=f.getnframes()/f.getframerate())
    source=folder/'published.mp3'
    def probe(args):return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','a:0',*args,'-of','json',str(source)]))
    return dict(decoded=records,ffprobe=probe(['-show_entries','format=duration,start_time:stream=sample_rate,start_time,duration']),first_audio_packet=probe(['-read_intervals','%+#1','-show_packets'])['packets'],source=e.file_record(source),note='Evidence only; compare actual skip/discard, decoded clock and boundaries before choosing offsets.')


def recognize(config,folder,selected,kind):
    from faster_whisper import WhisperModel
    import soundfile as sf
    audio,rate=sf.read(folder/'audio-16k.wav',dtype='float32')
    model=WhisperModel(config[kind+'_model'],device='cpu',compute_type='int8',cpu_threads=config.get('cpu_threads',8),local_files_only=True)
    output=[]
    for item in windows(selected,len(audio)/rate):
        start,end=item['start'],item['end']
        segments,_=model.transcribe(audio[round(start*rate):round(end*rate)],language='en',beam_size=5,temperature=0,word_timestamps=True,vad_filter=False,condition_on_previous_text=False)
        result=[]
        for s in segments:
            result.append(dict(start=s.start+start,end=s.end+start,text=s.text,words=[dict(start=w.start+start,end=w.end+start,word=w.word,probability=w.probability) for w in s.words]))
        output.append(dict(window=item,segments=result))
    return dict(model=kind,model_path=config[kind+'_model'],windows=output,note='Bounded ASR is additional evidence, not a replacement for raw recognition or proof of wording.')


def speakers(config,folder,selected,references):
    import numpy as np
    import soundfile as sf
    import sherpa_onnx
    audio,rate=sf.read(folder/'audio-16k.wav',dtype='float32');seconds=len(audio)/rate
    if not isinstance(references,dict) or len(references)<2:raise ValueError('Provide at least two episode-specific reference labels')
    extractor=sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=config['embedding_model'],num_threads=config.get('cpu_threads',8)))
    def embed(item):
        stream=extractor.create_stream();stream.accept_waveform(rate,audio[round(item['start']*rate):round(item['end']*rate)]);stream.input_finished()
        if not extractor.is_ready(stream):return None
        value=np.array(extractor.compute(stream));norm=np.linalg.norm(value)
        return value/norm if norm>0 else None
    centers={}
    for name,refs in references.items():
        values=[embed(item) for item in windows(refs,seconds)]
        if any(v is None for v in values):raise ValueError('A reference is too short for an embedding')
        center=np.mean(values,axis=0);norm=np.linalg.norm(center)
        if norm==0:raise ValueError('Reference centroid is empty')
        centers[name]=center/norm
    output=[]
    for item in windows(selected,seconds):
        value=embed(item)
        output.append(dict(window=item,cosine=None if value is None else {name:round(float(value@center),4) for name,center in centers.items()}))
    return dict(references=references,windows=output,note='Same-episode cosine support only. Short or overlapping fragments may be unreliable; scores do not establish identities or approve attribution.')


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--folder',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    s=p.add_subparsers(dest='action',required=True);s.add_parser('clock')
    for name in ('recognize','speakers'):
        q=s.add_parser(name);q.add_argument('--windows',type=Path,required=True)
        if name=='recognize':q.add_argument('--model',choices=['primary','secondary'],default='secondary')
        else:q.add_argument('--references',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise ValueError('Preserve earlier evidence; choose a fresh output path')
    config=e.read(a.config);episode=e.read(a.folder/'episode.json')
    if e.file_record(a.folder/'published.mp3')['sha256']!=episode['final_audio_sha256']:raise ValueError('Source differs from selected final audio')
    if a.action=='clock':result=clock(a.folder)
    elif a.action=='recognize':result=recognize(config,a.folder,e.read(a.windows),a.model)
    else:result=speakers(config,a.folder,e.read(a.windows),e.read(a.references))
    result.update(created_at=e.now(),episode_guid=episode['guid'],source_audio_sha256=episode['final_audio_sha256'])
    # Exclusive creation prevents accidentally replacing an earlier review result.
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(evidence=str(a.out),operation=a.action,windows=len(result.get('windows',[])))))
if __name__=='__main__':failures.cli(main,'transcript')
