#!/usr/bin/env python3
"""Receipt-bound chapter preparation, local boundary checks and native publication."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import wave
import xml.etree.ElementTree as ET
import episodes as e
import failures
from transcribe import transport, get
import captions

NS = 'https://podcastindex.org/namespace/1.0'
START = '<!-- podcast-chapters:start -->'
END = '<!-- podcast-chapters:end -->'
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return e.file_record(path)['sha256']


def text(path):
    # Preserve CRLF and other original Markdown bytes when deriving descriptions.
    return Path(path).read_bytes().decode('utf-8')


def source(config, show, number):
    if config.get('paused') is not False or config['show'] != show:
        raise ValueError('Chapter tasks are paused or this show is not configured')
    catalog = e.read(config['source_catalog'])
    entry = catalog['episodes'].get(number)
    if catalog['show'] != show or not entry:
        raise ValueError('Selected episode has no source clearance')
    episode, clearance = entry['episode'], entry['clearance']
    if (episode['number'] != number or clearance.get('audit_complete') is not True or
            clearance['final_audio_sha256'] != episode['final_audio_sha256']):
        raise ValueError('Clearance does not bind the selected final audio')
    if config.get('source_controls'):
        controls = e.read(config['source_controls'])
        known = controls['episodes'].get(number)
        if controls['show'] != show or (known and (known['clearance'].get('audit_complete') is not True or
                known['clearance']['final_audio_sha256'] != episode['final_audio_sha256'])):
            raise ValueError('Existing source hold or final-audio clearance differs')
    return entry


def requested_source(config, show, number):
    """Validate a shortcut without downloading media before message authentication."""
    if config.get('paused') is not False or config['show'] != show:
        raise ValueError('Chapter tasks are paused or this show is not configured')
    catalog = e.read(config['source_catalog'])
    if catalog['show'] != show:
        raise ValueError('Chapter source catalog show differs')
    if number in catalog['episodes']:
        return source(config, show, number)
    if config.get('allow_published_source_intake') is not True:
        raise ValueError('Selected episode has no source clearance')
    if not re.fullmatch(r'[1-9][0-9]*', number):
        raise ValueError('Select a published episode number')
    return None


def acquire_source(config, show, number, selected=None):
    """Bind one authorized chapter task to current published audio; never clear a hold."""
    if selected is None:
        entry = requested_source(config, show, number)
    else:
        # An operator queue selects exact feed identities, including specials
        # without iTunes episode numbers. It never changes their native metadata.
        e.slug(number)
        if config.get('paused') is not False or config['show'] != show or config.get('allow_published_source_intake') is not True:
            raise ValueError('Selected chapter intake is paused or not configured')
        catalog = e.read(config['source_catalog'])
        if catalog['show'] != show or selected['number'] != number:
            raise ValueError('Selected source show/identity differs')
        entry = source(config,show,number) if number in catalog['episodes'] else None
        if entry and any(entry['episode'][k] != selected[k] for k in ('guid','url','slug')):
            raise ValueError('Existing chapter source differs from the selected queue item')
    if entry is not None:
        return entry
    # The transcript catalog may contain holds even though chapter tasks maintain
    # their own records. A known disallowed entry is never replaced by live intake.
    if config.get('source_controls'):
        controls = e.read(config['source_controls'])
        if controls['show'] != show:
            raise ValueError('Source control show differs')
        known = controls['episodes'].get(number)
        if known and known['clearance'].get('audit_complete') is not True:
            raise ValueError('Existing source hold requires resolution by its owner')
    feed, _ = get(config['feed'])
    candidates = [item for item in ET.fromstring(feed).findall('./channel/item')
                  if (item.findtext('guid') == selected['guid'] if selected is not None else
                      item.findtext('{http://www.itunes.com/dtds/podcast-1.0.dtd}episode') == number)]
    if len(candidates) != 1:
        raise ValueError('Published episode number is missing or ambiguous')
    item = candidates[0]; link = item.findtext('link') or ''
    if selected is not None and (link != selected['url'] or item.findtext('pubDate') != selected['pubDate'] or
            dict(item.find('enclosure').attrib) != selected['enclosure'] or
            item.findtext('{http://www.itunes.com/dtds/podcast-1.0.dtd}episode') != selected['native_number']):
        raise ValueError('Queued published source identity changed')
    cp = transport(); cfg = cp.load_config(Path(config['castopod_config']))
    slug = link.rstrip('/').rsplit('/', 1)[-1]
    live = cp.inspect(cfg, show, slug)['episode']; enclosure = item.find('enclosure')
    if (not live or live['status'] != 'published' or live['guid'] != item.findtext('guid') or
            live['link'] != link or str(live['number']) != str(selected['native_number'] if selected is not None else number) or enclosure is None or
            enclosure.get('url') != live['audio_url'] or not live.get('transcript_url')):
        raise ValueError('Selected published episode/audio/transcript identity differs')
    audio, _ = get(live['audio_url']); digest = hashlib.sha256(audio).hexdigest()
    if config.get('source_controls'):
        known = e.read(config['source_controls'])['episodes'].get(number)
        if known and (known['clearance'].get('audit_complete') is not True or known['clearance']['final_audio_sha256'] != digest):
            raise ValueError('Published audio differs from the existing source clearance')
    entry = dict(episode=dict(number=number,guid=live['guid'],slug=slug,title=live['title'],url=link,
                              pubDate=item.findtext('pubDate'),enclosure=dict(enclosure.attrib),final_audio_sha256=digest),
                 clearance=dict(audit_complete=True,status='published_audio_identity_verified',final_audio_sha256=digest,
                    provenance='Chapter-only intake of the selected current published recording; no ad audit, audio edit or transcription authorization.'))
    if selected is not None:
        if slug != selected['slug']:
            raise ValueError('Queued episode slug changed')
        entry['episode']['native_number'] = live['number']
        if live['number'] is None:
            entry['episode']['display_name'] = live['title']
    path = Path(config['source_catalog'])
    with path.with_suffix('.lock').open('a') as lock:
        os.chmod(lock.name,0o600); fcntl.flock(lock,fcntl.LOCK_EX)
        if e.read(config['config_path']).get('paused') is not False:
            raise ValueError('Chapter tasks were paused during intake')
        catalog = e.read(path)
        if number in catalog['episodes']:
            return source(config,show,number)
        catalog['episodes'][number] = entry; e.save(path,catalog)
    return entry


def scope(config, folder):
    task = e.read(folder.parent/'chapters-task.json')
    current = source(config, task['show'], task['episode'])
    saved = e.read(task['authorization']['request_path'])
    if (str(folder) != task['directory'] or config['feed'] != task['feed'] or
            current != task['source'] or e.digest(saved['incoming']) != task['authorization']['incoming_sha256']):
        raise ValueError('Chapter task source, authorization or destination changed')
    return task, current['episode']


@contextmanager
def locked(folder, timeout=60):
    folder = e.private_root(folder)
    with (folder/'.chapters.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        deadline = time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Another chapter operation still holds the episode lock; inspect its saved state') from None
                time.sleep(min(.1,max(0,deadline-time.monotonic())))
        yield


def validate(value, duration):
    if not isinstance(value, dict) or value.get('version') != '1.2.0':
        raise ValueError('Use Podcasting 2.0 JSON Chapters version 1.2.0')
    rows = value.get('chapters')
    if not isinstance(rows, list) or not (3 if duration >= 600 else 1) <= len(rows) <= 10:
        raise ValueError('Use 3–10 chapters for full episodes; short recordings may have fewer')
    previous = -1
    for row in rows:
        start, title = row.get('startTime'), row.get('title')
        if (type(start) not in (int, float) or not math.isfinite(start) or
                not previous < start < duration or start < 0):
            raise ValueError('Chapter starts must increase within the final audio')
        if previous >= 0 and start-previous < 30:
            raise ValueError('Keep chapter starts at least 30 seconds apart for description compatibility')
        if (not isinstance(title, str) or not title.strip() or len(title) > 100 or
                re.search(r'[<>\r\n\x00-\x1f]', title) or row.get('toc', True) is not True):
            raise ValueError('Use visible chapters with short plain-text titles')
        previous = start
    if rows[0]['startTime'] != 0:
        raise ValueError('The first chapter must start at zero')
    return rows


def timestamp(seconds):
    seconds = int(seconds)
    return f'{seconds//3600:02d}:{seconds%3600//60:02d}:{seconds%60:02d}'


def rendered_text(value):
    """Compare displayed prose despite the Markdown renderer's smart quotes."""
    return ' '.join(value.translate(str.maketrans('‘’“”', "''\"\"")).split())


