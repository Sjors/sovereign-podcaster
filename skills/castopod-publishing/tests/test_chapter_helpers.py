"""Run the actual PHP helper entry points with synthetic models; no hosting access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
PHP=json.loads(os.environ['PHP_TEST_COMMAND']) if os.environ.get('PHP_TEST_COMMAND') else ([shutil.which('php')] if shutil.which('php') else None)


@unittest.skipUnless(PHP,'PHP CLI is unavailable (set PHP_TEST_COMMAND to a JSON argv list)')
class ChapterHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.app=self.root/'app'
        for name in ('public','app/Config','writable','fake-system'):(self.app/name).mkdir(parents=True,exist_ok=True)
        (self.app/'app/Config/Paths.php').write_text('<?php namespace Config; class Paths { public string $systemDirectory = __DIR__."/../../fake-system"; }')
        shutil.copyfile(HERE/'chapter-model-fixture.php',self.app/'fake-system/Boot.php')
        self.state=self.root/'state.json';self.media=self.root/'uploaded-chapters.json'
        self.env=dict(os.environ,CHAPTER_FIXTURE_STATE=str(self.state),CHAPTER_FIXTURE_MEDIA=str(self.media))
        self.original=dict(id=1,slug='fixture',title='Synthetic title',guid='fixture-guid',status='published',
            published_at='2026-11-03 00:00:00',description_markdown='Original source links and sponsor',
            audio_url='https://example.org/audio.mp3',audio_file_key='podcasts/demo/fixture.mp3',audio_file_size=123,
            duration=900,link='https://example.org/fixture',number=1,season=None,
            transcript_id=None,transcript_url=None,transcript_json_url=None,chapters_id=None,chapters_url=None)
        self.state.write_text(json.dumps(self.original))
        self.expected=self.root/'expected.json';self.expected.write_text(json.dumps(self.inspect()['episode']))
        self.chapters=self.root/'chapters.json';self.chapters.write_text(json.dumps(dict(version='1.2.0',chapters=[dict(startTime=t,title=title) for t,title in [(0,'Opening'),(300,'Second Topic'),(600,'Final Topic')]])))
        self.notes=self.root/'notes.md';self.notes.write_text('Original source links and sponsor\n\n00:00:00 Opening\n00:05:00 Second Topic\n00:10:00 Final Topic\n')

    def helper(self,name,**options):
        return subprocess.run([*PHP,str(HERE.parent/'scripts/castopod'/name),'--app='+str(self.app),
            '--podcast=demo','--slug=fixture','--user=fixture',*[f'--{key.replace("_","-")}={value}' for key,value in options.items()]],env=self.env,capture_output=True,text=True)

    def inspect(self):
        result=self.helper('castopod-inspect.php')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        return json.loads(result.stdout)

    def test_real_helpers_attach_native_chapters_and_preserve_unrelated_fields(self):
        before=json.loads(self.expected.read_text())
        result=self.helper('castopod-update-episode.php',chapters=self.chapters,description_file=self.notes,expected_state=self.expected)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        after=self.inspect();self.assertIn('chapters',after['features'])
        self.assertEqual(self.media.read_bytes(),self.chapters.read_bytes())
        self.assertEqual(after['episode']['chapters_url'],'https://example.org/chapters.json')
        self.assertEqual(after['episode']['description_markdown'],self.notes.read_text())
        for key,value in before.items():
            if not key.startswith(('chapters_','description_')):self.assertEqual(after['episode'][key],value,key)

    def test_server_lock_snapshot_rejects_intervening_edits_before_any_media_write(self):
        self.original['description_markdown']='Owner revised this after inspection'
        self.state.write_text(json.dumps(self.original))
        result=self.helper('castopod-update-episode.php',chapters=self.chapters,description_file=self.notes,expected_state=self.expected)
        self.assertNotEqual(result.returncode,0);self.assertFalse(self.media.exists())
        self.assertEqual(json.loads(self.state.read_text())['description_markdown'],self.original['description_markdown'])

    def test_invalid_chapter_timeline_stops_before_writing_notes_or_media(self):
        for times in ([0,600,300],[1,300,600],[0,300,900]):
            self.chapters.write_text(json.dumps(dict(version='1.2.0',chapters=[dict(startTime=t,title='Fixture') for t in times])))
            result=self.helper('castopod-update-episode.php',chapters=self.chapters,description_file=self.notes,expected_state=self.expected)
            self.assertNotEqual(result.returncode,0);self.assertFalse(self.media.exists())
            self.assertEqual(json.loads(self.state.read_text()),self.original)

    def test_number_only_correction_preserves_uuid_and_all_other_fields(self):
        before=self.inspect()['episode']
        result=self.helper('castopod-update-episode.php',number=79,expected_state=self.expected)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        after=self.inspect()['episode'];self.assertEqual(after.pop('number'),79);before.pop('number')
        self.assertEqual(after,before);self.assertFalse(self.media.exists())

    def test_number_update_requires_snapshot_and_cannot_include_media_or_notes(self):
        for options in (dict(number=79),dict(number=0,expected_state=self.expected),
                        dict(number=79,expected_state=self.expected,chapters=self.chapters),
                        dict(number=79,expected_state=self.expected,description_file=self.notes)):
            result=self.helper('castopod-update-episode.php',**options)
            self.assertNotEqual(result.returncode,0);self.assertFalse(self.media.exists())
            self.assertEqual(json.loads(self.state.read_text()),self.original)


if __name__=='__main__':unittest.main()
