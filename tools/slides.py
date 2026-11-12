#!/usr/bin/env python3
"""Build or verify an offline, versioned slide-review directory. No network I/O."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def interval(item, duration):
    a, b = item['start'], item['end']
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in (a, b)):
        raise ValueError('Times must be finite numbers')
    if not 0 <= a < b <= duration:
        raise ValueError('Interval is outside the source audio timeline')
    return a, b


def validate(transcript, plan):
    duration = transcript['duration']
    if type(duration) not in (float, int) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid duration')
    if not transcript['cues'] or not plan['slides']:
        raise ValueError('Full transcript and slide plan are required')
    previous = -1
    for cue in transcript['cues']:
        a, _ = interval(cue, duration)
        if a < previous or not isinstance(cue['text'], str) or not cue['text'].strip():
            raise ValueError('Cues must be ordered and have text; overlap is allowed')
        previous = a
    previous_end = 0
    for slide in plan['slides']:
        a, b = interval(slide, duration)
        if a < previous_end or slide['kind'] not in ('topic', 'source'):
            raise ValueError('Slides must be ordered, non-overlapping topic/source cards')
        if not isinstance(slide['title'], str) or not slide['title'].strip():
            raise ValueError('Slide title required')
        previous_end = b
        if slide['kind'] == 'source':
            source = slide['source']
            url = urlsplit(source['url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Source URL must be HTTPS without credentials')
            if not all(isinstance(source[k], str) and source[k].strip() for k in ('title', 'excerpt')):
                raise ValueError('Source title and exact excerpt required')


def build(args):
    raw_transcript = args.transcript.read_bytes()
    raw_plan = args.plan.read_bytes()
    transcript, plan = json.loads(raw_transcript), json.loads(raw_plan)
    validate(transcript, plan)
    esc = lambda s: html.escape(str(s), quote=True)
    cards = []
    for slide in plan['slides']:
        context = ' '.join(c['text'] for c in transcript['cues']
                           if c['end'] > slide['start'] and c['start'] < slide['end'])
        source = slide.get('source') if slide['kind'] == 'source' else None
        excerpt = (f"<blockquote>{esc(source['excerpt'])}</blockquote>"
                   f"<p>{esc(source['title'])} — {esc(source['url'])}</p>"
                   '<p>Source verification pending</p>') if source else ''
        cards.append(f"<article><p>{slide['start']}–{slide['end']} s · {esc(slide['kind'])}</p>"
                     f"<h2>{esc(slide['title'])}</h2>{excerpt}<details open>"
                     f"<summary>Transcript context</summary><p>{esc(context)}</p></details></article>")
    page = ('<!doctype html><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>Slide review</title><style>body{font:20px sans-serif;max-width:1000px;margin:40px auto;'
            'padding:20px;background:#f4f3ef;color:#192a36}article{background:white;padding:32px;'
            'margin:24px 0;border:1px solid #bbb}p{overflow-wrap:anywhere}h2{font-size:36px}</style>'
            f"<h1>{esc(transcript.get('title', 'Slide review'))}</h1>"
            '<p>Editorial draft · no approval or publishing authority recorded</p>' + ''.join(cards))
    files = {'transcript.json': raw_transcript, 'slides.json': raw_plan, 'index.html': page.encode()}
    if args.feedback:
        files['feedback.txt'] = args.feedback.read_bytes()
    files['tool.py'] = Path(__file__).read_bytes()
    manifest = {'schema': 1, 'stage': 'slides', 'status': 'needs_review',
                'files': {name: sha(data) for name, data in files.items()}}
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    # Reserve destination first; concurrent writers and existing revisions fail.
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix='.slide-build-', dir=args.out.parent) as tmp:
            for name, data in files.items():
                (Path(tmp) / name).write_bytes(data)
            for name in files:
                shutil.move(str(Path(tmp) / name), args.out / name)
    except BaseException:
        # Preserve partial work for inspection; do not report it as complete.
        raise
    print(args.out / 'index.html')


def verify(directory):
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    if manifest['schema'] != 1 or manifest['stage'] != 'slides':
        raise ValueError('Unknown bundle schema')
    required = {'transcript.json', 'slides.json', 'index.html', 'tool.py'}
    names = set(manifest['files'])
    if not required <= names or names - required - {'feedback.txt'}:
        raise ValueError('Unexpected or missing bundle files')
    for name, expected in manifest['files'].items():
        path = directory / name
        if path.is_symlink() or sha(path.read_bytes()) != expected:
            raise ValueError(f'Artifact changed: {name}')
    validate(json.loads((directory / 'transcript.json').read_bytes()),
             json.loads((directory / 'slides.json').read_bytes()))
    print('Bundle hashes and timeline valid; editorial approval remains separate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build')
    for name in ('transcript', 'plan', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--feedback', type=Path)
    p = sub.add_parser('verify')
    p.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        build(args) if args.command == 'build' else verify(args.directory)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