def chapters_before_footer(notes, anchor=None):
    """Move the generated list ahead of a labeled or explicitly selected footer."""
    section = re.search(r'(?m)^## Chapters\r?\n\r?\n(?:[0-9]{2}:[0-9]{2}:[0-9]{2} [^\r\n]+(?:\r?\n|$))+', notes)
    footer = re.search(
        r'(?im)^(?:#{1,6}[ \t]+)?(?:This episode[’\x27]s sponsors?:|(?:Episode )?Sponsors?:|'
        r'(?:Aaron|Sjors)[’\x27]s? (?:Nostr|Twitter|email):|Contact(?: info(?:rmation)?)?:)', notes)
    if not footer:
        footer = re.search(r'(?i)(?<=\s)Episode Sponsors?:', notes)
    if anchor is not None:
        if not isinstance(anchor,str) or len(anchor.strip())<8 or notes.count(anchor)!=1:
            raise ValueError('Footer anchor must select an exact, unique original footer beginning')
        start=notes.index(anchor)
        if section and section.start()<=start<section.end():
            raise ValueError('Footer anchor cannot select the chapter list')
    else:
        start=footer.start() if footer else None
    if not section or start is None or start > section.start():
        return notes
    # Keep the existing footer separator with the sponsor/contact text.
    separator = re.search(r'(?m)^[ \t]*(?:={3,}|-{3,}|\*{3,})[ \t]*\r?\n(?:[ \t]*\r?\n)*$', notes[:start])
    if separator:
        start = separator.start()
    before = notes[:start]
    footer_text = notes[start:section.start()].rstrip('\r\n')
    return (before + ('' if before.endswith('\n\n') or before.endswith('\r\n\r\n') or not before else '\n\n') +
            section.group().rstrip('\r\n') + '\n\n' + footer_text + notes[section.end():])


