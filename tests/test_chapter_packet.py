import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import chapter_packet as packet
import chapters as c
import episodes as e


class ChapterPacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.raw = ('WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n<v Alice>Hello <b>Bitcoin</b> &amp; friends.\n\n'
                    '00:00:02.000 --> 00:00:04.000\n<v Alice>Yes yes, exactly.\n\n'
                    '00:00:04.000 --> 00:00:06.000\n<v Bob>A new subject.\n')
        (self.folder/'transcript.vtt').write_text(self.raw)
        (self.folder/'published.mp3').write_bytes(b'synthetic audio')
        self.audio_sha = c.sha(self.folder/'published.mp3')
        self.episode = dict(guid='fixture-guid', final_audio_sha256=self.audio_sha)
        self.task = dict(episode='1')
        self.prepared = dict(episode_guid='fixture-guid', duration=100,
                             inputs={name: c.sha(self.folder/name) for name in ('transcript.vtt', 'published.mp3')})
        e.save(self.folder/'prepared.json', self.prepared)
        self.scope = patch.object(c, 'scope', return_value=(self.task, self.episode))
        self.scope.start()
        self.addCleanup(self.scope.stop)
        e.save(self.folder/'chapters.json', dict(version='1.2.0', chapters=[dict(startTime=0, title='Opening')]))

    def evidence(self):
        windows = [dict(start=0, end=25, reason='Opening')]
        binding = dict(chapters_sha256=c.sha(self.folder/'chapters.json'), source_audio_sha256=self.audio_sha,
                       transcript_sha256=c.sha(self.folder/'transcript.vtt'), windows=windows)
        directory = e.private_root(self.folder/'checks'/e.digest(binding))
        evidence_path = directory/'evidence.json'
        e.save(evidence_path, dict(model_path='/private/model-path', windows=[dict(window=windows[0], segments=[
            dict(start=0.4, end=3.1, text='  Complete boundary text. ', words=[dict(word='Complete', probability=0.9)])])]))
        saved = dict(phase='completed', binding=binding, evidence=str(evidence_path), evidence_sha256=c.sha(evidence_path))
        e.save(directory/'check.json', saved)
        return saved

    def test_complete_transcript_groups_speakers_and_retains_each_word(self):
        originals = {name: (self.folder/name).read_bytes() for name in self.prepared['inputs']}
        view = packet.source_packet({}, self.folder)
        self.assertEqual([row['text'] for row in view['paragraphs']],
                         ['Hello Bitcoin & friends. Yes yes, exactly.', 'A new subject.'])
        self.assertEqual([(row['first_cue'], row['last_cue']) for row in view['paragraphs']], [(1, 2), (3, 3)])
        text = packet.transcript_view(view)
        self.assertNotIn('WEBVTT', text)
        self.assertNotIn('<v ', text)
        self.assertIn('END OF COMPLETE TRANSCRIPT', text)
        self.assertIn(c.sha(self.folder/'transcript.vtt'), text)
        self.assertEqual(originals, {name: (self.folder/name).read_bytes() for name in originals})
        self.assertFalse((self.folder/'review.json').exists())

    def test_overlapping_and_sequential_repetitions_are_preserved(self):
        raw = ('WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n<v A>Yes yes.\n\n'
               '00:00:02.000 --> 00:00:04.000\n<v A>Yes yes.\n\n'
               '00:00:04.000 --> 00:00:06.000\n<v A>Yes yes.\n')
        result = packet.paragraphs(raw, 10)
        self.assertEqual(result['paragraphs'][0]['text'], 'Yes yes. Yes yes. Yes yes.')
        self.assertEqual(result['overlaps'], [dict(cue=2, previous_cue=1)])
        self.assertEqual(result['cues'], 3)

    def test_pagination_covers_long_transcript_without_omission(self):
        cues = ['WEBVTT\n']
        for i in range(120):
            cues.append(f'{packet.clock(i)} --> {packet.clock(i+1)}\n<v Speaker {i%2}>Unique-word-{i}.\n')
        value = packet.paragraphs('\n'.join(cues), 120)
        result = dict(episode='1', episode_guid='fixture-guid', source_audio_sha256='a',
                      transcript_sha256='b', prepared_sha256='c', **value)
        pages = [packet.transcript_view(result, start, 13) for start in range(1, 121, 13)]
        combined = ''.join(pages)
        for i in range(120):
            self.assertEqual(combined.count(f'Unique-word-{i}.'), 1)
        self.assertIn('NEXT paragraph 14', pages[0])
        self.assertNotIn('END OF COMPLETE TRANSCRIPT', pages[0])
        self.assertIn('END OF COMPLETE TRANSCRIPT', pages[-1])
        for start, count in [(0, 1), (121, 1), (1, 0), (1, -1)]:
            with self.assertRaises(ValueError):
                packet.transcript_view(result, start, count)

    def test_overlapping_speaker_backstep_is_retained_and_explicitly_annotated(self):
        raw=('WEBVTT\n\n00:00:02.540 --> 00:00:04.020\n<v Alice>Closing thought.\n\n'
             '00:00:02.220 --> 00:00:04.500\n<v Bob>Overlapping response.\n')
        result=packet.paragraphs(raw,10)
        self.assertEqual([r['text'] for r in result['paragraphs']],['Closing thought.','Overlapping response.'])
        self.assertEqual(result['backsteps'],[dict(cue=2,previous_cue=1,start=2.22,previous_start=2.54)])
        view=packet.transcript_view(dict(episode='1',episode_guid='fixture',source_audio_sha256='a',
            transcript_sha256='b',prepared_sha256='c',**result))
        self.assertIn('retained in original cue/text order',view)
        self.assertLess(view.index('Closing thought.'),view.index('Overlapping response.'))

    def test_unrecognised_text_or_markup_is_not_silently_discarded(self):
        for raw in [self.raw+'\nUnparsed speech\n', self.raw.replace('Hello', '<unknown>Hello</unknown>'),
                    self.raw.replace('00:00:04.000 --> 00:00:06.000', '00:00:00.500 --> 00:00:01.500'),
                    self.raw.replace('00:00:06.000', '00:01:50.000')]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                packet.paragraphs(raw, 100)

    def test_changed_source_is_rejected(self):
        (self.folder/'transcript.vtt').write_text(self.raw.replace('Bitcoin', 'changed'))
        with self.assertRaisesRegex(ValueError, 'source artifacts changed'):
            packet.source_packet({}, self.folder)

    def test_boundaries_omit_words_and_model_paths_but_keep_all_segments_and_hashes(self):
        saved = self.evidence()
        result = packet.boundary_packet({}, self.folder)
        self.assertEqual(result['evidence'][0]['segments'], [dict(start=0.4, end=3.1, text='Complete boundary text.')])
        view = packet.boundary_view(result)
        self.assertIn(saved['evidence_sha256'], view)
        self.assertIn('00:00:00.400–00:00:03.100 Complete boundary text.', view)
        for hidden in ('private/model-path', 'probability', 'words', 'model_path'):
            self.assertNotIn(hidden, json.dumps(result))
        self.assertFalse((self.folder/'review.json').exists())

    def test_stale_chapters_and_tampered_evidence_stop_without_recognition(self):
        saved = self.evidence()
        with patch.object(c.subprocess, 'run') as recognize:
            path = Path(saved['evidence'])
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError, 'unresolved or changed'):
                packet.boundary_packet({}, self.folder)
            # A new chapter revision cannot reuse the earlier evidence either.
            e.save(self.folder/'chapters.json', dict(version='1.2.0', chapters=[dict(startTime=0, title='Changed')]))
            with self.assertRaisesRegex(ValueError, 'Run and review'):
                packet.boundary_packet({}, self.folder)
            recognize.assert_not_called()

    def test_export_cannot_overwrite_an_original(self):
        config = self.folder/'config.json'
        e.save(config, {})
        before = (self.folder/'transcript.vtt').read_bytes()
        with patch.object(sys, 'argv', ['chapter_packet.py', '--config', str(config), '--folder', str(self.folder),
                                      '--out', str(self.folder/'transcript.vtt'), 'transcript']):
            with self.assertRaises(FileExistsError):
                packet.main()
        self.assertEqual((self.folder/'transcript.vtt').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
