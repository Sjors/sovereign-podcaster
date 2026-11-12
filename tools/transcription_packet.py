#!/usr/bin/env python3
"""Read-only, paginated transcript review packet; no recognition, edits or network calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import episodes as e
import failures


def groups(words,flags):
    batches=[]
    for flag in sorted(flags,key=lambda x:x['word_index']):
        index=flag['word_index']
        if batches and index<=batches[-1][-1]['word_index']+4:batches[-1].append(flag)
        else:batches.append([flag])
    result=[]
    for batch in batches:
        lo,hi=batch[0]['word_index'],batch[-1]['word_index']
        result.append(dict(start_word_index=lo,end_word_index_exclusive=hi+1,start=words[lo]['start'],end=words[hi]['end'],reasons=sorted({r for x in batch for r in x['reasons']}),context=''.join(w['word'] for w in words[max(0,lo-3):hi+4]).strip()))
    return result


def packet(folder,section='summary',offset=0,limit=20,evidence=None):
    if offset<0 or not 1<=limit<=100:raise ValueError('Use a nonnegative offset and limit 1–100')
    def page(items):return dict(total=len(items),offset=offset,limit=limit,items=items[offset:offset+limit],more=offset+limit<len(items))
    if section=='cues':return page(e.read(folder/'publication/expected-captions.json'))
    if section=='evidence':
        if not evidence or Path(evidence).name!=evidence or not (folder/evidence).resolve().is_relative_to(folder.resolve()):raise ValueError('Select a local evidence filename within this episode')
        data=e.read(folder/evidence);items=[]
        for item in data['windows']:
            compact=dict(window=item['window'])
            if 'segments' in item:compact['segments']=[{k:s[k] for k in ('start','end','text')} for s in item['segments']]
            if 'cosine' in item:compact['cosine']=item['cosine']
            items.append(compact)
        return dict(**page(items),source_sha256=e.file_record(folder/evidence)['sha256'])
    words=e.read(folder/'words-for-review.json');flags=e.read(folder/'review-flags.json')
    if section=='flags':return page(groups(words,flags))
    comparisons=e.read(folder/'model-comparison.json')
    if section=='differences':
        # Show intervals first; inspect only the relevant bounded evidence instead
        # of dumping both complete transcripts a second time.
        return page([{k:x[k] for k in ('start','end','agreement_ratio')} for x in comparisons if x['agreement_ratio']<.97])
    if section=='gaps':
        seconds=e.read(folder/'clock.json')['audio-native.wav']['seconds'];spans=[]
        if words and words[0]['start']>=1.5:spans.append(dict(start=0,end=words[0]['start']))
        spans.extend(dict(start=a['end'],end=b['start']) for a,b in zip(words,words[1:]) if b['start']-a['end']>=1.5)
        if words and seconds-words[-1]['end']>=1.5:spans.append(dict(start=words[-1]['end'],end=seconds))
        return dict(**page(spans),note='Recognition gaps may be silence/music; inspect recording evidence before calling them omissions.')
    return dict(episode=e.read(folder/'episode.json')['number'],clock=e.read(folder/'clock.json'),recognition=e.read(folder/'ready-for-review.json'),flag_reason_counts=dict(Counter(r for f in flags for r in f['reasons'])),flag_groups=len(groups(words,flags)),comparison_windows=len(comparisons),windows_below_97_percent=sum(x['agreement_ratio']<.97 for x in comparisons),complete_text=str(folder/'review.txt'),review_schema='docs/transcript-review-schema.md',evidence_files=[x.name for x in sorted(folder.glob('*evidence.json'))],note='Read the complete proposed wording. Flags and model agreement are review aids, not measured accuracy or approval.')


def main():
    def bounded_limit(value):
        try:number=int(value)
        except ValueError:raise argparse.ArgumentTypeError('limit must be an integer from 1 to 100') from None
        if not 1<=number<=100:raise argparse.ArgumentTypeError('limit must be from 1 to 100; request the next page with --offset')
        return number
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--section',choices=['summary','flags','differences','gaps','cues','evidence'],default='summary');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=bounded_limit,default=20,help='page size, 1–100 (default: 20); continue with --offset')
    p.add_argument('--evidence',help='local evidence JSON filename for --section evidence; compact segments omit raw word metadata')
    p.add_argument('--format',choices=['json','text'],default='json',help='text is a compact complete caption display for --section cues')
    a=p.parse_args()
    if a.format=='text' and a.section!='cues':p.error('--format text requires --section cues')
    if a.section=='evidence' and not a.evidence:p.error('--section evidence requires --evidence FILE.json')
    result=packet(a.folder,a.section,a.offset,a.limit,a.evidence)
    if a.format=='text':
        print(json.dumps({k:v for k,v in result.items() if k!='items'}))
        for cue in result['items']:print(f'{cue["number"]} {cue["startTime"]:.3f}–{cue["endTime"]:.3f} <{cue["speaker"]}> {cue["text"]}')
    else:print(json.dumps(result,indent=2))
if __name__=='__main__':failures.cli(main,'transcript')