def description(original, rows, legacy=None, footer=None):
    """Replace the chapter section or append it, preserving all other Markdown."""
    # Castopod escapes HTML comments in Markdown: internal delimiters would be
    # visible to listeners. Recognize the old markers only to migrate them away.
    block = '## Chapters\n\n'+'  \n'.join(
        timestamp(row['startTime'])+' '+row['title'] for row in rows)
    if START in original or END in original:
        if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END) or legacy:
            raise ValueError('Chapter block markers need inspection')
        a, b = original.index(START), original.index(END)+len(END)
        return chapters_before_footer(original[:a]+block+original[b:],footer)
    sections = list(re.finditer(r'(?m)^## Chapters\r?\n\r?\n(?:[0-9]{2}:[0-9]{2}:[0-9]{2} [^\r\n]+(?:\r?\n|$))+', original))
    if sections:
        if len(sections) != 1 or legacy:
            raise ValueError('Chapter sections need inspection')
        section=sections[0]
        return chapters_before_footer(original[:section.start()]+block+'\n'+original[section.end():],footer)
    if legacy:
        # Only an exact, uniquely selected old timestamp list may be removed.
        lines = [line.strip() for line in legacy.splitlines() if line.strip()]
        timing = r'^(?:[-*]\s+)?\(?\d{1,3}:\d{2}(?::\d{2})?\)?\s*[-–—:]?\s+.*$'
        if (original.count(legacy) != 1 or len(lines) < 4 or
                not re.fullmatch(r'[#\s]*(?:Timestamps|Chapters):?', lines[0], re.I) or
                any(not re.fullmatch(timing, line) or re.search(r'https?://', line) for line in lines[1:])):
            raise ValueError('Legacy removal must select only the exact old timestamp heading/list')
        original = original.replace(legacy, '', 1)
    elif re.search(r'(?im)^\s*[#\s]*(?:Timestamps|Chapters):?\s*$', original):
        raise ValueError('Review and identify the old timestamp block before replacing it')
    return chapters_before_footer(original+('' if original.endswith('\n\n') else '\n\n')+block+'\n',footer)


