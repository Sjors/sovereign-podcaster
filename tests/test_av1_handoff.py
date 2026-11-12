import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from video import av1_packaging as a
from video import hls as w


class Av1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_codec_strings_use_configuration_not_h264_constant(self):
        self.assertEqual(a.av1_codec_string(bytes.fromhex('81040c00')), 'av01.0.04M.08')
        self.assertEqual(a.av1_codec_string(bytes.fromhex('8105cc00')), 'av01.0.05H.10')
        self.assertEqual(a.av1_codec_string(bytes.fromhex('8148e000')), 'av01.2.08H.12')
        for invalid in (b'', bytes.fromhex('01040c00'), bytes.fromhex('81242c00')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                a.av1_codec_string(invalid)

    def test_ffprobe_configuration_dump(self):
        dump = '\n00000000: 8104 0c00 0a0e 0000 0024 c6ab df00 be04  .........$......\n00000010: 0404 0410                                ....\n'
        record = a.extradata_bytes(dump)
        self.assertEqual(len(record), 20)
        self.assertEqual(a.av1_codec_string(record), 'av01.0.04M.08')

    def manifest(self):
        entries = []
        for label in a.SIZES:
            path = self.root / f'{label}.mp4'
            report = self.root / f'{label}.json'
            path.write_bytes(label.encode())
            report.write_text(json.dumps({'full_decode_passed': True}))
            entries.append(dict(label=label, path=str(path), verification=str(report)))
        manifest = dict(version=1, expected_duration_seconds=20.0, renditions=entries,
                        fallback=dict(entries[1], sha256='approved-hash', size=12345))
        path = self.root / 'inputs.json'
        path.write_text(json.dumps(manifest))
        return path, manifest

    def test_pending_or_failed_render_reports_are_not_imported(self):
        path, manifest = self.manifest()
        self.assertTrue(a.readiness(path)['ready'])
        report = Path(manifest['renditions'][0]['verification'])
        report.unlink()
        self.assertFalse(a.readiness(path)['ready'])
        args = SimpleNamespace(manifest=path, output=self.root / 'output')
        with self.assertRaisesRegex(ValueError, 'not ready'):
            a.prepare(args, w)
        self.assertFalse(args.output.exists())
        report.write_text(json.dumps({'full_decode_passed': False}))
        self.assertFalse(a.readiness(path)['ready'])

    def test_report_must_match_exact_file_and_approved_fallback(self):
        path, manifest = self.manifest()
        item = manifest['fallback']
        report = dict(full_decode_passed=True, fast_start=True, no_edit_lists=True,
                      normalized_retained_spoken_words_preserved=True, file=item['path'], sha256='wrong', bytes=9)
        Path(item['verification']).write_text(json.dumps(report))
        details = dict(sha256='actual', size=9)
        with patch.object(a, 'media_details', return_value=details), self.assertRaisesRegex(ValueError, 'exact source bytes'):
            a.verified_input(item, manifest, w)
        report['sha256'] = 'actual'
        Path(item['verification']).write_text(json.dumps(report))
        with patch.object(a, 'media_details', return_value=details), self.assertRaisesRegex(ValueError, 'Approved input sha256 mismatch'):
            a.verified_input(item, manifest, w)

    def test_rfc_peak_uses_contiguous_windows_and_measured_audio_bytes(self):
        segments = []
        for i, size in enumerate([600, 600, 2800]):
            path = self.root / str(i)
            path.write_bytes(b'x' * size)
            segments.append(path)
        result = a.bandwidth(segments, [6, 6, 2])
        # The short tail is under half a target duration: measure it with its neighbour.
        self.assertEqual(result['peak_bandwidth'], 3400)
        self.assertEqual(result['average_bandwidth'], 2286)

    def test_independent_480_fallback_has_its_own_mime_dimensions_and_rate(self):
        bundle = dict(master_sha256='a' * 64, fallback_sha256='b' * 64,
                      assets=[dict(sha256='a' * 64, size=777), dict(sha256='b' * 64, size=12345)],
                      variants=[dict(width=1280, height=720, duration=2438.9, codecs='av01.0.05M.08,mp4a.40.2')],
                      fallback=dict(width=854, height=480, duration=20.021333, average_bitrate=181618,
                                    codecs='av01.0.04M.08,mp4a.40.2'))
        tags = w.media_tags(bundle, ['https://server.test'])
        self.assertIn('m application/vnd.apple.mpegurl', tags[0])
        self.assertEqual([x for x in tags[0] if x.startswith('m ')], ['m application/vnd.apple.mpegurl'])
        self.assertIn('m video/mp4; codecs="av01.0.04M.08,mp4a.40.2"', tags[1])
        self.assertIn('dim 854x480', tags[1])
        self.assertIn('bitrate 181618', tags[1])
        self.assertNotIn('dim 1280x720', tags[1])
        self.assertNotIn('avc1', str(tags))

    def test_handoff_rejects_stereo_or_wrong_codec(self):
        info = dict(streams=[dict(codec_type='video', codec_name='av1', codec_tag_string='av01'),
                             dict(codec_type='audio', codec_name='aac', profile='LC', sample_rate='48000', channels=2)])
        with patch.object(a.subprocess, 'check_output', return_value=json.dumps(info).encode()), \
                self.assertRaisesRegex(ValueError, 'mono'):
            a.media_details(self.root / 'source.mp4', w)


if __name__ == '__main__':
    unittest.main()
