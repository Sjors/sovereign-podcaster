"""Authenticated active-turn follow-ups; queued bridge delivery never resubmits them."""
from pathlib import Path
import fcntl
import re
import uuid
import episodes as e

TERMINAL = {'completed', 'failed', 'cancelled'}


def root(config):
    if config.get('followup_steering') is not True or not config.get('marmot_home'):
        return None
    instance = e.read(Path(config['marmot_home'])/'podcaster-instance.json')
    return Path(instance['state_root'])/'steering'


def path_for(directory, incoming):
    return directory/(e.digest({k:incoming[k] for k in ('account','group','sender','message_id')})+'.json')


def consumed(config, incoming, route):
    directory = root(config)
    if directory is None:
        return False
    path = path_for(directory, incoming)
    if not path.exists():
        return False
    value = e.read(path)
    if value['incoming'] != incoming or value['route'] != route:
        raise RuntimeError('Steered message identity or route changed')
    if value['phase'] not in ('accepted', 'completed'):
        raise RuntimeError('Steering submission has an uncertain outcome; inspect before retrying')
    return True


def ordinary(text):
    import episode_routing
    text = text.strip()
    # Explicit commands and exact publication approvals keep their existing handlers.
    return bool(text) and not text.startswith('/') and episode_routing.command(text) is None and not re.fullmatch(
        r'(?i)(?:approve(?: [0-9a-f]{12})?|yes [0-9a-f]{12})', text)


class Followups:
    def __init__(self, config, route, folder, session_id, authenticate, rpc):
        self.config, self.route, self.folder = config, route, Path(folder)
        self.session_id, self.authenticate, self.rpc = session_id, authenticate, rpc
        self.directory = root(config)
        self.since = int((self.folder/'input.json').stat().st_mtime)
        self.original = config.get('incoming_message', {}).get('message_id')
        self.accepted = []
        self.last_scan = 0

    def scan(self, api, active_turn, now):
        if not self.directory or now-self.last_scan < 2:
            return 0
        self.last_scan = now
        response = self.rpc(dict(type='timeline_list', account_id_hex=self.route['account'],
            group_id_hex=self.route['group'], limit=50))
        messages = sorted(response.get('messages', []), key=lambda x:(x['recorded_at'],x['message_id_hex']))
        count = 0
        for message in messages:
            text = message.get('text')
            if (message.get('direction') != 'received' or message.get('availability') != 'available'
                    or message.get('sender', {}).get('account_id_hex') != self.config['trusted_hex']
                    or message.get('recorded_at', 0) < self.since
                    or message.get('message_id_hex') == self.original
                    or message.get('text_truncated') or message.get('media')
                    or not isinstance(text, str) or not ordinary(text)):
                continue
            if text.strip().lower()=='yes' and message.get('reply_to_message_id_hex'):
                # Quoted yes can be an exact publication approval. Only known
                # transcript questions may consume it as active-turn feedback.
                cfg=e.read(self.config['transcription_config']) if self.config.get('transcription_config') else {}
                if not any(message['reply_to_message_id_hex'] in q.get('message_ids',[])
                        for p in Path(cfg.get('feedback_root','/nonexistent')).glob('*.json') for q in [e.read(p)]):
                    continue
            incoming = self.authenticate(message)
            e.private_root(self.directory)
            path = path_for(self.directory, incoming)
            with path.with_suffix('.lock').open('a') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:continue
                count += self.submit(api,active_turn,path,incoming)
        return count

    def submit(self,api,active_turn,path,incoming):
        if path.exists():
            prior = e.read(path)
            if prior['incoming'] != incoming or prior['route'] != self.route:
                raise RuntimeError('Steering identity changed')
            if prior['phase'] not in ('accepted','completed'):
                raise RuntimeError('Earlier steering submission is unresolved; inspect before retrying')
            return 0
        marker = 'Authenticated White Noise follow-up '+incoming['message_id']
        content = marker+'\n'+incoming['text']+'\n\nThis is the user’s newer follow-up in this same conversation. Apply corrections to earlier wording as appropriate. Do not send a second stage-progress message.'
        body = {'events':[{'type':'agent.session.input.message','input':[{'role':'user','content':[{'type':'input_text','text':content}]}]}]}
        value = dict(schema=1,phase='pending',incoming=incoming,route=self.route,
            session_id=self.session_id,owner_folder=str(self.folder),target_turn=active_turn['id'],
            submission=str(uuid.uuid4()),marker=marker,created_at=e.now())
        e.save(path,value)
        # A lost response leaves an immutable uncertain receipt, never another input.
        api.call('sessions/'+self.session_id+'/events',body,value['submission'])
        value.update(phase='accepted',accepted_at=e.now());e.save(path,value)
        if self.config.get('transcription_config'):
            import transcription_feedback
            question=transcription_feedback.receive(e.read(self.config['transcription_config']),incoming)
            if question:
                value['feedback_question']=question['id'];e.save(path,value)
        self.accepted.append(path)
        return 1

    def settled(self, items, turns):
        statuses = {x['id']:x['status'] for x in turns}
        for path in self.accepted:
            value = e.read(path)
            matches = [x for x in items if x.get('type')=='message' and x.get('role')=='user'
                and any(value['marker'] in c.get('text','') for c in x.get('content',[]))]
            if not matches or not any(statuses.get(x.get('turn_id')) in TERMINAL for x in matches):
                return False
        return True


def finish(config, folder, turn_id):
    directory = root(config)
    if directory is None or not directory.exists():
        return
    for path in directory.glob('*.json'):
        value = e.read(path)
        if value.get('owner_folder') == str(folder) and value['phase'] == 'accepted':
            value.update(phase='completed',completed_at=e.now(),result_turn=turn_id);e.save(path,value)