def reviewed_clock(folder, episode, metadata_duration, frames, sample_rate):
    """Require an inspected, exact-source verdict for an estimated duration mismatch."""
    seconds=frames/sample_rate;path=folder/'clock-review.json'
    if abs(seconds-float(metadata_duration))<=2 and not path.exists():
        return None
    if not path.exists():
        raise ValueError('Published metadata and decoded audio clocks differ; inspect before review')
    review=e.read(path)
    expected=dict(episode_guid=episode['guid'],source_audio_sha256=episode['final_audio_sha256'],
        metadata_duration=float(metadata_duration),decoded_frames=frames,sample_rate=sample_rate)
    if (review.get('verdict')!='use-decoded-clock' or any(review.get(k)!=v for k,v in expected.items()) or
            not isinstance(review.get('reason'),str) or not review['reason'].strip()):
        raise ValueError('Inspected clock review does not bind this exact source and decoded clock')
    return path


def prepare(config, folder):
    task, episode = scope(config, folder)
    if (folder/'prepared.json').exists():
        prepared = e.read(folder/'prepared.json')
        check_inputs(folder, prepared)
        return prepared
    if any((folder/name).exists() for name in ('episode-before.json', 'published.mp3', 'feed-before.xml')):
        raise ValueError('Partial preparation is unresolved; inspect before retrying')
    cp = transport(); cfg = cp.load_config(Path(config['castopod_config']))
    before = cp.inspect(cfg, task['show'], episode['slug']); live = before['episode']
    if (not {'chapters', 'conditional-update'} <= set(before.get('features', [])) or not live or
            live['status'] != 'published' or live['guid'] != episode['guid'] or
            str(live['number']) != str(episode.get('native_number',episode['number'])) or live['link'] != episode['url']):
        raise ValueError('Matching helpers and the selected published episode are required')
    feed, _ = get(config['feed']); item = captions.target(feed, episode['guid'])
    if (item.findtext('link') != episode['url'] or item.findtext('pubDate') != episode['pubDate'] or
            item.find('enclosure').get('url') != live['audio_url']):
        raise ValueError('Canonical feed identity differs from the selected episode')
    if not live.get('transcript_url'):
        raise ValueError('Publish/review this episode’s native transcript before generating chapters')
    tags = item.findall('{'+NS+'}transcript')
    if not any(tag.get('url') == live['transcript_url'] and tag.get('type') == 'text/vtt' for tag in tags):
        raise ValueError('Selected native VTT is not advertised in the canonical feed')
    audio, _ = get(live['audio_url'])
    if hashlib.sha256(audio).hexdigest() != episode['final_audio_sha256']:
        raise ValueError('Served audio differs from the cleared final recording')
    transcript, _ = get(live['transcript_url'])
    old_chapters = get(live['chapters_url'])[0] if live.get('chapters_url') else None
    if not transcript.decode('utf-8-sig').startswith('WEBVTT'):
        raise ValueError('Require the existing native WebVTT transcript')
    e.save(folder/'episode.json', episode); e.save(folder/'episode-before.json', before)
    (folder/'feed-before.xml').write_bytes(feed)
    (folder/'published.mp3').write_bytes(audio); (folder/'transcript.vtt').write_bytes(transcript)
    (folder/'notes-original.md').write_text(live['description_markdown'])
    if old_chapters is not None: (folder/'chapters-original.json').write_bytes(old_chapters)
    for source_path, destination, options in [
            (folder/'published.mp3', folder/'audio-native.wav', []),
            (folder/'audio-native.wav', folder/'audio-16k.wav', ['-ac', '1', '-ar', '16000'])]:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(source_path),
                        '-map', '0:a:0', *options, '-c:a', 'pcm_s16le', str(destination)],
                       check=True, capture_output=True, timeout=180)
    with wave.open(str(folder/'audio-native.wav')) as wav:
        frames,sample_rate=wav.getnframes(),wav.getframerate()
    seconds=frames/sample_rate
    clock_review=reviewed_clock(folder,episode,live['duration'],frames,sample_rate)
    prepared = dict(episode_guid=episode['guid'],duration=seconds,
                    target={key: cfg.get(key) for key in ('transport','ssh','app','user','cli')},
                    inputs={name: sha(folder/name) for name in ('published.mp3','transcript.vtt','notes-original.md',
                        'feed-before.xml','episode-before.json','audio-native.wav','audio-16k.wav','episode.json')})
    if old_chapters is not None: prepared['inputs']['chapters-original.json'] = sha(folder/'chapters-original.json')
    if clock_review is not None:prepared['inputs']['clock-review.json']=sha(clock_review)
    e.save(folder/'prepared.json', prepared)
    return prepared


