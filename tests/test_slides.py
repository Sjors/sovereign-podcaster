import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slides', ROOT / 'tools/slides.py')
slides = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slides)


class SlideTests(unittest.TestCase):
    def test_revision_integrity_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'r1'
            cmd = [sys.executable, str(ROOT / 'tools/slides.py'), 'build',
                   '--transcript', str(ROOT / 'examples/transcript.json'),
                   '--plan', str(ROOT / 'examples/slides.json'), '--out', str(out)]
            subprocess.run(cmd, check=True, capture_output=True)
            slides.verify(out)
            self.assertEqual((out / 'transcript.json').read_bytes(),
                             (ROOT / 'examples/transcript.json').read_bytes())
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            (out / 'index.html').write_text('changed after review')
            with self.assertRaises(ValueError):
                slides.verify(out)

    def test_timeline_and_source_validation(self):
        transcript = json.loads((ROOT / 'examples/transcript.json').read_text())
        plan = {'slides': [{'start': 0, 'end': 21, 'kind': 'topic', 'title': 'Bad'}]}
        with self.assertRaises(ValueError):
            slides.validate(transcript, plan)
        plan['slides'][0].update(end=10, kind='source', source={
            'url': 'javascript:alert(1)', 'title': 'Source', 'excerpt': 'Excerpt'})
        with self.assertRaises(ValueError):
            slides.validate(transcript, plan)

    def test_escaping_feedback_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            plan = json.loads((ROOT / 'examples/slides.json').read_text())
            plan['slides'][0]['title'] = '<script>alert(1)</script>'
            (folder / 'plan.json').write_text(json.dumps(plan))
            (folder / 'feedback.txt').write_text('Make the title clearer')
            args = type('Args', (), dict(transcript=ROOT / 'examples/transcript.json',
                        plan=folder / 'plan.json', out=folder / 'r2', feedback=folder / 'feedback.txt'))
            slides.build(args)
            slides.verify(args.out)
            page = (args.out / 'index.html').read_text()
            self.assertNotIn('<script>', page)
            self.assertIn('&lt;script&gt;', page)
            self.assertEqual((args.out / 'feedback.txt').read_text(), 'Make the title clearer')


if __name__ == '__main__':
    unittest.main()
