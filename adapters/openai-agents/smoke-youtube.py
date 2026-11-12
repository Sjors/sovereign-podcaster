#!/usr/bin/env python3
"""Run one budgeted Agents API task under the isolated user: YouTube identity check."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def private_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise RuntimeError('Private input must be an owner-owned regular file with mode 0600')
        return f.read()


def save(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(value, f, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class API:
    def __init__(self, key, project):
        self.key, self.project = key, project
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))

    def open(self, path, body=None, submission=None, stream=False):
        headers = {'Authorization': 'Bearer ' + self.key, 'OpenAI-Project': self.project,
                   'OpenAI-Beta': 'agents=v1', 'Content-Type': 'application/json'}
        if submission: headers['Idempotency-Key'] = submission
        if stream: headers['Accept'] = 'text/event-stream'
        request = urllib.request.Request('https://api.openai.com/v1/agents/' + path,
                                         data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            return self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            request_id = re.sub(r'[^a-zA-Z0-9_-]', '', error.headers.get('x-request-id', ''))[:100]
            try:
                detail = json.loads(error.read()).get('error', {})
                scopes = sorted(set(re.findall(r'api\.[a-zA-Z_.]+', str(detail.get('message', '')))))
                code = re.sub(r'[^a-zA-Z0-9_.-]', '', str(detail.get('code', '')))[:100]
                message = str(detail.get('message', '')).replace(self.key, '[redacted-key]')
                message = re.sub(r'sk-[A-Za-z0-9_-]{6,}', '[redacted-key]', message)[:600]
            except Exception: scopes, code, message = [], '', ''
            raise RuntimeError(f'API HTTP {error.code}; request_id={request_id}; code={code}; scopes={scopes}; {message}') from None

    def call(self, path, body=None, submission=None):
        with self.open(path, body, submission) as response:
            payload = response.read()
            # Event submission/cancellation may acknowledge success without JSON.
            # Treat that acknowledgement as success instead of cancelling the task.
            if not payload.strip() and response.status in (202, 204):
                return None
            return json.loads(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--max-cents', type=int, default=50)
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--without-server-spend-limit', action='store_true',
                        help='Explicit compatibility fallback: timeout only, no server dollar cap')
    parser.add_argument('--resume-run', type=Path,
                        help='Reuse a saved session when no input was submitted yet')
    args = parser.parse_args()
    if not 1 <= args.max_cents <= 100 or not 30 <= args.timeout <= 600:
        parser.error('Smoke-test limits: 1–100 cents and 30–600 seconds')
    os.umask(0o077)
    home = Path.home()
    config = home / '.config/sovereign-podcaster'
    keys = config / 'openai'
    app = private_read(keys / 'application.key').strip()
    environment = private_read(keys / 'environment.key').strip()
    if not app or not environment or app == environment:
        raise RuntimeError('Two distinct nonempty credentials are required')
    instance = json.loads(private_read(config / 'youtube.json'))
    command = [instance['python'], instance['helper'], 'check', '--config-dir',
               instance['config_dir'], '--channel-id', instance['channel_id']]
    workspace = home / '.local/share/sovereign-podcaster/agent-work'
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    runs = home / '.local/share/sovereign-podcaster/agents'
    runs.mkdir(parents=True, exist_ok=True, mode=0o700)
    run = args.resume_run if args.resume_run else Path(tempfile.mkdtemp(prefix='youtube-check-', dir=runs))
    if args.resume_run and (run.is_symlink() or run.stat().st_uid != os.getuid()):
        raise RuntimeError('Resume requires an owned run directory')
    api = API(app, args.project_id)
    instructions = ('Perform only the supplied read-only YouTube identity-check task. '
                    'Run the exact supplied command once; do not inspect credential files, '
                    'print environment variables, alter source, install software, or call '
                    'YouTube mutations. Do not publish, upload, or delegate. The helper '
                    'manages its local token privately. Report its JSON result and exit status.')
    request = {'agent': {'model': args.model, 'instructions': instructions,
                         'reasoning': {'effort': 'low'}, 'multi_agent': {'enabled': False}},
               'environment': {'type': 'self_hosted', 'workspace_directory': str(workspace)},
               'metadata': {'workflow': 'sovereign-podcaster-youtube-check'}}
    if not args.without_server_spend_limit:
        request['spend_control'] = {'limit': args.max_cents}
    create_key, input_key = str(uuid.uuid4()), str(uuid.uuid4())
    print('Run directory: ' + str(run), flush=True)
    if args.resume_run:
        previous_request = json.loads(private_read(run / 'request.json'))
        if previous_request != request:
            raise RuntimeError('Resume configuration differs from the saved request')
        previous_session = json.loads(private_read(run / 'session.json'))
        input_key = json.loads(private_read(run / 'submissions.json'))['input']
        session = api.call('sessions/' + previous_session['id'])
        previous_turns = api.call('sessions/' + previous_session['id'] + '/turns?limit=100&order=desc')
        if previous_turns.get('data'):
            save(run / 'turns.json', previous_turns)
            raise RuntimeError('Session already has turns; inspect saved work instead of resubmitting input')
    else:
        save(run / 'request.json', request)
        save(run / 'submissions.json', {'create': create_key, 'input': input_key})
        session = api.call('sessions', request, create_key)
    save(run / 'session.json', session)
    session_id = session['id']
    print('Session ready: ' + session_id, flush=True)
    if not args.without_server_spend_limit and session.get('spend_control', {}).get('limit') != args.max_cents:
        raise RuntimeError('API did not confirm the requested session spending limit; no task submitted')
    env = session['environment']
    parsed = urllib.parse.urlsplit(env['remote_url'])
    if parsed.scheme != 'https' or parsed.hostname != 'api.openai.com':
        raise RuntimeError('Unexpected executor registration endpoint; no executor started')
    codex_home = home / '.local/share/sovereign-podcaster/codex'
    codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    child_env = {'HOME': str(home), 'USER': os.environ['USER'], 'LOGNAME': os.environ['USER'],
                 'PATH': str(home / '.local/bin') + ':/usr/bin:/bin', 'SHELL': '/bin/bash',
                 'CODEX_HOME': str(codex_home),
                 'CODEX_API_KEY': environment, 'RUST_LOG': 'warn'}
    # Only the restricted key enters the executor environment, never application.key.
    child = None
    executor_lines = []

    def clean(text):
        return re.sub(r'sk-[A-Za-z0-9_-]{6,}', '[redacted-key]', text.replace(app, '[redacted-key]').replace(environment, '[redacted-key]'))

    def drain():
        for line in child.stdout:
            executor_lines.append(clean(line.rstrip()))

    events, stream_ready, stream_stop = [], threading.Event(), threading.Event()
    previously_connected = (args.resume_run and (run / 'event-types.json').exists()
                            and 'agent.session.environment.connected' in json.loads(private_read(run / 'event-types.json')))

    def follow():
        try:
            with api.open('sessions/' + session_id + '/events?stream=true', stream=True) as response:
                stream_ready.set()
                for line in response:
                    if stream_stop.is_set(): break
                    text = line.decode().strip()
                    kind = None
                    if text.startswith('event:'): kind = text[6:].strip()
                    elif text.startswith('data:'):
                        try: kind = json.loads(text[5:].strip()).get('type')
                        except (ValueError, AttributeError): pass
                    if kind and (not events or events[-1] != kind):
                        events.append(kind)
                        if 'delta' not in kind: print('Event: ' + kind, flush=True)
        except Exception as error:
            events.append('stream-ended:' + type(error).__name__)
            stream_ready.set()

    finished = False
    try:
        threading.Thread(target=follow, daemon=True).start()
        stream_ready.wait(15)
        child = subprocess.Popen([str(home / '.local/bin/codex'), 'exec-server', '--remote',
                                  env['remote_url'], '--environment-id', env['id']],
                                 env=child_env, cwd=workspace, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, start_new_session=True)
        threading.Thread(target=drain, daemon=True).start()
        connection_deadline = time.monotonic() + (2 if previously_connected else 30)
        while 'agent.session.environment.connected' not in events:
            if child.poll() is not None:
                raise RuntimeError('Executor exited before connection with code ' + str(child.returncode))
            if time.monotonic() > connection_deadline:
                if previously_connected:
                    print('Executor running for a previously verified environment; requesting continuation', flush=True)
                    break
                raise RuntimeError('Executor connection deadline exceeded; no task submitted')
            time.sleep(0.25)
        print('Submitting the one read-only task', flush=True)
        message = {'events': [{'type': 'agent.session.input.message', 'input': [
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Run exactly this command and report its JSON and exit status:\n' + shlex.join(command)}]}]}]}
        save(run / 'input.json', message)
        api.call('sessions/' + session_id + '/events', message, input_key)
        deadline, last = time.monotonic() + args.timeout, None
        while time.monotonic() < deadline:
            session = api.call('sessions/' + session_id)
            turns = api.call('sessions/' + session_id + '/turns?limit=100&order=desc')
            save(run / 'session.json', session); save(run / 'turns.json', turns)
            roots = [t for t in turns.get('data', []) if not t.get('subagent_id')]
            turn = roots[0] if roots else {}
            current = (session.get('status'), turn.get('status'))
            if current != last:
                print('Status: ' + str(current), flush=True); last = current
            if turn.get('status') in ('completed', 'failed', 'cancelled'):
                finished = True
                items = api.call('sessions/' + session_id + '/items?order=asc&limit=100')
                save(run / 'items.json', json.loads(clean(json.dumps(items))))
                result = {'session_id': session_id, 'turn_status': turn['status'], 'model': args.model,
                          'usage': session.get('usage'), 'spend_control': session.get('spend_control'),
                          'turn_id': turn.get('id'), 'turn_usage': turn.get('usage'),
                          'server_spending_limit_requested': not args.without_server_spend_limit,
                          'executor_uid': os.getuid(), 'youtube_content_mutations_authorized': False,
                          'tool_result_review_required': True}
                save(run / 'result.json', result)
                print(json.dumps(result, indent=2), flush=True)
                if turn['status'] != 'completed': raise RuntimeError('Agent turn did not complete successfully')
                return
            if session.get('status') == 'failed': raise RuntimeError('Agent session failed')
            if child.poll() is not None: raise RuntimeError('Executor exited with code ' + str(child.returncode))
            time.sleep(2)
        raise RuntimeError('Smoke-test deadline exceeded')
    finally:
        failure = sys.exc_info()[1]
        if failure is not None:
            save(run / 'failure.json', {'type': type(failure).__name__,
                                       'message': clean(str(failure)) if isinstance(failure, RuntimeError)
                                       else 'Details suppressed; inspect saved session and tool history'})
        if not finished:
            try: api.call('sessions/' + session_id + '/events', {'events': [{'type': 'agent.session.input.cancel'}]})
            except Exception: pass
        stream_stop.set()
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
        save(run / 'executor-log.json', executor_lines)
        if previously_connected and 'agent.session.environment.connected' not in events:
            events.insert(0, 'agent.session.environment.connected')
        save(run / 'event-types.json', events)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        if isinstance(error, RuntimeError): print(str(error), flush=True)
        else: print('Smoke test failed (' + type(error).__name__ + '); details suppressed.', flush=True)
        raise SystemExit(1)
