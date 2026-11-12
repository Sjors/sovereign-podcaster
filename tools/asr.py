"""Ported local Whisper and anonymous diarization pipeline; configuration contains paths, never secrets."""
from collections import Counter
from dataclasses import asdict
import datetime as dt
import difflib
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import time
from episodes import save
CONFIG={}
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def transcribe(folder, model_kind):
    complete = folder / f'{model_kind}-complete.json'
    if complete.exists():
        return
    output = folder / f'{model_kind}-segments.jsonl'
    if output.exists():
        raise RuntimeError(f'Partial ASR retained for inspection: {output}')
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    model_path = Path(CONFIG['primary_model'] if model_kind=='primary' else CONFIG['secondary_model'])
    episode = json.loads((folder / 'episode.json').read_text())
    glossary = json.loads(Path(CONFIG['glossary']).read_text())
    save(folder / 'technical-glossary.json', {
        'source': CONFIG['glossary'], 'sha256': sha(Path(CONFIG['glossary'])), 'aliases': glossary['aliases'],
        'use': 'Canonical spellings and pronunciation clues for contextual review; never blind reverse substitutions.'})
    vocabulary = (CONFIG.get('review_vocabulary','')+' '+episode['title']+'. '+'. '.join(episode.get('vocabulary',[]))).strip()
    assert not re.search(r'https?://|npub1|nsec1|[a-z0-9]{45,}', vocabulary, re.I), 'Prompt contains non-speech contact/URL data'
    started = time.monotonic()
    model = WhisperModel(str(model_path), device='cpu', compute_type='int8', cpu_threads=CONFIG.get('cpu_threads',8),
                         num_workers=1, local_files_only=True)
    options = dict(language='en', beam_size=5, word_timestamps=True,
                   condition_on_previous_text=False, vad_filter=True,
                   vad_parameters={'min_silence_duration_ms': 500}, initial_prompt=None)
    if model_kind == 'secondary':
        # Sequential decoding enables Whisper's normal temperature fallback for
        # high-compression/low-confidence segments, rather than keeping a bad batch.
        segments, info = model.transcribe(str(folder / 'audio-16k.wav'),
                                         temperature=(0, .2, .4, .6, .8, 1.0), **options)
    else:
        segments, info = BatchedInferencePipeline(model).transcribe(
            str(folder / 'audio-16k.wav'), batch_size=8, temperature=0, **options)
    metadata = {'model_path': str(model_path), 'faster_whisper': version('faster-whisper'),
                'duration': info.duration, 'duration_after_vad': info.duration_after_vad,
                'initial_prompt': None, 'review_vocabulary': vocabulary,
                'cpu_threads': CONFIG.get('cpu_threads',8), 'compute_type': 'int8',
                'batch_size': None if model_kind == 'secondary' else 8, 'beam_size': 5,
                'temperature': [0, .2, .4, .6, .8, 1.0] if model_kind == 'secondary' else 0,
                'pipeline_version': 3, 'word_timestamps': True,
                'condition_on_previous_text': False, 'vad_filter': True,
                'source_sha256': json.loads((folder / 'download.json').read_text())['sha256']}
    save(folder / f'{model_kind}-info.json', metadata)
    count = 0
    with output.open('x') as stream:
        for segment in segments:
            stream.write(json.dumps(asdict(segment), ensure_ascii=False) + '\n')
            stream.flush()
            count += 1
            print(f'{model_kind}: {segment.end:.1f}/{info.duration:.1f}s {segment.text[:95]}', flush=True)
    save(complete, {'segments': count, 'elapsed_seconds': time.monotonic() - started,
                    'completed_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'segments_sha256': sha(output)})

def diarize(folder, clusters):
    target = folder / 'diarization.json'
    if target.exists():
        return
    import sherpa_onnx
    import soundfile as sf
    started = time.monotonic()
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=CONFIG['segmentation_model']), num_threads=4),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=CONFIG['embedding_model'], num_threads=4),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=clusters, threshold=0.5),
        min_duration_on=0.3, min_duration_off=0.5)
    assert config.validate()
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio, rate = sf.read(folder / 'audio-16k.wav', dtype='float32')
    assert rate == diarizer.sample_rate
    turns = [{'start': float(x.start), 'end': float(x.end), 'cluster': int(x.speaker)}
             for x in diarizer.process(audio).sort_by_start_time()]
    assert turns, 'No speaker turns detected'
    save(target, {'turns': turns, 'requested_clusters': clusters,
                  'actual_clusters': len({x['cluster'] for x in turns}),
                  'method': 'sherpa-onnx pyannote segmentation 3.0 + NeMo TitaNet; anonymous clusters',
                  'sherpa_onnx': version('sherpa-onnx'), 'elapsed_seconds': time.monotonic() - started})

def assign(words, turns):
    result = []
    for original in words:
        word = dict(original)
        overlap = Counter()
        for turn in turns:
            if turn['start'] > word['end']:
                break
            shared = max(0, min(turn['end'], word['end']) - max(turn['start'], word['start']))
            if shared:
                overlap[turn['cluster']] += shared
        if overlap:
            word['cluster'] = overlap.most_common(1)[0][0]
            word['cluster_overlap_fraction'] = overlap[word['cluster']] / max(word['end'] - word['start'], .001)
            word['speaker_ambiguous'] = len(overlap) > 1
        else:
            center = (word['start'] + word['end']) / 2
            nearest = min(turns, key=lambda t: max(t['start'] - center, center - t['end'], 0))
            distance = max(nearest['start'] - center, center - nearest['end'], 0)
            word['cluster'] = nearest['cluster'] if distance <= .75 else None
            word['speaker_ambiguous'] = True
            word['nearest_speech_distance'] = distance
        result.append(word)
    return result

