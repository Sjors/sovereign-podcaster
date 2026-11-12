import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import review_media as m
import jobs
import episodes as e

class BackgroundTests(unittest.TestCase):
    def request(self,root):
        return dict(kind='review-fragment',parameters=dict(input=str(root/'source.mp4'),home=str(root/'marmot'),id='fixture-review',start='0',duration='1',account='a'*64,group='b'*32,caption='Synthetic review fixture'))

    def test_fragment_job_preserves_explicit_route_and_rejects_publication_flags(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            request=self.request(Path(d));command=jobs.command(request)
            self.assertEqual(command[2],'fragment')
            for key,value in request['parameters'].items():self.assertEqual(command[command.index('--'+key)+1],value)
            with self.assertRaises(ValueError):jobs.command(dict(request,apply=True))
            with patch.object(jobs.shutil,'which',return_value=None):failure=jobs.preflight(request)
            self.assertEqual((failure['code'],failure['stage'],failure['component'],failure['effects']),('missing-tool','prepare','ffmpeg','not-started'))

    def test_fragment_worker_stages_verified_media_without_sending_or_repeating(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            root=Path(d);request=self.request(root);source=root/'source.mp4'
            subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=orange:s=320x180:r=15:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
            original=e.file_record(source)
            folder=e.private_root(root/'jobs'/'clip');e.save(folder/'job.json',dict(schema=1,id='clip',request=request,request_sha256=e.digest(request),state='queued'))
            with patch.object(jobs,'notify',return_value=dict(state='not_configured')) as notify:
                state=jobs.worker(folder)
            self.assertEqual(state['state'],'completed');self.assertEqual(state['exit_code'],0)
            manifest=root/'marmot/media-uploads/fixture-review/send.json';value=e.read(manifest)
            self.assertEqual(value['account_id_hex'],'a'*64);self.assertEqual(value['group_id_hex'],'b'*32)
            self.assertEqual(e.file_record(source),original)
            evidence=e.read(manifest.parent/'job.json');self.assertTrue(evidence['full_decode_passed']);self.assertEqual(evidence['state'],'verified')
            self.assertEqual(value['attachments'][0]['sha256'],e.file_record(manifest.parent/'clip.mp4')['sha256'])
            self.assertFalse((root/'marmot/dev/client-sends').exists())
            with patch.object(jobs.subprocess,'Popen') as popen:
                self.assertEqual(jobs.start(folder.parent,'clip',request)['state'],'completed');popen.assert_not_called()
            with self.assertRaises(ValueError):jobs.worker(folder)

    def test_detached_render_drops_keys_and_duplicate_launch_is_refused(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            root=Path(d);source=root/'synthetic.mp4';source.write_bytes(b'synthetic fixture')
            with patch.dict(m.os.environ,{'OPENAI_API_KEY':'synthetic-app','CODEX_API_KEY':'synthetic-executor','SSH_AUTH_SOCK':'synthetic-agent'}),patch.object(m.subprocess,'Popen',return_value=Mock(pid=12345)) as popen:
                result=m.background_fallback(source,root/'render')
                self.assertTrue(popen.call_args.kwargs['start_new_session'])
                env=popen.call_args.kwargs['env']
                self.assertFalse({'OPENAI_API_KEY','CODEX_API_KEY','SSH_AUTH_SOCK'}&env.keys())
                with self.assertRaisesRegex(ValueError,'already exists'):m.background_fallback(source,root/'render')
                self.assertEqual(popen.call_count,1)
                self.assertEqual(json.loads((root/'render.launcher.json').read_text())['result'],result['result'])

if __name__=='__main__':unittest.main()