def check_inputs(folder, prepared):
    if any(sha(folder/name) != digest for name, digest in prepared['inputs'].items()):
        raise ValueError('Preserved chapter source artifacts changed')


def render(config, folder, check_only=False):
    scope(config, folder); prepared = e.read(folder/'prepared.json'); check_inputs(folder, prepared)
    rows = validate(e.read(folder/'chapters.json'), prepared['duration'])
    legacy_path = folder/'legacy-timestamps.json'
    legacy = e.read(legacy_path)['remove'] if legacy_path.exists() else None
    footer_path = folder/'footer.json'
    footer = e.read(footer_path)['start'] if footer_path.exists() else None
    if footer is not None and text(folder/'notes-original.md').count(footer)!=1:
        raise ValueError('Footer anchor differs from the preserved original notes')
    notes = description(text(folder/'notes-original.md'), rows, legacy, footer)
    expected_state = e.read(folder/'episode-before.json')['episode']
    if check_only:
        if text(folder/'notes.md') != notes or e.read(folder/'expected-state.json') != expected_state:
            raise ValueError('Chapter exports changed after rendering')
    else:
        (folder/'notes.md').write_text(notes)
        e.save(folder/'expected-state.json', expected_state)
    value = dict(chapters_sha256=sha(folder/'chapters.json'), notes_sha256=sha(folder/'notes.md'),
                 expected_state_sha256=sha(folder/'expected-state.json'),
                 legacy_sha256=sha(legacy_path) if legacy_path.exists() else None, count=len(rows))
    if footer_path.exists():value['footer_sha256']=sha(footer_path)
    if not check_only: e.save(folder/'render.json', value)
    return value


def check(config, folder, run=True):
    """One bounded local ASR pass for every proposed boundary; never retry an unknown worker."""
    _, episode = scope(config, folder)
    prepared = e.read(folder/'prepared.json'); check_inputs(folder, prepared)
    rows = validate(e.read(folder/'chapters.json'), prepared['duration'])
    windows = [dict(start=max(0,row['startTime']-12),end=min(prepared['duration'],row['startTime']+25),
                    reason=row['title']) for row in rows]
    binding = dict(chapters_sha256=sha(folder/'chapters.json'), source_audio_sha256=episode['final_audio_sha256'],
                   transcript_sha256=sha(folder/'transcript.vtt'), windows=windows)
    directory = e.private_root(folder/'checks'/e.digest(binding)); state = directory/'check.json'
    if state.exists():
        saved = e.read(state)
        if saved['binding'] != binding or saved['phase'] != 'completed' or saved['evidence_sha256'] != sha(directory/'evidence.json'):
            raise ValueError('Earlier boundary check is unresolved or changed; inspect before retrying')
        return saved
    if not run:
        raise ValueError('Run and review boundary checks before publication')
    e.save(directory/'windows.json', windows)
    e.save(state, dict(phase='running', binding=binding))
    runtime = e.read(config['review_config'])
    try:
        subprocess.run(['nice', '-n', '10', runtime['python'], str(ROOT/'tools/transcription_review.py'),
                        '--config', config['review_config'], '--folder', str(folder), '--out', str(directory/'evidence.json'),
                        'recognize', '--model', 'secondary', '--windows', str(directory/'windows.json')],
                       check=True, capture_output=True, timeout=480)
        evidence = e.read(directory/'evidence.json')
        if (evidence['episode_guid'] != episode['guid'] or evidence['source_audio_sha256'] != episode['final_audio_sha256'] or
                [part['window'] for part in evidence['windows']] != windows or
                any(not part['segments'] for part in evidence['windows'])):
            raise ValueError('Boundary recognition evidence does not cover the selected audio/windows')
        result = dict(phase='completed',binding=binding,evidence_sha256=sha(directory/'evidence.json'),
                      evidence=str(directory/'evidence.json'))
        e.save(state,result); return result
    except BaseException:
        e.save(state,dict(phase='failed',binding=binding)); raise


