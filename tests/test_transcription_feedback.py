"""Conversation replies require semantic review; transport receipt is not an answer."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import transcription_feedback as f


class FeedbackConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'q.json'
        self.cfg=dict(feedback_root=str(self.root),account_id_hex='a'*64,group_id_hex='b'*32,trusted_hex='c'*64,episodes={'guid':{}})
        self.q=dict(id='question',state='waiting',episode_guid='guid',account='a'*64,group='b'*32,trusted_sender='c'*64,
            sent_at='2026-01-01T00:00:00+00:00',deadline='2026-01-01T00:15:00+00:00',message_ids=['d'*64])
        e.save(self.path,self.q)
        self.incoming=dict(account='a'*64,group='b'*32,sender='c'*64,message_id='1'*64,recorded_at=1800000000,reply_to=None,text='Can you give me the minute before this?')
        self.message=dict(direction='sent',availability='available',sender={'account_id_hex':'a'*64},message_id_hex='d'*64,reactions_truncated=False)
        self.reaction=dict(actor={'account_id_hex':'c'*64},emoji='👍',reaction_message_id_hex='e'*64,reacted_at=1800000010)

    def test_any_text_requires_interpretation_before_answering(self):
        for text in ['Can you give me the minute before this?', 'What comes before that?', 'A longer clip, please.', 'Yes, that is right.', 'No, I said four.']:
            with self.subTest(text=text):
                e.save(self.path,self.q)
                self.assertEqual(f.receive(self.cfg,dict(self.incoming,text=text))['state'],'reply-received')
                with self.assertRaises(ValueError):f.require_for_publication(self.cfg,dict(guid='guid'))

    def test_context_classification_keeps_question_open_and_does_not_replay_request(self):
        f.receive(self.cfg,self.incoming)
        q=f.classify(self.cfg,'question','1'*64,'context')
        self.assertEqual(q['state'],'waiting');self.assertIsNone(q['deadline'])
        self.assertEqual(f.classify(self.cfg,'question','1'*64,'context'),q)
        self.assertEqual(f.receive(self.cfg,self.incoming)['state'],'waiting')
        with self.assertRaises(ValueError):f.require_for_publication(self.cfg,dict(guid='guid'))
        self.assertEqual(f.receive_reaction(self.cfg,self.message,self.reaction)['state'],'answered')
        self.assertEqual(len(f.require_for_publication(self.cfg,dict(guid='guid'))),1)

    def test_later_text_answer_replaces_context_request_and_retains_history(self):
        f.receive(self.cfg,self.incoming);f.classify(self.cfg,'question','1'*64,'context')
        answer=dict(self.incoming,message_id='2'*64,recorded_at=1800000020,text='Yes, that is what I said.')
        self.assertEqual(f.receive(self.cfg,answer)['state'],'reply-received')
        q=f.classify(self.cfg,'question','2'*64,'answer')
        self.assertEqual(q['state'],'answered');self.assertEqual(q['reply'],answer);self.assertIn(self.incoming,q['reply_history'])
        f.receive(self.cfg,self.incoming)
        self.assertEqual(e.read(self.path)['reply'],answer)

    def test_classification_is_bound_to_current_reply_route_and_disposition(self):
        f.receive(self.cfg,self.incoming)
        with self.assertRaises(ValueError):f.classify(self.cfg,'question','2'*64,'answer')
        with self.assertRaises(ValueError):f.classify(dict(self.cfg,trusted_hex='f'*64),'question','1'*64,'answer')
        f.classify(self.cfg,'question','1'*64,'context')
        with self.assertRaises(ValueError):f.classify(self.cfg,'question','1'*64,'answer')
        f.receive_reaction(self.cfg,self.message,self.reaction)
        with self.assertRaises(ValueError):f.classify(self.cfg,'question','1'*64,'answer')

    def test_poll_checks_original_reaction_while_text_is_unclassified(self):
        f.receive(self.cfg,self.incoming)
        def rpc(socket,request,timeout):
            if request['type']=='timeline_list':
                return dict(messages=[dict(direction='received',availability='available',sender={'account_id_hex':'c'*64},text=self.incoming['text'],message_id_hex='1'*64,recorded_at=1800000000)])
            return dict(account_id_hex='a'*64,group_id_hex='b'*32,message_id_hex='d'*64,message=dict(self.message,reactions=[self.reaction]))
        with patch.object(f,'control') as control:
            control.return_value.rpc.side_effect=rpc
            self.cfg['marmot_home']=str(self.root/'marmot')
            self.assertEqual(f.poll(self.cfg)[0]['state'],'answered')
            self.assertEqual(f.poll(self.cfg)[0]['reply']['message_id'],'e'*64)

    def test_pending_context_request_does_not_expire_as_minor_wording(self):
        f.receive(self.cfg,self.incoming)
        with patch.object(f,'control') as control:
            control.return_value.rpc.side_effect=lambda socket,request,timeout: (dict(messages=[]) if request['type']=='timeline_list' else dict(account_id_hex='a'*64,group_id_hex='b'*32,message_id_hex='d'*64,message=dict(self.message,reactions=[])))
            self.cfg['marmot_home']=str(self.root/'marmot')
            self.assertEqual(f.poll(self.cfg)[0]['state'],'reply-received')


if __name__=='__main__':unittest.main()
