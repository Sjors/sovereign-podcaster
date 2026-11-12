"""Safe diagnostic reports for the user's copy/paste maintenance workflow."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import failures as f
import jobs

class FailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.store=patch.object(f,'store_root',return_value=self.root/'reports');self.store.start();self.addCleanup(self.store.stop)

    def test_report_drops_secrets_urls_raw_exception_and_untrusted_identifiers(self):
        secret='sk-super-secret';url='https://googleapis.example/upload?upload_id=CAPABILITY'
        error=RuntimeError('uncertain response '+secret+' '+url+' PRIVATE TRANSCRIPT')
        value=f.from_exception(error,'youtube-private',{'show':'safe','episode':'one','job':secret})
        raw=json.dumps(value);text=f.format_report(value)
        for bad in (secret,url,'CAPABILITY','PRIVATE TRANSCRIPT'):
            self.assertNotIn(bad,raw);self.assertNotIn(bad,text)
        denied=f.from_exception(RuntimeError('API HTTP 403 '+secret+' '+url),'controller')
        self.assertEqual(denied['http_status'],403);self.assertNotIn(secret,f.format_report(denied))
        self.assertIn('uncertain-outcome',text);self.assertIn('may be partial',text);self.assertIn('Show: safe',text)
        poisoned=dict(value,summary=secret,source_revision=secret,python=secret,utc=secret)
        self.assertNotIn(secret,f.format_report(poisoned))

    def test_classifier_knows_tools_modules_inputs_permissions_and_guards(self):
        cases=[(FileNotFoundError(2,'missing','ffmpeg'),'missing-tool','ffmpeg'),
            (ModuleNotFoundError("Secret should never appear",name='PIL.Image'),'missing-module','PIL'),
            (FileNotFoundError(2,'missing','/private/original.wav'),'missing-input','audio'),
            (FileNotFoundError(2,'missing','/private/application.key'),'configuration-required','OpenAI-application-key'),
            (PermissionError('raw secret'),'permission-denied','unknown'),
            (ValueError('Maintenance guard does not permit this action'),'authorization-required','maintenance-control')]
        for error,code,component in cases:
            with self.subTest(code=code,component=component):
                value=f.from_exception(error,'render');self.assertEqual((value['code'],value['component']),(code,component))

    def test_cli_writes_private_report_and_prints_only_uuid_notice(self):
        path=self.root/'failure.json';out=io.StringIO()
        def failed():raise ModuleNotFoundError('Private raw body',name='PIL')
        with patch.dict(os.environ,{'SP_FAILURE_REPORT':str(path)}),contextlib.redirect_stderr(out):
            with self.assertRaises(SystemExit) as stopped:f.cli(failed,'render')
        self.assertEqual(stopped.exception.code,1);value=e.read(path)
        self.assertEqual(out.getvalue().strip(),f.format_notice(value));self.assertEqual(uuid.UUID(value['id']).version,4);self.assertEqual(f.lookup(value['id'])['report'],value);self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn('Private raw body',out.getvalue());self.assertEqual(f.persist(f.report(),path),value)

    def test_missing_tool_worker_notifies_with_stable_report_and_never_runs_production(self):
        folder=self.root/'job';folder.mkdir();request=dict(kind='render',parameters=dict(revision='/fixture/one'),notify=dict(home='/fixture/marmot',account='a'*64,group='b'*64))
        e.save(folder/'job.json',dict(state='queued',id='render-one',request=request,request_sha256=e.digest(request)))
        def capture(args,**kw):
            self.message=e.read(Path(args[-1]));return json.dumps(dict(response=dict(message_ids_hex=['c'*64]))).encode()
        with patch.object(jobs.shutil,'which',return_value=None),patch.object(jobs.subprocess,'run') as run,patch.object(jobs.subprocess,'check_output',side_effect=capture):
            # Avoid git's read-only source stamp sharing the mocked subprocess module.
            with patch.object(f,'source_revision',return_value='a'*40):result=jobs.worker(folder)
            run.assert_not_called()
        self.assertEqual(result['state'],'failed');value=e.read(folder/'failure.json')
        self.assertEqual(value['code'],'missing-tool');self.assertEqual(value['effects'],'not-started')
        self.assertEqual(f.format_notice(value),self.message['text']);self.assertNotIn('apt package',self.message['text']);self.assertNotIn('Stage:',self.message['text']);self.assertNotIn('/fixture',self.message['text']);self.assertEqual(f.lookup(value['id'])['report'],value)
        with patch.object(jobs.subprocess,'check_output') as send:jobs.notify(folder);send.assert_not_called()
        self.assertEqual(jobs.status(folder)['failure']['id'],value['id'])

    def test_worker_uses_child_report_and_never_quotes_raw_log(self):
        folder=self.root/'job';folder.mkdir();request=dict(kind='render',parameters=dict(revision='/fixture'))
        e.save(folder/'job.json',dict(state='queued',id='one',request=request,request_sha256=e.digest(request)))
        def failed(*args,**kw):
            self.assertNotIn('OPENAI_API_KEY',kw['env'])
            path=Path(kw['env']['SP_FAILURE_REPORT']);e.save(path,f.report('missing-input','render','transcript'))
            kw['stdout'].write(b'PRIVATE TRANSCRIPT sk-never-copy-this')
            return subprocess.CompletedProcess(args[0],1)
        with patch.object(f,'source_revision',return_value='a'*40),patch.object(jobs,'preflight',return_value=None),patch.object(jobs.subprocess,'run',side_effect=failed):jobs.worker(folder)
        self.assertEqual(e.read(folder/'failure.json')['component'],'transcript')
        self.assertNotIn('PRIVATE TRANSCRIPT',f.format_report(e.read(folder/'failure.json')))

    def test_uuid_lookup_preserves_origin_and_refuses_tampering_or_unsafe_ids(self):
        path=self.root/'job/failure.json';path.parent.mkdir(mode=0o700)
        value=f.persist(f.report('missing-input','render','audio'),path)
        entry=f.lookup(value['id']);self.assertEqual(entry['record_path'],str(path))
        self.assertEqual((f.store_root()/'index'/(value['id']+'.json')).stat().st_mode&0o777,0o600)
        for bad in ('../secret','/etc/passwd','not-a-uuid',str(uuid.uuid1())):
            with self.subTest(bad=bad),patch.object(f,'private_json') as read:
                with self.assertRaises(ValueError):f.lookup(bad)
                read.assert_not_called()
        e.save(path,f.report())
        with self.assertRaisesRegex(ValueError,'differs'):f.lookup(value['id'])

    def test_legacy_prepared_full_report_cannot_be_sent_after_uuid_switch(self):
        folder=self.root/'legacy-job';folder.mkdir()
        target=dict(home='/fixture/marmot',account='a'*64,group='b'*64)
        e.save(folder/'job.json',dict(state='failed',id='legacy',nonce='nonce',request=dict(kind='render',notify=target)))
        value=f.persist(f.report('missing-input','render','revision'),folder/'failure.json')
        e.save(folder/'notice.send.json',dict(account_id_hex=target['account'],group_id_hex=target['group'],idempotency_key='job-nonce',text=f.format_report(value)))
        with patch.object(jobs.subprocess,'check_output') as send:
            with self.assertRaisesRegex(ValueError,'immutable send intent'):jobs.notify(folder)
            send.assert_not_called()

    def test_index_failure_never_advertises_an_unresolvable_uuid(self):
        value=f.report('storage-full','render','storage')
        with patch.object(f,'persist',side_effect=OSError('private raw detail')):
            notice=f.save_notice(value)
        self.assertNotIn(value['id'],notice);self.assertNotIn('private raw detail',notice);self.assertIn('could not be saved',notice)

    def test_create_defaults_to_uuid_only_and_lookup_is_local_full_report(self):
        out=io.StringIO()
        with patch.object(sys,'argv',['failures','create','--code','missing-input','--stage','prepare','--component','transcript']),contextlib.redirect_stdout(out):f.main()
        identifier=out.getvalue().split('Report UUID: ')[1].splitlines()[0]
        self.assertNotIn('missing-input',out.getvalue())
        diagnostic=io.StringIO()
        with patch.object(sys,'argv',['failures','lookup',identifier,'--json']),contextlib.redirect_stdout(diagnostic):f.main()
        self.assertEqual(json.loads(diagnostic.getvalue())['report']['component'],'transcript')

    def test_missing_revision_preflight_has_actionable_input_role(self):
        with patch.object(jobs.shutil,'which',return_value='/usr/bin/fixture'):
            value=jobs.preflight(dict(kind='package',parameters=dict(revision=str(self.root/'missing'),out=str(self.root/'out'))))
        self.assertEqual((value['code'],value['component']),('missing-input','revision'))
if __name__=='__main__':unittest.main()
