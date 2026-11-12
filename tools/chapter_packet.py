#!/usr/bin/env python3
"""Read-only, source-bound compact chapter review views; never approves or publishes."""
import argparse
import math
import os
from pathlib import Path

import chapters as c
import episodes as e
import transcript


def clock(value):
    milliseconds = round(value * 1000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}'


def paragraphs(raw, duration, max_seconds=45):
    """Merge adjacent cues into readable paragraphs without deleting spoken text.

    Even exact repeats are retained: overlapping clocks cannot prove that a
    repeated word was not actually spoken. Cue ranges preserve ordered provenance.
    """
    cues = transcript.parse(raw, default_speaker='Unlabelled')
    result, overlaps, backsteps = [], [], []
    previous = None
    for index, cue in enumerate(cues, 1):
        start, end = cue['start'], cue['end']
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration + 2):
            raise ValueError('Transcript cue is outside the prepared source clock')
        if previous and start < previous['start']:
            if end <= previous['start']:
                raise ValueError('Transcript cues are not ordered; inspect the original')
            backsteps.append(dict(cue=index,previous_cue=index-1,
                start=start,previous_start=previous['start']))
        words = cue['text'].split()
        if not words:
            raise ValueError('Empty transcript cue; inspect rather than omit it')
        if previous and start < previous['end']:
            overlaps.append(dict(cue=index, previous_cue=index-1))
        text = ' '.join(words)
        if (result and result[-1]['speaker'] == cue['speaker'] and
                max(end,result[-1]['end']) - min(start,result[-1]['start']) <= max_seconds and
                start <= result[-1]['end'] + 2):
            row = result[-1]
            row['start'] = min(row['start'],start)
            row['end'] = max(row['end'], end)
            row['last_cue'] = index
            if text:
                row['text'] += ' ' + text
        else:
            result.append(dict(start=start, end=end, speaker=cue['speaker'], text=text,
                               first_cue=index, last_cue=index))
        previous = cue
    return dict(paragraphs=result, cues=len(cues), overlaps=overlaps, backsteps=backsteps)


def source_packet(config, folder):
    task, episode = c.scope(config, folder)
    prepared = e.read(folder/'prepared.json')
    c.check_inputs(folder, prepared)
    if prepared['episode_guid'] != episode['guid']:
        raise ValueError('Prepared episode identity differs')
    digest = c.sha(folder/'transcript.vtt')
    compact = paragraphs((folder/'transcript.vtt').read_bytes().decode('utf-8-sig'), prepared['duration'])
    return dict(episode_guid=episode['guid'], episode=task['episode'],
                source_audio_sha256=episode['final_audio_sha256'], transcript_sha256=digest,
                prepared_sha256=c.sha(folder/'prepared.json'), **compact)


def boundary_packet(config, folder):
    """Reuse only completed, current evidence through the existing mandatory guard."""
    saved = c.check(config, folder, run=False)
    evidence = e.read(saved['evidence'])
    if c.sha(saved['evidence']) != saved['evidence_sha256']:
        raise ValueError('Boundary evidence changed while reading')
    windows = []
    for item in evidence['windows']:
        segments = []
        for segment in item['segments']:
            start, end, text = segment['start'], segment['end'], segment['text']
            if (type(start) not in (int, float) or type(end) not in (int, float) or
                    not math.isfinite(start) or not math.isfinite(end) or start >= end or
                    not isinstance(text, str) or not text.strip()):
                raise ValueError('Invalid boundary segment; inspect original evidence')
            segments.append(dict(start=start, end=end, text=' '.join(text.split())))
        windows.append(dict(window=item['window'], segments=segments))
    return dict(**saved['binding'], evidence_sha256=saved['evidence_sha256'], evidence=windows)


def transcript_view(packet, start=1, count=None):
    rows = packet['paragraphs']
    if start < 1 or start > len(rows) or (count is not None and count < 1):
        raise ValueError('Paragraph page is outside the full transcript')
    stop = min(len(rows), start-1+count) if count else len(rows)
    lines = [f"Episode {packet['episode']} | GUID {packet['episode_guid']}",
             f"Audio SHA256 {packet['source_audio_sha256']}",
             f"Transcript SHA256 {packet['transcript_sha256']}",
             f"Prepared SHA256 {packet['prepared_sha256']}",
             f"Paragraphs {start}-{stop}/{len(rows)} | source cues {packet['cues']} | "
             f"overlapping cue pairs (all text retained) {len(packet['overlaps'])} | "
             f"overlapping backward starts {len(packet.get('backsteps',[]))}",
             'Full transcript review is required; this view does not record approval.', '']
    for index, row in enumerate(rows[start-1:stop], start):
        lines.extend([f"P{index} [{clock(row['start'])}–{clock(row['end'])}; cues {row['first_cue']}-{row['last_cue']}] {row['speaker']}: {row['text']}", ''])
    lines.append(f'NEXT paragraph {stop+1}' if stop < len(rows) else 'END OF COMPLETE TRANSCRIPT')
    if packet['overlaps']:
        lines.append('Overlapping source cue provenance (all words retained; cue <- preceding cue):')
        lines.extend(f"{row['cue']} <- {row['previous_cue']}" for row in packet['overlaps'])
    if packet.get('backsteps'):
        lines.append('Overlapping backward starts retained in original cue/text order (no transcript correction):')
        lines.extend(f"Cue {row['cue']} at {clock(row['start'])} follows cue {row['previous_cue']} "
                     f"at {clock(row['previous_start'])}" for row in packet['backsteps'])
    return '\n'.join(lines)+'\n'


def boundary_view(packet):
    lines = [f"Chapters SHA256 {packet['chapters_sha256']}",
             f"Audio SHA256 {packet['source_audio_sha256']}",
             f"Transcript SHA256 {packet['transcript_sha256']}",
             f"Evidence SHA256 {packet['evidence_sha256']}", '']
    for item in packet['evidence']:
        window = item['window']
        lines.append(f"[{clock(window['start'])}–{clock(window['end'])}] {window['reason']}")
        lines.extend(f"{clock(row['start'])}–{clock(row['end'])} {row['text']}" for row in item['segments'])
        lines.append('')
    return '\n'.join(lines)+'\n'


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='Export to a new private UTF-8 file instead of stdout')
    commands = parser.add_subparsers(dest='command', required=True)
    view = commands.add_parser('transcript')
    view.add_argument('--start', type=int, default=1, help='First paragraph (one based)')
    view.add_argument('--count', type=int, help='Paragraphs per page; default exports the complete transcript')
    commands.add_parser('boundaries')
    args = parser.parse_args()
    config = e.read(args.config)
    with c.locked(args.folder):
        if args.command == 'transcript':
            output = transcript_view(source_packet(config, args.folder), args.start, args.count)
        else:
            output = boundary_view(boundary_packet(config, args.folder))
        if args.out:
            # Exclusive creation prevents replacing any original/source/review artifact.
            with args.out.open('x', encoding='utf-8') as handle:
                handle.write(output)
            print(str(args.out))
        else:
            print(output, end='')


if __name__ == '__main__':
    main()
