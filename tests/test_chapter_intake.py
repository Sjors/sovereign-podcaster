import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import chapter_intake as intake
import episodes as e


class ChapterIntakeTests(unittest.TestCase):
    def test_authenticated_selection_registers_only_one_source_and_reuses_it(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root=Path(tmp);state=e.private_root(root/'state');work=root/'work';cfgpath=root/'chapters.json';catalog=root/'catalog.json'
            episode=dict(number='15',guid='fixture',final_audio_sha256='a'*64)
            e.save(catalog,dict(show='demo',episodes={'15':dict(episode=episode,clearance=dict(audit_complete=True,final_audio_sha256='a'*64))}))
            cfg=dict(paused=False,show='demo',group_id_hex='b'*32,source_catalog=str(catalog),feed='https://example.org/feed.xml')
            e.save(cfgpath,cfg);instance=dict(state_root=str(state),work_root=str(work),chapters_config=str(cfgpath))
            route=dict(account='a'*64,group='b'*32,sender='c'*64,message_id='d'*64)
            binding=dict(account=route['account'],group=route['group'],cwd=str(root))
            incoming=dict(route,text='chapters demo 15',recorded_at=1,reply_to=None)
            e.private_root(state/'inbox');e.private_root(state/'routing')
            request=state/'inbox'/(hashlib.sha256(json.dumps(route,sort_keys=True).encode()).hexdigest()+'.json')
            e.save(request,dict(incoming=incoming,route=binding))
            routing=state/'routing'/(hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()+'.json')
            e.save(routing,dict(binding=binding,selected='demo/15'))
            with e.journal(work) as (w,data):e.initialize(w,data,'demo','15')
            env=dict(zip(['MARMOT_ACCOUNT_ID_HEX','MARMOT_GROUP_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX','MARMOT_MESSAGE_ID_HEX'],route.values()))
            authenticate=lambda *_:incoming
            result=intake.enroll(instance,'demo','15',env,authenticate)
            self.assertEqual(intake.enroll(instance,'demo','15',env,authenticate),result)
            self.assertEqual(e.read(result['task'])['source']['episode'],episode)
            self.assertEqual(e.read(cfgpath),cfg)  # Intake does not relax controls or enroll other episodes.
            with self.assertRaises(ValueError):intake.enroll(instance,'demo','14',env,authenticate)
            with self.assertRaisesRegex(ValueError,'authenticated'):
                intake.enroll(instance,'demo','15',env,lambda *_:dict(incoming,text='forged'))
            e.save(cfgpath,dict(cfg,paused=True))
            with self.assertRaisesRegex(ValueError,'paused'):intake.enroll(instance,'demo','15',env,authenticate)


if __name__=='__main__':unittest.main()
