import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

spec=importlib.util.spec_from_file_location('chapter_queue',Path(__file__).with_name('chapter_queue.py'))
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
e=q.e


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.work=e.private_root(self.base/'work');self.api=e.private_root(self.base/'api')
        self.root=self.base/'queue';self.cfg=self.base/'chapters.json';self.grant=self.base/'grant.json'
        self.instance=dict(chapters_config=str(self.cfg),work_root=str(self.work),state_root=str(self.api),account_id_hex='ab')
        e.save(self.cfg,dict(show='demo',feed='https://example.org/feed',group_id_hex='cd',paused=False,allow_published_source_intake=True))
        e.save(self.grant,dict(source='explicit-maintainer-user-request',incoming=dict(text='Queue all remaining episodes, newest first.'),scope=dict(operation='chapters-backfill',show='demo',feed='https://example.org/feed')))
        root=ET.Element('rss');channel=ET.SubElement(root,'channel')
        for number,day,title in [('1',1,'First'),('2',2,'Second'),(None,3,'Emergency broadcast')]:
            item=ET.SubElement(channel,'item')
            for k,v in [('guid',title),('link','https://example.org/'+(number or 'special')),('title',title),('pubDate',f'Mon, {day:02} Nov 2026 00:00:00 +0000')]:ET.SubElement(item,k).text=v
            if number:ET.SubElement(item,'{http://www.itunes.com/dtds/podcast-1.0.dtd}episode').text=number
            ET.SubElement(item,'enclosure',url='https://example.org/'+title+'.mp3')
        self.feed=ET.tostring(root)
        self.get=patch.object(q.chapters,'get',return_value=(self.feed,{}));self.get.start();self.addCleanup(self.get.stop)
        self.done={}
        self.completion=patch.object(q.chapters,'completion',side_effect=lambda f:self.done.get(str(f)));self.completion.start();self.addCleanup(self.completion.stop)
        self.register=patch.object(q,'register',side_effect=self.registration);self.register.start();self.addCleanup(self.register.stop)
        self.notices=[];self.runs=[]
        self.fail=patch.object(q.failures,'save_notice',return_value='Podcast task needs attention.\nReport UUID: 12345678-1234-4234-8234-123456789abc');self.fail.start();self.addCleanup(self.fail.stop)

    def registration(self,instance,cfg,root,selected):
        folder=self.work/selected['number']
        return dict(directory=str(folder),task=str(folder/'task.json'))

    def model_run(self,instance,cfg,root,path,item):
        self.runs.append(item['number']);self.done[item['registration']['directory']]='Verified '+item['number']
        return 'Untrusted model summary'

    def deliver(self,instance,cfg,path,text):self.notices.append(text)
    def create(self):return q.create(self.instance,self.root,self.grant)
    def once(self,run=None,deliver=None):return q.run_once(self.instance,self.root,run or self.model_run,deliver or self.deliver)

    def test_snapshot_includes_specials_and_orders_by_publication_date(self):
        manifest=self.create()
        self.assertTrue(manifest['selected'][0]['number'].startswith('special-'))
        self.assertEqual([x['number'] for x in manifest['selected'][1:]],['2','1'])
        self.assertIsNone(manifest['selected'][0]['native_number'])
        with self.assertRaisesRegex(ValueError,'already exists'):self.create()

    def test_serial_completion_sends_only_verified_notices_without_replaying(self):
        manifest=self.create()
        for _ in range(4):self.once()
        expected=[x['number'] for x in manifest['selected']]
        self.assertEqual(self.runs,expected)
        self.assertEqual(self.notices,['Verified '+n for n in expected])
        self.assertEqual(e.read(self.root/'state.json')['phase'],'completed')
        self.once();self.assertEqual(self.runs,expected)

    def test_explicit_exclusion_keeps_emergency_out_of_queue(self):
        grant=e.read(self.grant);grant['exclude_guids']=['Emergency broadcast'];e.save(self.grant,grant)
        manifest=self.create()
        self.assertEqual([x['number'] for x in manifest['selected']],['2','1'])
        self.assertEqual([x['guid'] for x in manifest['excluded']],['Emergency broadcast'])

    def test_verified_existing_episode_is_skipped_but_unresolved_work_is_rejected(self):
        folder=e.private_root(self.work/'existing');e.save(folder/'episode.json',dict(guid='First'))
        e.save(self.work/'episodes.json',dict(episodes={'demo/1':dict(chapters=dict(directory=str(folder)))}))
        self.done[str(folder)]='Verified first'
        manifest=self.create();self.assertEqual(manifest['skipped'],['1'])
        self.assertNotIn('1',[x['number'] for x in manifest['selected']])

    @patch.object(q.subprocess,'run')
    def test_installer_preserves_other_units_and_rejects_replacement(self,run):
        self.create();instance=self.base/'instance.json';e.save(instance,self.instance)
        with patch.object(q.Path,'home',return_value=self.base/'home'):
            unit=q.install(instance,self.root)
            self.assertIn('--queue',unit.read_text())
            self.assertEqual(run.call_args_list[-1].args[0],['systemctl','--user','enable','--now','sovereign-podcaster-chapters.service'])
            unit.write_text('Existing unrelated definition')
            with self.assertRaisesRegex(ValueError,'Existing chapter service differs'):q.install(instance,self.root)

    def test_uncertain_attempt_blocks_without_model_or_next_episode(self):
        manifest=self.create();number=manifest['selected'][0]['number']
        e.save(self.root/'items'/(number+'.json'),dict(number=number,phase='running'))
        self.assertEqual(self.once()['phase'],'blocked');self.once()
        self.assertEqual(self.runs,[]);self.assertEqual(len(self.notices),1)
        self.assertIn('Report UUID:',self.notices[0])

    def test_inspected_continuation_uses_new_submission_without_registering_again(self):
        manifest=self.create();selected=manifest['selected'][0];number=selected['number']
        registration=self.registration(self.instance,{},self.root,selected)
        item=dict(number=number,phase='continuation-approved',registration=registration,
            handle='saved-session',submission='new-inspected-continuation',prompt='Continue the inspected task')
        proof=self.root/'recovery.json'
        e.save(proof,dict(submission=item['submission'],handle=item['handle'],task=registration['task'],
            prompt_sha256=q.hashlib.sha256(item['prompt'].encode()).hexdigest()))
        item['recovery']=dict(path=str(proof),sha256=q.chapters.sha(proof));e.save(self.root/'items'/(number+'.json'),item)
        with patch.object(q,'register',side_effect=AssertionError('Must reuse the registered task')):
            self.assertEqual(self.once()['phase'],'delivered')
        self.assertEqual(self.runs,[number])
        self.assertEqual(e.read(self.root/'state.json')['completed'],[number])

    def test_changed_continuation_proof_does_not_resubmit(self):
        manifest=self.create();number=manifest['selected'][0]['number'];proof=self.root/'recovery.json';e.save(proof,{})
        item=dict(number=number,phase='continuation-approved',recovery=dict(path=str(proof),sha256='wrong'))
        e.save(self.root/'items'/(number+'.json'),item)
        self.assertEqual(self.once()['phase'],'blocked');self.assertEqual(self.runs,[])

    def test_model_claim_without_receipt_blocks_remaining_queue(self):
        self.create();run=Mock(return_value='Successfully published!')
        self.assertEqual(self.once(run=run)['phase'],'blocked');self.once(run=run)
        self.assertEqual(run.call_count,1);self.assertNotIn('Successfully',self.notices[0])

    def test_delivery_failure_preserves_verified_result_and_blocks_next(self):
        manifest=self.create();deliver=Mock(side_effect=RuntimeError('Uncertain send'))
        with self.assertRaises(RuntimeError):self.once(deliver=deliver)
        self.assertEqual(e.read(self.root/'state.json')['phase'],'blocked')
        self.assertEqual(e.read(self.root/'items'/(manifest['selected'][0]['number']+'.json'))['phase'],'verified')
        self.once();self.assertEqual(len(self.runs),1)

    def test_pause_and_active_work_leave_queue_idle(self):
        self.create();e.save(self.root/'control.json',dict(paused=True));self.assertTrue(self.once()['paused'])
        e.save(self.root/'control.json',dict(paused=False));e.save(self.api/'work.active.json',{})
        self.assertTrue(self.once()['busy']);self.assertEqual(self.runs,[])

    def test_changed_grant_or_destination_stops_before_work(self):
        self.create();e.save(self.grant,dict())
        e.save(self.root/'authorization.json',dict(incoming='changed'))
        with self.assertRaisesRegex(ValueError,'authorization'):self.once()
        self.assertEqual(self.runs,[])


if __name__=='__main__':unittest.main()
