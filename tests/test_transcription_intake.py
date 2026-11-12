import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import transcription_intake as intake
class IntakeTests(unittest.TestCase):
 def test_only_selected_cleared_episode_enrolled_and_retry_reuses_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);root.chmod(0o700);state=root/'state';work=root/'work';cfgpath=root/'config.json';catalog=root/'catalog.json'
   ep=dict(number='15',guid='guid',final_audio_sha256='a'*64)
   e.save(catalog,dict(show='demo',episodes={'15':dict(episode=ep,clearance=dict(audit_complete=True,final_audio_sha256='a'*64))}))
   e.save(cfgpath,dict(paused=False,show='demo',group_id_hex='b'*32,source_catalog=str(catalog),episodes={}))
   config=dict(state_root=str(state),work_root=str(work),transcription_config=str(cfgpath))
   route=dict(account='a'*64,group='b'*32,sender='c'*64,message_id='d'*64);binding=dict(account=route['account'],group=route['group'],cwd=str(root))
   incoming=dict(route,text='Transcribe episode15 and publish its transcript',recorded_at=1,reply_to=None)
   e.private_root(state/'inbox');e.private_root(state/'routing')
   request=state/'inbox'/(hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()+'.json');e.save(request,dict(incoming=incoming,route=binding))
   routing=state/'routing'/(hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()+'.json');e.save(routing,dict(binding=binding,selected='demo/15'))
   with e.journal(work) as (w,d):e.initialize(w,d,'demo','15')
   env={k:v for k,v in zip(['MARMOT_ACCOUNT_ID_HEX','MARMOT_GROUP_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX','MARMOT_MESSAGE_ID_HEX'],route.values())}
   authenticate=lambda *_:incoming
   result=intake.enroll(config,'demo','15',env,authenticate)
   self.assertEqual(set(e.read(cfgpath)['episodes']),{'guid'});self.assertFalse(Path(result['directory']).exists())
   self.assertEqual(intake.enroll(config,'demo','15',env,authenticate),result)
   with self.assertRaises(ValueError):intake.enroll(config,'demo','14',env,authenticate)
   e.save(cfgpath,dict(e.read(cfgpath),paused=True))
   with self.assertRaises(ValueError):intake.enroll(config,'demo','15',env,authenticate)
if __name__=='__main__':unittest.main()
