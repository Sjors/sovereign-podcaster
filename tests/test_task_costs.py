import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import task_costs as c


class CostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'costs'
        self.context=dict(root=str(self.root),session_id='session',model='synthetic',baseline_turn_ids=['earlier'],pricing=dict(input='2',cached_input='0.5',output='8',source='fixture',checked_at='2026-11-02'))

    def turn(self,identifier='one',usage=True):
        return dict(id=identifier,status='completed',usage=dict(input_tokens=1000000,input_tokens_details=dict(cached_tokens=200000),output_tokens=50000) if usage else None)

    def test_multiple_turns_replays_and_finish_include_last_turn(self):
        c.begin(self.context,'episode18','transcript')
        self.assertIsNone(c.observe(self.root,'session',[self.turn('earlier'),self.turn()]))
        c.observe(self.root,'session',[self.turn()])
        c.finish(self.context,'episode18')
        notice=c.observe(self.root,'session',[self.turn(),self.turn('two')])
        v=e.read(self.root/'episode18.json')
        self.assertEqual(v['summary']['estimated_model_usd'],'4.2')
        self.assertEqual(v['summary']['turns'],2);self.assertEqual(notice,'Estimated model cost: US$4.20.')
        self.assertFalse((self.root/'active.json').exists())
        self.assertEqual(os.stat(self.root/'episode18.json').st_mode & 0o777,0o600)

    def test_missing_and_late_usage_stays_unknown_until_refresh(self):
        c.begin(self.context,'t','video');c.finish(self.context,'t')
        self.assertIn('Partial',c.observe(self.root,'session',[self.turn(usage=False)]))
        p=self.root/'t.json';self.assertFalse(e.read(p)['summary']['complete'])
        v=c.refresh(p,'session',[self.turn(),self.turn('unrelated')])
        self.assertTrue(v['summary']['complete']);self.assertEqual(v['summary']['turns'],1)

    def test_missing_cache_detail_is_unknown_not_free(self):
        v=c.begin(self.context,'t','transcript');t=self.turn();del t['usage']['input_tokens_details']
        c.observe(self.root,'session',[t]);self.assertEqual(e.read(self.root/'t.json')['summary']['missing_usage_turn_ids'],['one'])

    def test_no_price_no_fabricated_amount(self):
        self.context['pricing']=None;c.begin(self.context,'t','video');c.finish(self.context,'t')
        self.assertIn('unavailable',c.observe(self.root,'session',[self.turn()]))

    def test_scope_guards_and_failed_work(self):
        with self.assertRaises(ValueError):c.begin(self.context,'active','video')
        c.begin(self.context,'t','video')
        with self.assertRaises(ValueError):c.begin(self.context,'other','video')
        with self.assertRaises(ValueError):c.observe(self.root,'wrong',[self.turn()])
        t=self.turn();t['status']='cancelled';c.finish(self.context,'t')
        c.observe(self.root,'session',[t],close=False)
        self.assertEqual(e.read(self.root/'t.json')['state'],'closing')
        self.assertEqual(e.read(self.root/'t.json')['summary']['turns'],1)
        with self.assertRaises(ValueError):c.finish(self.context,'../bad')

if __name__=='__main__':unittest.main()