def reviewed(config, folder):
    task, episode = scope(config, folder)
    prepared = e.read(folder/'prepared.json'); check_inputs(folder, prepared)
    rows = validate(e.read(folder/'chapters.json'), prepared['duration'])
    old_render = e.read(folder/'render.json')
    if render(config, folder, check_only=True) != old_render:
        raise ValueError('Chapter exports changed after rendering; review again')
    review = e.read(folder/'review.json'); evidence = check(config, folder, run=False)
    expected = dict(chapters_sha256=sha(folder/'chapters.json'),source_audio_sha256=episode['final_audio_sha256'],
                    transcript_sha256=sha(folder/'transcript.vtt'),evidence_sha256=evidence['evidence_sha256'])
    if (review.get('publication_ready') is not True or review.get('reviewed_full_transcript') is not True or
            any(review.get(key) != value for key,value in expected.items()) or
            len(review.get('boundaries', [])) != len(rows) or any(
                decision.get('startTime') != row['startTime'] or not isinstance(decision.get('reason'),str) or not decision['reason'].strip()
                for decision,row in zip(review.get('boundaries', []),rows))):
        raise ValueError('Agent editorial review of the exact chapters and audio boundaries is required')
    return task, episode, prepared, rows


def publish(config, folder, apply=False):
    task, episode, prepared, rows = reviewed(config, folder)
    cp = transport(); cfg = cp.load_config(Path(config['castopod_config']))
    if {key:cfg.get(key) for key in prepared['target']} != prepared['target']:
        raise ValueError('Publishing destination changed')
    receipt = folder/'transport.json'
    if receipt.exists():
        # Never invoke an uncertain mutation again; verify is explicitly read-only.
        if e.read(receipt)['phase'] != 'verified':
            raise ValueError('Prior publication is unresolved; inspect before retrying, using verify')
        return verify(config,folder)
    before = e.read(folder/'episode-before.json')['episode']
    if cp.inspect(cfg,task['show'],episode['slug'])['episode'] != before:
        raise ValueError('Episode changed since preparation; inspect before retrying')
    audio,_ = get(before['audio_url'])
    transcript,_ = get(before['transcript_url'])
    if hashlib.sha256(audio).hexdigest() != episode['final_audio_sha256'] or hashlib.sha256(transcript).hexdigest() != sha(folder/'transcript.vtt'):
        raise ValueError('Published audio/transcript changed; review against the current source')
    if not apply:
        return dict(apply=False,count=len(rows),reviewed=True)
    cp.run_episode(cfg,task['show'],'update',episode['slug'],chapters=folder/'chapters.json',
                   notes=folder/'notes.md',expected_state=folder/'expected-state.json',apply=True,receipt=receipt)
    return verify(config,folder)


