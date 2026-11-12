#!/usr/bin/env python3
"""Build the pinned harness with incoming-message context and explicit silent turns."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
LOCK=json.loads((ROOT/'adapters/marmot/release.json').read_text())
COMMIT='3fb4b4759ac676b0c21c4c3527074866c9fa4c89'
PATCH=ROOT/'patches/marmot-message-context.patch'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cargo',default='cargo');a=p.parse_args();os.umask(0o077)
    source=a.source.expanduser().absolute();out=a.out.expanduser().absolute()
    if out.exists():raise RuntimeError('Artifact destination exists; inspect it first')
    if not source.exists():subprocess.run(['git','-c','credential.helper=','clone','--branch',LOCK['tag'],'--depth','1',LOCK['repository']+'.git',str(source)],check=True)
    def git(*args,**kwargs):return subprocess.run(['git','-C',str(source),*args],check=True,**kwargs)
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=COMMIT:raise RuntimeError('Source differs from pinned upstream commit')
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True)
    if dirty:
        git('apply','--reverse','--check',str(PATCH))
        diff=subprocess.check_output(['git','-C',str(source),'diff','--binary'])
        if diff!=PATCH.read_bytes():raise RuntimeError('Source has additional modifications; use a fresh build directory')
    else:git('apply','--check',str(PATCH));git('apply',str(PATCH))
    subprocess.run([a.cargo,'test','--locked','--release','-p','marmot-terminal-harness','--lib'],cwd=source,check=True)
    subprocess.run([a.cargo,'test','--locked','--release','-p','marmot-terminal-harness','--test','jsonl_process'],cwd=source,check=True)
    subprocess.run([a.cargo,'test','--locked','--release','-p','wn-codex','--','--test-threads=1'],cwd=source,check=True)
    subprocess.run([a.cargo,'build','--locked','--release','-p','wn-codex'],cwd=source,check=True)
    binary=source/'target/release/wn-codex';out.mkdir(mode=0o700,parents=True);shutil.copyfile(binary,out/'wn-codex');(out/'wn-codex').chmod(0o700)
    def sha(path):return hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    manifest=dict(schema=1,upstream=LOCK['repository'],commit=COMMIT,tag=LOCK['tag'],patch_sha256=sha(PATCH),binary_sha256=sha(out/'wn-codex'),cargo=subprocess.check_output([a.cargo,'--version'],text=True).strip(),license='MIT',tests='149 library + 23 jsonl_process tests and wn-codex tests; umask 077; message context, parallel route isolation and explicit silence')
    (out/'build.json').write_text(json.dumps(manifest,indent=2)+'\n');print(out)
if __name__=='__main__':main()
