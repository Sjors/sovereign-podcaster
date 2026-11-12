import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('reconcile',Path(__file__).with_name('reconcile.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class ReconcileTests(unittest.TestCase):
 def test_active_work_blocks_and_cancelled_input_is_never_replayed(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'turn-one';folder.mkdir();(root/'cursors').mkdir();keys=root/'keys';keys.mkdir()
   for name in ['application.key','environment.key']:(keys/name).write_text('synthetic-'+name)
   save=r.b.transport.save;marker=root/'route.active.json';cursor=root/'cursors/handle.json'
   save(marker,dict(handle='handle',folder=str(folder),session_id='session'))
   save(cursor,dict(session_id='session',requests={'input':dict(phase='pending',folder=str(folder),baseline_turn_ids=['old'])}))
   cfg=dict(state_root=str(root),openai_key_directory=str(keys));api=Mock()
   with patch.object(r.b,'paged',return_value=[dict(id='new',status='in_progress')]):
    with self.assertRaisesRegex(ValueError,'active work'):r.reconcile(cfg,root,api,True)
   self.assertTrue(marker.exists())
   turns=[dict(id='old',status='completed'),dict(id='new',status='cancelled',usage={'input_tokens':12})]
   with patch.object(r.b,'paged',side_effect=[turns,[]]):result=r.reconcile(cfg,root,api,True)
   self.assertFalse(marker.exists());self.assertEqual(result['status'],'cancelled')
   self.assertEqual(json.loads(cursor.read_text())['requests']['input']['phase'],'cancelled')
   api.call.assert_not_called()
if __name__=='__main__':unittest.main()
