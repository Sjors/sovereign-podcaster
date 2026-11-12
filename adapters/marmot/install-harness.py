#!/usr/bin/env python3
"""Install a verified patched harness for this user's podcast service only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--home',type=Path,required=True);a=p.parse_args()
    bundle=a.bundle.resolve();home=a.home.expanduser().resolve();manifest=json.loads((bundle/'build.json').read_text())
    if manifest.get('commit')!='3fb4b4759ac676b0c21c4c3527074866c9fa4c89' or manifest.get('patch_sha256')!=sha(ROOT/'patches/marmot-message-context.patch') or manifest['binary_sha256']!=sha(bundle/'wn-codex'):raise RuntimeError('Build provenance/hash mismatch')
    if home.stat().st_uid!=os.getuid() or home.stat().st_mode&0o777!=0o700:raise RuntimeError('Expected private owned Marmot instance')
    if list((home/'api-state').rglob('*.active.json')):raise RuntimeError('A model request is active/unresolved; inspect before restarting')
    env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
    def system(*args):subprocess.run(['systemctl','--user',*args],env=env,check=True)
    target=Path.home()/'.local/lib/sovereign-podcaster/wn-codex';target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    drop=Path.home()/'.config/systemd/user/sovereign-podcaster-agent.service.d/message-context.conf'
    if '\n' in str(target):raise RuntimeError('Invalid executable path')
    text='[Service]\nExecStart=\nExecStart="'+str(target).replace('%','%%').replace('\\','\\\\').replace('"','\\"')+'"\n'
    if target.exists() and sha(target)==manifest['binary_sha256'] and drop.exists() and drop.read_text()==text:print('Patched harness already installed');return
    system('stop','sovereign-podcaster-agent.service')
    if target.exists():shutil.copyfile(target,target.with_name('wn-codex.previous'))
    with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f:
        f.write((bundle/'wn-codex').read_bytes());os.fchmod(f.fileno(),0o700);temporary=Path(f.name)
    temporary.replace(target);shutil.copyfile(bundle/'build.json',target.with_name('build.json'))
    drop.parent.mkdir(mode=0o700,parents=True,exist_ok=True);drop.write_text(text)
    system('daemon-reload');system('start','sovereign-podcaster-agent.service');system('is-active','sovereign-podcaster-agent.service')
    print('Installed for the podcast service. Original upstream binary and other agents are unchanged.')
if __name__=='__main__':main()
