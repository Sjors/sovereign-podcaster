#!/usr/bin/env python3
"""Delegate installation to pinned upstream tooling; pair one explicit trusted npub."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0,str(REPO/'tools'))
sys.path.insert(0,str(HERE.parent/'openai-agents'))
import providers
from runtime_limits import HARNESS_TIMEOUT_SECONDS
LOCK = json.loads((HERE/'release.json').read_text())


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        from urllib.parse import urlsplit
        target=urlsplit(newurl)
        if target.scheme!='https' or target.username is not None:raise RuntimeError('Refusing unsafe installer redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, 'w') as f:
        os.fchmod(f.fileno(), 0o600); json.dump(value, f, indent=2); f.write('\n')
        f.flush(); os.fsync(f.fileno())
    os.replace(temporary, path)


def private_input(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        s=os.fstat(stream.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o600:
            raise ValueError('Private provider input must be owned by this user with mode 0600')
        return stream.read()


def workspace_alias():
    """Keep the checkout name portable while making the phone command short."""
    alias=Path.home()/'src/podcast'
    alias.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if alias.is_symlink() or alias.exists():
        if alias.resolve()!=REPO.resolve():
            raise RuntimeError('~/src/podcast already points elsewhere; preserve it and inspect before setup')
    else:
        alias.symlink_to(REPO,target_is_directory=True)
    return alias


def skill_links():
    root=Path.home()/'.local/share/sovereign-podcaster/codex/skills'
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in ('podcast-transcription','video-production','marmot-whitenoise','nostr-publishing','fetch-nostr-events','youtube-publishing','castopod-publishing','castopod-maintenance'):
        source=REPO/'skills'/name
        link=root/name
        if link.is_symlink() or link.exists():
            if link.resolve()!=source.resolve():
                raise RuntimeError('Existing skill path differs; preserve it and inspect before setup: '+name)
        else:link.symlink_to(source,target_is_directory=True)


def enable_chat_media(home, env):
    """Allow only the private chat staging directory, never a project/home tree."""
    staging=home/'media-uploads';staging.mkdir(mode=0o700,exist_ok=True)
    if staging.is_symlink() or staging.stat().st_uid!=os.getuid() or stat.S_IMODE(staging.stat().st_mode)!=0o700:
        raise RuntimeError('Media staging must be an owned private real directory')
    units=Path.home()/'.config/systemd/user'
    unit=units/'sovereign-podcaster-marmot.service'
    commands=[line for line in unit.read_text().splitlines() if line.startswith('ExecStart=') and line!='ExecStart=']
    if len(commands)!=1 or '--media-allowed-root' in commands[0]:
        raise RuntimeError('Inspect existing connector command before modifying media roots')
    dropin=units/'sovereign-podcaster-marmot.service.d';dropin.mkdir(mode=0o700,exist_ok=True)
    target=dropin/'media.conf'
    text='[Service]\nExecStart=\n'+commands[0]+' "--media-allowed-root" "'+str(staging)+'"\n'
    if target.exists() and target.read_text()!=text:raise RuntimeError('Existing media drop-in differs; preserve it for inspection')
    target.write_text(text);target.chmod(0o600)
    subprocess.run(['systemctl','--user','daemon-reload'],env=env,check=True)
    subprocess.run(['systemctl','--user','restart','sovereign-podcaster-marmot.service'],env=env,check=True)


def contact(home):
    instance = json.loads((home/'podcaster-instance.json').read_text())
    bootstrap = json.loads((home/'bootstrap.json').read_text())
    repo=Path(instance.get('workspace_alias',instance['repository']))
    try:picker='/'+str(repo.relative_to(Path.home()))
    except ValueError:picker='a Git workspace under your home directory'
    return {'agent_npub': bootstrap['npub'], 'agent_nprofile': bootstrap.get('nprofile'),
            'trusted_contact_npub': instance['trusted_npub'],
            'next_step': 'Add agent_npub in White Noise, create a private group from the trusted contact, select '+picker+', and send a fresh test phrase.',
            'device_verification': instance.get('device_verification', 'REQUIRED')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, default=Path.home()/'.marmot-agents/podcast')
    p.add_argument('--trusted-npub')
    p.add_argument('--project-id')
    p.add_argument('--llm-config',type=Path,help='Private provider/model configuration; PPQ needs no OpenAI project or Codex CLI')
    p.add_argument('--work-root',type=Path,help='Private episode journal/artifact root outside Git')
    p.add_argument('--allow-timeout-only', action='store_true', help='Explicitly permit bounded model turns without a server dollar cap')
    p.add_argument('--enable-chat-media',action='store_true',help='Permit encrypted chat attachments from this private staging root only')
    p.add_argument('--contact', action='store_true', help='Print existing public pairing details; never regenerate identity')
    args = p.parse_args(); os.umask(0o077); home = args.home.expanduser().absolute()
    if args.contact:
        print(json.dumps(contact(home), indent=2)); return
    if not re.fullmatch(r'npub1[023456789acdefghjklmnpqrstuvwxyz]{58}', args.trusted_npub or ''):
        p.error('--trusted-npub must be the phone owner public npub, never a secret')
    selection=providers.settings(dict(model='gpt-6.1-sol',**({'llm_config':str(args.llm_config.expanduser().absolute())} if args.llm_config else {})),lambda path:json.loads(private_input(path)))
    ppq=selection['provider']=='ppq'
    if not ppq and not args.project_id:p.error('--project-id is required for the Codex Agents API backend')
    if args.project_id and not re.fullmatch('proj_[A-Za-z0-9]+',args.project_id):p.error('Invalid OpenAI project ID')
    if not args.allow_timeout_only:
        p.error('The tested API rejects per-session spending limits. Review and explicitly select --allow-timeout-only before enabling model replies.')
    for parent in (home.resolve(), *home.resolve().parents):
        git = parent/'.git'
        if git.is_file() or (git/'HEAD').is_file(): p.error('Marmot state must be outside Git')
    instance_path = home/'podcaster-instance.json'
    intent_path = home/'install-intent.json'
    if home.is_symlink(): p.error('Marmot home must not be a symlink')
    if instance_path.exists():
        old = json.loads(instance_path.read_text())
        if old['trusted_npub'] != args.trusted_npub or (args.project_id and old['project_id'] != args.project_id):
            p.error('Existing identity has different trusted contact/project; inspect before changing it')
        old['workspace_alias']=str(workspace_alias());old.setdefault('followup_steering',True)
        if not ppq:skill_links()
        if args.llm_config:old['llm_config']=str(args.llm_config.expanduser().absolute())
        if args.work_root:
            if old.get('work_root') and Path(old['work_root'])!=args.work_root.expanduser().absolute():p.error('Existing work root differs; inspect state before migration')
            old['work_root']=str(args.work_root.expanduser().absolute())
        if args.enable_chat_media:
            env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
            enable_chat_media(home,env);old['outbound_chat_media_enabled']=True
        save(instance_path,old)
        print(json.dumps(contact(home), indent=2)); return
    if ppq:
        key=private_input(Path(selection['ppq_key_file'])).strip()
        if not key or any(c.isspace() for c in key):p.error('Save one private PPQ API key before enabling this backend')
    for name in (() if ppq else ('application.key','environment.key')):
        key=Path.home()/'.config/sovereign-podcaster/openai'/name
        if key.is_symlink() or not key.is_file() or key.stat().st_uid!=os.getuid() or stat.S_IMODE(key.stat().st_mode)!=0o600:
            p.error('Save both private OpenAI keys as this user before enabling the API backend')
    if home.exists() and any(home.iterdir()) and not intent_path.exists(): p.error('Unmanaged nonempty Marmot home; refusing takeover')
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    if home.stat().st_uid != os.getuid() or stat.S_IMODE(home.stat().st_mode) != 0o700:
        p.error('Marmot home must be owner-owned and 0700')
    backend = REPO/'adapters/openai-agents/marmot-backend.py'
    if not os.access(backend, os.X_OK): p.error('Agents API backend must be installed and executable first')
    intent={'trusted_npub':args.trusted_npub,'project_id':args.project_id,'release':LOCK['tag']}
    if intent_path.exists() and json.loads(intent_path.read_text())!=intent:
        p.error('Partial installation has different parameters; inspect before resuming')
    save(intent_path,intent)
    download = home/'installer'; download.mkdir(mode=0o700,exist_ok=True)
    url = LOCK['repository']+'/releases/download/'+LOCK['tag']+'/'+LOCK['installer']
    downloader=urllib.request.build_opener(HTTPSRedirect(),urllib.request.ProxyHandler({}))
    with downloader.open(url, timeout=60) as response: data = response.read(2*1024*1024)
    with downloader.open(url+'.sha256', timeout=60) as response: checksum = response.read(4096).decode().split()[0]
    digest = hashlib.sha256(data).hexdigest()
    if digest != LOCK['installer_sha256'] or digest != checksum:
        raise RuntimeError('Upstream installer checksum differs from reviewed pin')
    installer = download/LOCK['installer']; installer.write_bytes(data); installer.chmod(0o600)
    env = {'HOME': str(Path.home()), 'USER': os.environ['USER'], 'LOGNAME': os.environ['USER'],
           'PATH': str(Path.home()/'.local/bin')+':/usr/bin:/bin', 'SHELL':'/bin/bash',
           'XDG_RUNTIME_DIR': '/run/user/'+str(os.getuid()),
           'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/'+str(os.getuid())+'/bus',
           'MARMOT_AGENT_LABEL':'sovereign-podcaster',
           'MARMOT_AGENT_SERVICE_NAME':'sovereign-podcaster-marmot',
           'MARMOT_HARNESS_SERVICE_NAME':'sovereign-podcaster-agent',
           'WN_CODEX_TIMEOUT_SECS':str(HARNESS_TIMEOUT_SECONDS), 'WN_CODEX_IDLE_TIMEOUT_SECS':'120',
           'WN_CODEX_MAX_PENDING_PER_GROUP':'4'}
    command = ['bash', str(installer), '--yes', '--home', str(home), '--allow-welcomer',
               args.trusted_npub, '--codex-bin', str(backend), '--execution-profile', 'inherit', '--no-start-wn-codex']
    with (home/'installer.log').open('w') as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    bootstrap = json.loads((home/'bootstrap.json').read_text())
    allowed = bootstrap.get('welcomer_account_ids_hex', [])
    if len(allowed) != 1: raise RuntimeError('Expected exactly one trusted inviter/sender')
    instance = {'schema':1, 'trusted_npub':args.trusted_npub, 'trusted_hex':allowed[0],
                'account_id_hex':bootstrap['account_id_hex'], 'project_id':args.project_id,
                'model':'gpt-6.1-sol', 'turn_timeout_seconds':180, 'allow_timeout_only':True, 'followup_steering':True,
                'repository':str(REPO), 'workspace_alias':str(workspace_alias()), 'workspace_root':str(Path.home()),'marmot_home':str(home),
                'codex_executable':str(Path.home()/'.local/bin/codex'),
                'openai_key_directory':str(Path.home()/'.config/sovereign-podcaster/openai'),
                'state_root':str(home/'api-state'), 'work_root':str((args.work_root or Path.home()/'.local/share/sovereign-podcaster/work').expanduser().absolute()),
                'device_verification':'REQUIRED', 'artifact_exports_enabled':False}
    if args.llm_config:instance['llm_config']=str(args.llm_config.expanduser().absolute())
    if not ppq:skill_links()
    if args.enable_chat_media:
        enable_chat_media(home,env);instance['outbound_chat_media_enabled']=True
    save(instance_path, instance)
    units = Path.home()/'.config/systemd/user'
    dropin = units/'sovereign-podcaster-agent.service.d'; dropin.mkdir(parents=True, exist_ok=True)
    # This is a path, not an application key. The executor gets only environment.key.
    (home/'harness').mkdir(mode=0o700,exist_ok=True)
    text = ('[Service]\nEnvironment="SP_MARMOT_INSTANCE='+str(instance_path)+'"\n'
            'Environment="WN_CODEX_STATE_PATH='+str(home/'harness/sessions.json')+'"\n'
            'Environment="WN_CODEX_TIMEOUT_SECS='+str(HARNESS_TIMEOUT_SECONDS)+'"\n'
            'Environment="RUST_LOG=warn"\n')
    (dropin/'podcaster.conf').write_text(text)
    subprocess.run(['systemctl','--user','daemon-reload'], env=env, check=True)
    subprocess.run(['systemctl','--user','enable','--now','sovereign-podcaster-agent.service'],env=env,check=True)
    print(json.dumps(contact(home), indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        raise SystemExit(str(error) if isinstance(error,RuntimeError) else type(error).__name__+': setup failed; inspect the private installer log')
