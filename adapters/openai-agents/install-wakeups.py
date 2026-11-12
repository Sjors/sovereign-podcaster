#!/usr/bin/env python3
"""Install this account's transcript completion/reaction watcher without restarting its agent."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import episodes as e

def install(instance_path):
    config=e.read(instance_path)
    if not Path(config['transcription_config']).is_file():raise ValueError('Configure transcription before enabling its watcher')
    def quote(value):
        value=str(value)
        if any(c in value for c in ('\n','\r','\0','%')):raise ValueError('Unsupported systemd path')
        return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
    units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
    script=Path(__file__).with_name('wakeups.py').resolve()
    text='[Unit]\nDescription=Sovereign podcaster transcript handoffs\nAfter=sovereign-podcaster-marmot.service\n\n[Service]\nType=simple\nUMask=0077\nExecStart='+quote(sys.executable)+' '+quote(script)+' --instance '+quote(instance_path.resolve())+'\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n'
    path=units/'sovereign-podcaster-wakeups.service'
    if path.exists() and path.read_text()!=text:raise ValueError('Existing watcher unit differs; inspect it before replacement')
    path.write_text(text);path.chmod(0o600)
    env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()))
    subprocess.run(['systemctl','--user','daemon-reload'],env=env,check=True)
    subprocess.run(['systemctl','--user','enable','--now','sovereign-podcaster-wakeups.service'],env=env,check=True)
    subprocess.run(['systemctl','--user','is-active','--quiet','sovereign-podcaster-wakeups.service'],env=env,check=True)
    current=e.read(instance_path);current['transcription_wakeups']=True;e.save(instance_path,current)
    return path

def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__);p.add_argument('--instance',type=Path,required=True);a=p.parse_args();install(a.instance);print('Transcript handoffs enabled; existing agent/connector services were not restarted.')
if __name__=='__main__':main()
