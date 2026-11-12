import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('install_wakeups',Path(__file__).with_name('install-wakeups.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InstallTests(unittest.TestCase):
 def test_only_new_service_is_started_and_existing_instance_fields_survive(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);config=root/'transcription.json';m.e.save(config,{})
   instance=root/'instance.json';m.e.save(instance,dict(transcription_config=str(config),preserve='yes'))
   with patch.object(m.Path,'home',return_value=root),patch.object(m.subprocess,'run') as run:m.install(instance)
   commands=[call.args[0] for call in run.call_args_list]
   self.assertEqual(commands[1],['systemctl','--user','enable','--now','sovereign-podcaster-wakeups.service'])
   self.assertFalse(any('restart' in command or 'stop' in command for command in commands))
   self.assertEqual(m.e.read(instance)['preserve'],'yes');self.assertTrue(m.e.read(instance)['transcription_wakeups'])
if __name__=='__main__':unittest.main()
