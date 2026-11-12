#!/usr/bin/env python3
"""Record an actual direct maintainer instruction; never impersonate Marmot.

This local operator entry point is audit evidence within the shared UID, not a
human-authentication API. The operator must have received the saved instruction
directly, and must bind its scope to the reviewed files and destinations.
"""
import argparse
import json
import os
from pathlib import Path
import episodes as e
import reviews


def record(root,show,episode,revision,scope,authorization,config):
    with e.journal(root) as (_,data):
        item=e.episode(data,show,episode);r=e.verified_revision(item,revision)
        if revision!=item['current_revision']:raise ValueError('Approve only the current revision')
        grant=e.read(authorization)
        if grant.get('source')!='explicit-maintainer-user-request':raise ValueError('A direct maintainer instruction is required')
        old=list(item['approvals'])
        a=e.approve(item,revision,scope,authorization)
        a['source']='explicit-maintainer-user-request'
        try:reviews.require(item,scope,reviews.manifest(r,scope),config)
        except Exception:
            item['approvals']=old
            raise
        return dict(scope=scope,revision=revision,manifest_sha256=a['manifest_sha256'],youtube_video_id=a.get('youtube_video_id'))


def main():
    os.umask(0o077);p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','authorization','config'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('show','episode','revision'):p.add_argument('--'+key,required=True)
    p.add_argument('--scope',choices=reviews.SCOPES,required=True);a=p.parse_args()
    print(json.dumps(record(a.root,a.show,a.episode,a.revision,a.scope,a.authorization,e.read(a.config))))

if __name__=='__main__':main()
