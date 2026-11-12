"""Lifecycle gating uses saved publication evidence, never model prose alone."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import episodes as e
import transcription_notices as notices

class NoticeTests(unittest.TestCase):
 def test_waiting_question_already_supplies_its_own_chat_prompt(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'episode';config=dict(feedback_root=str(root/'questions'))
   self.assertFalse(notices.waiting_question(config,folder))
   e.private_root(root/'questions');e.save(root/'questions/one.json',dict(state='waiting',folder=str(folder)))
   self.assertTrue(notices.waiting_question(config,folder))
   self.assertFalse(notices.waiting_question(config,root/'other'))
   e.save(root/'questions/one.json',dict(state='reply-received',folder=str(folder)))
   self.assertTrue(notices.waiting_question(config,folder))
   e.save(root/'questions/one.json',dict(state='answered',folder=str(folder)))
   self.assertFalse(notices.waiting_question(config,folder))

 def test_publication_claim_is_silent_until_matching_verified_artifact_exists(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);answer='Published. Estimated model cost: $0.02.'
   self.assertIsNone(notices.result(folder,answer))
   e.save(folder/'episode.json',dict(guid='selected'));e.private_root(folder/'publication');(folder/'publication/transcript.vtt').write_text('WEBVTT\n')
   receipt=dict(verified=True,episode_guid='selected',vtt_sha256=e.file_record(folder/'publication/transcript.vtt')['sha256']);e.save(folder/'publication/verification.json',receipt)
   self.assertEqual(notices.result(folder,answer),answer)
   e.save(folder/'publication/verification.json',dict(receipt,episode_guid='other'))
   with self.assertRaises(ValueError):notices.result(folder,answer)
   e.save(folder/'publication/verification.json',receipt);(folder/'publication/transcript.vtt').write_text('changed')
   with self.assertRaises(ValueError):notices.result(folder,answer)

if __name__=='__main__':unittest.main()
