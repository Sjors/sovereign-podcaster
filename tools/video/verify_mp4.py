import struct

def mp4_atoms(path):
    containers={b"moov",b"trak",b"mdia",b"minf",b"stbl",b"edts"}
    found=[]
    with path.open("rb") as handle:
        def walk(start,end,prefix=""):
            position=start
            while position+8<=end:
                handle.seek(position)
                size,name=struct.unpack(">I4s",handle.read(8))
                header=8
                if size==1:
                    size=struct.unpack(">Q",handle.read(8))[0]; header=16
                elif size==0: size=end-position
                assert size>=header and position+size<=end
                label=prefix+name.decode("ascii",errors="replace")
                found.append({"type":label,"offset":position,"size":size})
                if name in containers: walk(position+header,position+size,label+"/")
                position+=size
        walk(0,path.stat().st_size)
    return found

from array import array
import subprocess
from math import sqrt

def audio_samples(path,start,duration=8):
    samples=array("f")
    samples.frombytes(subprocess.check_output([
        "ffmpeg","-hide_banner","-loglevel","error","-ss",str(start),"-i",str(path),
        "-t",str(duration),"-vn","-ac","1","-ar","12000","-f","f32le","-"
    ]))
    return samples

def dot_at_lag(a,b,lag):
    a_start,b_start=max(0,-lag),max(0,lag)
    length=min(len(a)-a_start,len(b)-b_start)
    return sum(x*y for x,y in zip(a[a_start:a_start+length],b[b_start:b_start+length]))

def alignment(reference, rendered, duration, max_delay=.1):
    observations=[]
    span=min(6,duration/3)
    for position in sorted(set((0,max(0,duration/2-span/2),max(0,duration-span-.3)))):
        a=audio_samples(reference,position,span);b=audio_samples(rendered,position,span)
        length=min(len(a),len(b));a=a[:length];b=b[:length]
        power=dot_at_lag(a,a,0)
        if power>=1e-8 and dot_at_lag(b,b,0)<1e-8:raise ValueError('Rendered audio is silent where source audio is present')
        if power<1e-8:
            if dot_at_lag(b,b,0)>1e-6:raise ValueError('Expected silence differs from rendered audio')
            observations.append(dict(at_seconds=position,silence=True));continue
        envelope=lambda samples:array('f',(sum(abs(x) for x in samples[i:i+12]) for i in range(0,len(samples)-11,12)))
        aa,bb=envelope(a),envelope(b)
        mean_a,mean_b=sum(aa)/len(aa),sum(bb)/len(bb)
        aa=array('f',(x-mean_a for x in aa));bb=array('f',(x-mean_b for x in bb))
        limit=round(max_delay*1000)
        coarse=max(range(-limit,limit+1),key=lambda lag:dot_at_lag(aa,bb,lag))
        window=min(12000,length)
        begin=max(range(0,max(1,length-window+1),window),key=lambda i:dot_at_lag(a[i:i+window],a[i:i+window],0))
        aa,bb=a[begin:begin+window],b[begin:begin+window]
        lag=max(range(coarse*12-120,coarse*12+121),key=lambda n:dot_at_lag(aa,bb,n))
        if lag>=0:x,y=a[:length-lag],b[lag:]
        else:x,y=a[-lag:],b[:length+lag]
        correlation=dot_at_lag(x,y,0)/sqrt(dot_at_lag(x,x,0)*dot_at_lag(y,y,0))
        if correlation<.94 or abs(lag/12000)>max_delay:raise ValueError(f'Rendered audio alignment/content check failed at {position:.2f}s: correlation {correlation:.3f}, delay {lag/12000:.4f}s')
        observations.append(dict(at_seconds=position,delay_seconds=lag/12000,correlation=correlation))
    return observations
