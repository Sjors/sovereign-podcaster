"""Select transcript lifecycle messages; retain intermediate answers in session state."""
from pathlib import Path
import re
import episodes as e
import failures
import transcription_feedback as feedback


def waiting_question(config, folder):
    """The feedback tool already delivered the prompt; no extra chat reply is needed."""
    folder=Path(folder).resolve()
    return any(q.get('state') in feedback.UNRESOLVED_STATES and Path(q['folder']).resolve()==folder
        for path in Path(config['feedback_root']).glob('*.json') for q in [e.read(path)])


def result(folder, answer):
    """Return a verified final answer or UUID failure; intermediate work stays quiet."""
    folder=Path(folder)
    receipt=folder/'publication/verification.json'
    if receipt.exists():
        publication=e.read(receipt);source=e.read(folder/'episode.json')
        if (publication.get('verified') is not True or
            publication.get('episode_guid')!=source['guid'] or
            publication.get('vtt_sha256')!=e.file_record(folder/'publication/transcript.vtt')['sha256']):
            raise ValueError('Transcript completion receipt differs from its source/artifact')
        return answer
    match=re.search(r'Report UUID: ([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\b',answer)
    if match:return failures.format_notice({'id':match[1]})
    unsaved=failures.format_notice({},stored=False)
    if unsaved in answer:return unsaved
    return None
