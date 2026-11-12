"""Video handoffs invoke a model only for new authorized work."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import video_tasks as v
e=v.e

class VideoTasksTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.instance=dict(work_root=str(self.root/'work'),state_root=str(self.root/'state'),video_tasks_enabled=True)
        with e.journal(Path(self.instance['work_root'])) as (root,data):
            self.item=e.initialize(root,data,'fixture','100');self.path=Path(self.item['directory'])/'video-task.json'
            auth=self.root/'authorization.json';e.save(auth,dict(human_request='Explicit fixture'))
            task=dict(id='fixture-task',phase='queued',announce=False,handled_events=[],authorization=e.file_record(auth),route=dict(account='a'*64,group='b'*32))
            e.save(self.path,task);self.item['video_task']=dict(path=str(self.path))
        self.run=Mock(return_value='WAITING_FOR_JOB');self.deliver=Mock()
    def once(self):v.run_once(self.instance,self.run,self.deliver)
    def job(self,state='completed'):
        path=e.private_root(self.path.parent/'jobs'/'fixture')/'job.json';request=dict(kind='render',parameters=dict(revision=str(self.path.parent/'r1')))
        e.save(path,dict(state=state,request=request,request_sha256=e.digest(request),nonce='fixture',exit_code=0))
        return path
    def test_initial_assignment_and_completed_job_wake_once_without_idle_calls_or_chat(self):
        self.once();self.once();self.assertEqual(self.run.call_count,1);self.deliver.assert_not_called()
        self.job();self.once();self.once();self.assertEqual(self.run.call_count,2);self.deliver.assert_not_called()
    def test_unfinished_job_waits_without_model_calls(self):
        self.job('queued');self.once();self.run.assert_not_called();self.deliver.assert_not_called()
    def test_failed_publication_can_resume_only_after_matching_verified_stage_recovery(self):
        task=e.read(self.path);task['publication_config']=str(self.root/'publication.json');e.save(self.path,task)
        with e.journal(Path(self.instance['work_root'])) as (_,data):
            item=e.episode(data,'fixture','100');item['revisions']['r2']=dict(nostr_manifest_sha256='a'*64,manifest_sha256='b'*64)
            item['publications'].append(dict(stage='nostr',manifest_sha256='a'*64,receipt=dict(verified=True,video_event_id='c'*64)))
        request=dict(kind='nostr',parameters=dict(root=self.instance['work_root'],show='fixture',episode='100',revision='r2',config=task['publication_config']),apply=True)
        path=e.private_root(self.path.parent/'jobs'/'recover')/'job.json'
        e.save(path,dict(state='failed',request=request,request_sha256=e.digest(request),nonce='fixture',exit_code=1))
        self.once();self.once();self.assertEqual(self.run.call_count,1);self.assertEqual(e.read(path)['state'],'failed')
        item=e.read(Path(self.instance['work_root'])/'episodes.json')['episodes']['fixture/100']
        self.assertTrue(any(x.startswith('recovered-publication:') for x in e.read(self.path)['handled_events']))
        request['parameters']['config']=str(self.root/'foreign.json');job=e.read(path);job.update(request=request,request_sha256=e.digest(request));e.save(path,job)
        with self.assertRaises(RuntimeError):v.events(item,e.read(self.path))
    def test_failed_render_is_not_hidden_by_a_publication_receipt(self):
        self.job('failed')
        with self.assertRaises(RuntimeError):v.events(self.item,e.read(self.path))
    def test_exact_approval_wakes_and_old_approval_does_not_repeat(self):
        self.once()
        with e.journal(Path(self.instance['work_root'])) as (_,data):
            e.episode(data,'fixture','100')['reviews']={'fixture':dict(state='approved',id='fixture',approval_message_id='d'*64)}
        self.run.return_value='WAITING_FOR_REVIEW';self.once();self.once();self.assertEqual(self.run.call_count,2);self.deliver.assert_not_called()
    def test_paused_and_completed_tasks_stay_idle(self):
        for phase in ('paused','completed','blocked'):
            task=e.read(self.path);task['phase']=phase;e.save(self.path,task);self.once()
        self.run.assert_not_called()
    def test_announcement_policy_is_a_task_choice_independent_of_provider(self):
        self.assertIn('NO announcement',v.instructions(self.path))
        task=e.read(self.path);task['announce']=True;e.save(self.path,task)
        self.assertIn('normal announcement flow',v.instructions(self.path));self.assertNotIn('NO announcement',v.instructions(self.path))
    def test_failure_sends_only_saved_uuid_once_and_stops(self):
        with unittest.mock.patch.object(v.failures,'save_notice',return_value='Report UUID: fixture'):
            self.run.side_effect=ValueError('private detail');self.once();self.once()
        self.assertEqual(self.run.call_count,1);self.assertEqual(self.deliver.call_count,1)
        self.assertEqual(self.deliver.call_args.args[-1],'Report UUID: fixture');self.assertEqual(e.read(self.path)['phase'],'blocked')

if __name__=='__main__':unittest.main()