def review_material(folder):
    primary = [json.loads(line) for line in (folder / 'primary-segments.jsonl').read_text().splitlines()]
    secondary = [json.loads(line) for line in (folder / 'secondary-segments.jsonl').read_text().splitlines()]
    turns = json.loads((folder / 'diarization.json').read_text())['turns']
    primary_words = [dict(word, segment_id=segment['id']) for segment in primary for word in segment.get('words') or []]
    assert primary_words, 'Empty primary transcription'
    words = assign(primary_words, turns)
    duration = json.loads((folder / 'primary-info.json').read_text())['duration']
    flags = []
    asr_alerts = []
    for segment in primary:
        tokens = re.findall(r"[\w']+", segment['text'].lower())
        reasons = []
        if re.search(r'npub1|nsec1|[a-z0-9]{45,}', segment['text'], re.I):
            reasons.append('contact_or_hash_like_output_requires_audio_check')
        if segment.get('compression_ratio', 0) > 2.4:
            reasons.append('high_compression_possible_repetition')
        for size in range(1, 6):
            counts = Counter(tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1))
            if counts and max(counts.values()) >= 4 and max(counts.values()) * size >= .5 * len(tokens):
                reasons.append('highly_repeated_phrase')
                break
        if len(tokens) < .8 * (segment['end'] - segment['start']) and segment['end'] - segment['start'] > 15:
            reasons.append('sparse_words_over_long_speech_span')
        if reasons:
            asr_alerts.append({'segment_id': segment['id'], 'start': segment['start'], 'end': segment['end'],
                               'text': segment['text'], 'reasons': reasons})
    for index, word in enumerate(words):
        reasons = []
        if word['probability'] < .5:
            reasons.append('low_ASR_probability')
        if word['end'] <= word['start']:
            reasons.append('zero_word_duration')
        if word['speaker_ambiguous']:
            reasons.append('ambiguous_speaker')
        if not 0 <= word['start'] <= word['end'] <= duration + .1:
            reasons.append('outside_audio')
        if reasons:
            flags.append({'word_index': index, **word, 'reasons': reasons})
    comparisons = []
    secondary_words = [word for segment in secondary for word in segment.get('words') or []]
    for start in range(0, int(duration) + 1, 30):
        a = ''.join(w['word'] for w in words if start <= (w['start'] + w['end']) / 2 < start + 30).strip()
        b = ''.join(w['word'] for w in secondary_words if start <= (w['start'] + w['end']) / 2 < start + 30).strip()
        normal = lambda s: re.findall(r"[\w']+", s.lower())
        aw, bw = normal(a), normal(b)
        ratio = difflib.SequenceMatcher(None, aw, bw, autojunk=False).ratio()
        comparisons.append({'start': start, 'end': min(start + 30, duration),
                            'agreement_ratio': ratio, 'primary': a, 'secondary': b})
    save(folder / 'words-for-review.json', words)
    save(folder / 'review-flags.json', flags)
    save(folder / 'asr-quality-alerts.json', asr_alerts)
    save(folder / 'model-comparison.json', comparisons)
    technical_alerts = []
    aliases = json.loads(Path(CONFIG['glossary']).read_text())['aliases']
    for segment in primary:
        text = segment['text']
        candidates = [key for key, spoken in aliases.items()
                      if spoken.casefold() != key.casefold()
                      and re.search(r'(?<!\w)' + re.escape(spoken) + r'(?!\w)', text, re.I)]
        if re.search(r'\bmusic\b', text, re.I):
            candidates.extend(['MuSig', 'MuSig2'])
        if re.search(r'\bminors?\b|\bminers?\b', text, re.I):
            candidates.append('miner/minor: choose from context, never blindly replace')
        if re.search(r'\bfutures?\b', text, re.I):
            candidates.append('future/feature: inspect the recording and context; preserve temporal future')
        if candidates:
            technical_alerts.append({'start': segment['start'], 'end': segment['end'],
                                     'text': text, 'possible_terms': sorted(set(candidates)),
                                     'action': 'Review in context/audio; no automatic replacement'})
    save(folder / 'technical-review-alerts.json', technical_alerts)
    save(folder / 'ready-for-review.json', {
        'primary_segments_sha256': sha(folder / 'primary-segments.jsonl'), 'word_count': len(words),
        'flags': len(flags), 'speaker_clusters': sorted({t['cluster'] for t in turns}),
        'ASR_segment_alerts': len(asr_alerts),
        'windows_below_90_percent_agreement': sum(x['agreement_ratio'] < .9 for x in comparisons),
        'status': 'needs_wording_speaker_and_timing_review', 'published': False,
        'model_comparison_limit': 'Related Whisper models can agree on an error; agreement is not measured accuracy.'})
    lines = []
    for segment in primary:
        related = [w for w in words if w['segment_id'] == segment['id']]
        lines.append(f"[{segment['start']:.2f}–{segment['end']:.2f}] clusters {dict(Counter(w['cluster'] for w in related))}: {segment['text'].strip()}")
    (folder / 'review.txt').write_text('\n'.join(lines) + '\n')