def verify(config, folder):
    task, episode, prepared, rows = reviewed(config,folder)
    cp = transport(); cfg = cp.load_config(Path(config['castopod_config']))
    if {key:cfg.get(key) for key in prepared['target']} != prepared['target']:
        raise ValueError('Publishing destination changed')
    old = e.read(folder/'episode-before.json')['episode']; after = cp.inspect(cfg,task['show'],episode['slug'])['episode']
    for key,value in old.items():
        if not key.startswith(('chapters_','description_')) and after.get(key) != value:
            raise ValueError('Unrelated episode field changed: '+key)
    if after['description_sha256'] != sha(folder/'notes.md') or after['description_markdown'] != text(folder/'notes.md'):
        raise ValueError('Hosted description differs from the canonical chapter export')
    public,headers = get(after['chapters_url'])
    mime = next((v.split(';')[0] for k,v in headers.items() if k.lower()=='content-type'),'')
    if public != (folder/'chapters.json').read_bytes() or mime not in ('application/json','application/json+chapters'):
        raise ValueError('Public canonical chapter JSON/MIME differs')
    feed,_ = get(config['feed']); before_item = captions.target((folder/'feed-before.xml').read_bytes(),episode['guid'])
    after_item = captions.target(feed,episode['guid'])
    tags = after_item.findall('{'+NS+'}chapters')
    if len(tags) != 1 or tags[0].get('url') != after['chapters_url'] or tags[0].get('type') != 'application/json+chapters':
        raise ValueError('RSS chapter attachment missing or incorrect')
    visible = rendered_text(html.unescape(re.sub('<[^>]+>',' ',after_item.findtext('description') or '')))
    if any(rendered_text(timestamp(row['startTime'])+' '+row['title']) not in visible for row in rows):
        raise ValueError('RSS description omits a derived chapter')
    removable = {'description','{http://purl.org/rss/1.0/modules/content/}encoded',
                 '{http://www.itunes.com/dtds/podcast-1.0.dtd}summary','{'+NS+'}chapters'}
    for item in (before_item,after_item):
        for child in list(item):
            if child.tag in removable: item.remove(child)
    if ET.tostring(before_item) != ET.tostring(after_item):
        raise ValueError('Unrelated RSS episode fields changed')
    audio,_ = get(after['audio_url']); transcript,_ = get(after['transcript_url']); page,_ = get(after['link'],accept='text/html')
    if START.encode() in page or END.encode() in page or html.escape(START).encode() in page or html.escape(END).encode() in page:
        raise ValueError('Internal chapter markers are visible in the public episode page')
    if hashlib.sha256(audio).hexdigest() != episode['final_audio_sha256'] or hashlib.sha256(transcript).hexdigest() != sha(folder/'transcript.vtt'):
        raise ValueError('Original published audio/transcript changed')
    result = dict(verified=True,episode_guid=episode['guid'],number=episode['number'],count=len(rows),
                  link=episode['url'],chapters_sha256=sha(folder/'chapters.json'),notes_sha256=sha(folder/'notes.md'),
                  review_sha256=sha(folder/'review.json'),verified_at=e.now())
    e.save(folder/'verification.json',result); return result


def completion(folder):
    folder = Path(folder); receipt = folder/'verification.json'
    if not receipt.exists(): return None
    result = e.read(receipt); episode = e.read(folder/'episode.json')
    if (result.get('verified') is not True or result['episode_guid'] != episode['guid'] or
            result['number'] != episode['number'] or result['link'] != episode['url'] or
            result['chapters_sha256'] != sha(folder/'chapters.json') or result['notes_sha256'] != sha(folder/'notes.md') or
            result['review_sha256'] != sha(folder/'review.json') or
            result['count'] != len(e.read(folder/'chapters.json')['chapters'])):
        raise ValueError('Chapter completion receipt differs from the selected artifacts')
    noun = 'chapter' if result['count'] == 1 else 'chapters'
    label = episode.get('display_name') or 'episode '+result['number']
    return f"Added {result['count']} {noun} to {label}: {result['link']}"


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True); parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('action',choices=('prepare','render','check','publish','verify'))
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args(); config = e.read(args.config); folder = args.folder.absolute()
    with locked(folder):
        result = publish(config,folder,args.apply) if args.action=='publish' else globals()[args.action](config,folder)
    print(json.dumps(result,indent=2))


if __name__=='__main__': failures.cli(main,'chapters')
