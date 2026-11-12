"""Reviewed word/cue rendering and complete public-caption comparison, ported from the working backfill."""
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from episodes import save
def digest(data):return hashlib.sha256(data).hexdigest()

def timestamp(seconds):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{ms:03}'

def render(folder,preview=False):
    review = json.loads((folder / 'review.json').read_text())
    assert preview or review['publication_ready'] is True
    source_hash = digest((folder / 'primary-segments.jsonl').read_bytes())
    assert review['primary_segments_sha256'] == source_hash, 'Review belongs to different ASR'
    words = json.loads((folder / 'words-for-review.json').read_text())
    duration = json.loads((folder / 'primary-info.json').read_text())['duration']
    for correction in review.get('word_corrections', []):
        word = words[correction['word_index']]
        assert word['word'] == correction['before']
        word['word'] = correction['after']
    names = review['speaker_mapping']
    for word in words:
        key = str(word['cluster'])
        assert key in names and names[key], f'Unresolved cluster {key}'
        word['speaker'] = names[key]
        assert '<' not in word['speaker'] and '>' not in word['speaker']
        assert math.isfinite(word['start']) and math.isfinite(word['end'])
        assert 0 <= word['start'] <= word['end'] <= duration + .1
    assert all(a['start'] <= b['start'] for a, b in zip(words, words[1:])), 'Unordered ASR words'
    for correction in review.get('speaker_corrections', []):
        start, end = correction['start_word_index'], correction['end_word_index']
        assert 0 <= start < end <= len(words)
        assert correction['speaker'] in names.values()
        for word in words[start:end]:
            word['speaker'] = correction['speaker']
    for correction in review.get('timing_corrections', []):
        word = words[correction['word_index']]
        assert [word['start'], word['end']] == correction['before']
        word['start'], word['end'] = correction['after']
    replacements = sorted(review.get('replacement_spans', []), key=lambda x: x['start_word_index'])
    assert all(a['end_word_index'] <= b['start_word_index'] for a, b in zip(replacements, replacements[1:])), 'Overlapping reviewed replacements'
    for replacement in reversed(replacements):
        start, end = replacement['start_word_index'], replacement['end_word_index']
        assert 0 <= start < end <= len(words)
        assert digest(''.join(w['word'] for w in words[start:end]).encode()) == replacement['replaced_text_sha256']
        words[start:end] = replacement['words']
    for insertion in sorted(review.get('word_insertions', []), key=lambda word: word['start']):
        position = next((i for i, word in enumerate(words) if word['start'] > insertion['start']), len(words))
        words.insert(position, insertion)
    words = [word for word in words if word['word']]
    # Keep each utterance together when its corrected times overlap an interruption.
    # Sorting all words by time would interleave the two speakers word by word.
    for word in words:
        assert word['speaker'] in names.values()
        assert math.isfinite(word['start']) and math.isfinite(word['end'])
        assert 0 <= word['start'] <= word['end'] <= duration + .1
    cues, current = [], []
    for word in words:
        if current and (word['speaker'] != current[-1]['speaker']
                        or word['start'] - current[-1]['end'] > 1.2
                        or word['end'] - current[0]['start'] > 6
                        or len(''.join(w['word'] for w in current)) + len(word['word']) > 82):
            cues.append(current)
            current = []
        current.append(word)
    if current:
        cues.append(current)
    # Avoid leaving a single short continuation word as its own caption when the
    # preceding caption has room. Genuine replies by another speaker stay separate.
    combined = []
    for cue in cues:
        if (combined and cue[-1]['end'] - cue[0]['start'] < .4
                and combined[-1][-1]['speaker'] == cue[0]['speaker']
                and cue[0]['start'] - combined[-1][-1]['end'] < .5
                and cue[-1]['end'] - combined[-1][0]['start'] <= 7
                and len(''.join(w['word'] for w in combined[-1] + cue)) <= 110):
            combined[-1].extend(cue)
        else:
            combined.append(cue)
    cues = combined
    expected = []
    lines = ['WEBVTT - Automatic transcript; recognition may contain errors. Reviewed for technical wording and speaker labels. Times match the published episode.', '']
    for number, cue in enumerate(cues):
        start = round(cue[0]['start'], 3)
        end = min(round(duration, 3), max(round(cue[-1]['end'], 3), start + .05))
        assert end > start
        text = ''.join(w['word'] for w in cue).strip()
        assert text and '\n' not in text and '<' not in text and '>' not in text
        speaker = cue[0]['speaker']
        expected.append({'number': number, 'startTime': start, 'endTime': end,
                         'speaker': speaker, 'text': text})
        lines.extend([f'{timestamp(start)} --> {timestamp(end)}', f'<v {speaker}>{text}', ''])
    assert sum(len(cue) for cue in cues) == len(words), 'Rendering lost recognized words'
    vtt = ('\n'.join(lines) + '\n').encode()
    publication = folder / 'publication'
    publication.mkdir(exist_ok=True)
    (publication / 'transcript.vtt').write_bytes(vtt)
    save(publication / 'expected-captions.json', expected)
    save(publication / 'render.json', {'sha256': digest(vtt), 'words': len(words), 'cues': len(cues),
                                      'speakers': dict(Counter(w['speaker'] for w in words)),
                                      'review_source_sha256': source_hash,
                                      'full_manual_listen_through': review.get('full_manual_listen_through', False)})
    return publication, vtt, expected

def compare_captions(actual, expected):
    assert len(actual) == len(expected), 'Caption count differs'
    for a, b in zip(actual, expected):
        for field in ['text', 'speaker', 'number']:
            assert a.get(field) == b[field], (field, a, b)
        for field in ['startTime', 'endTime']:
            assert abs(a[field] - b[field]) < .00001, (field, a, b)

def target(feed, guid):
    return next(x for x in ET.fromstring(feed).findall('./channel/item') if x.findtext('guid') == guid)

class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, text):
        self.parts.append(text)

class PageParagraphs(HTMLParser):
    """Read Castopod transcript rows, excluding the episode description/footer."""
    def __init__(self):
        super().__init__();self.inside=False;self.parts=[];self.paragraphs=[]
        self.main_depth=0;self.article_depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='main':self.main_depth+=1
        if tag=='article' and self.main_depth:self.article_depth+=1
        if tag=='p' and self.article_depth:self.inside=True;self.parts=[]
    def handle_endtag(self,tag):
        if tag=='p' and self.inside:
            self.paragraphs.append(' '.join(''.join(self.parts).split()));self.inside=False
        if tag=='article' and self.article_depth:self.article_depth-=1
        if tag=='main' and self.main_depth:
            self.main_depth-=1
            if not self.main_depth:self.article_depth=0;self.inside=False
    def handle_data(self,text):
        if self.inside:self.parts.append(text)

def compare_paragraphs(page,cues):
    parser=PageParagraphs();parser.feed(page)
    groups=[]
    for cue in cues:
        if groups and groups[-1]['speaker']==cue['speaker']:groups[-1]['texts'].append(cue['text'])
        else:groups.append(dict(speaker=cue['speaker'],texts=[cue['text']]))
    expected=[' '.join(' '.join([g['speaker']]+g['texts']).split()) for g in groups]
    actual=parser.paragraphs
    if actual!=expected:raise ValueError('Rendered speaker paragraphs differ from the ordered reviewed cues')
    return dict(verified=True,transcript_paragraphs=len(actual),expected_cues=len(cues),all_cues_exact_ordered_and_grouped_by_speaker=True)
