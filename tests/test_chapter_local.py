import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import chapter_local as c
import episodes as e


class LocalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.auth=self.root/'authorization.json'
        e.save(self.auth,dict(source='explicit-maintainer-user-request',api_queue_paused=True,marmot_notifications=False,
            completed_numbers=['3'],remaining_numbers=['2','1']))
        e.save(self.root/'control.json',dict(paused=True));e.save(self.root/'manifest.json',{})
        self.cfg=dict(config_path='/fixture/config');self.manifest=dict(show='fixture',selected=[dict(number=n,guid=n) for n in ('3','2','1')])
        self.mock=patch.object(c.queue,'checked',return_value=(self.cfg,self.manifest,dict(completed=['3'])))
        self.mock.start();self.addCleanup(self.mock.stop)

    def test_next_is_local_and_requires_paused_api_queue(self):
        with patch.object(c.queue,'register') as register:
            self.assertEqual(c.operate({},self.root,self.auth,'next')['next'],'2');register.assert_not_called()
        e.save(self.root/'control.json',dict(paused=False))
        with self.assertRaisesRegex(ValueError,'paused API'):c.operate({},self.root,self.auth,'next')

    def test_out_of_order_prepare_does_not_register_or_publish(self):
        with patch.object(c.queue,'register') as register:
            with self.assertRaisesRegex(ValueError,'next explicitly'):c.operate({},self.root,self.auth,'prepare','1')
            register.assert_not_called()

    def test_altered_selection_and_notification_intent_fail_closed(self):
        for changes in (dict(remaining_numbers=['1','2']),dict(marmot_notifications=True)):
            original=e.read(self.auth);e.save(self.auth,original|changes)
            with self.assertRaises(ValueError):c.operate({},self.root,self.auth,'next')
            e.save(self.auth,original)

    def test_changed_progress_binding_cannot_advance(self):
        e.save(self.root/'local-progress.json',dict(binding={},completed={'2':{}}))
        with self.assertRaisesRegex(ValueError,'authorization changed'):c.operate({},self.root,self.auth,'next')

    def test_only_verified_selected_completion_advances_without_notifications(self):
        work=e.private_root(self.root/'work')
        with e.journal(work) as (root,data):
            item=e.initialize(root,data,'fixture','2');folder=e.private_root(Path(item['directory'])/'chapters')
            item['chapters']=dict(directory=str(folder),task=str(folder/'task.json'))
        e.save(folder/'episode.json',dict(guid='2'));e.save(folder/'transport.json',dict(phase='verified'))
        e.save(folder/'verification.json',dict(verified=True))
        instance=dict(work_root=str(work))
        with patch.object(c.chapters,'completion',return_value=None):
            with self.assertRaisesRegex(ValueError,'publicly verified'):c.operate(instance,self.root,self.auth,'record','2')
        self.assertFalse((self.root/'local-progress.json').exists())
        with patch.object(c.chapters,'completion',return_value='Verified episode 2'):
            result=c.operate(instance,self.root,self.auth,'record','2')
        self.assertFalse(result['notifications']);self.assertEqual(result['remaining'],1)
        self.assertEqual(c.operate(instance,self.root,self.auth,'next')['next'],'1')


if __name__=='__main__':unittest.main()
