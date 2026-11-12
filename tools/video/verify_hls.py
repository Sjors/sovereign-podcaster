#!/usr/bin/env python3
"""Verify local HLS compressed payloads and optionally fully decode each rendition."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from . import hls as w


def packets(path, selector):
    data = subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', selector, '-show_packets',
        '-show_entries', 'packet=data_hash', '-show_data_hash', 'sha256', '-of', 'csv=p=0', str(path)
    ]).decode()
    hashes = re.findall(r'SHA256:([0-9a-f]{64})', data)
    if not hashes:
        raise ValueError(f'No encoded packets found: {path} ({selector})')
    return dict(count=len(hashes), ordered_sha256=hashlib.sha256(''.join(hashes).encode()).hexdigest())


def verify(directory, full_decode=False):
    directory = Path(directory).resolve()
    bundle = w.validate_bundle(directory)
    results = []
    for variant in bundle['variants']:
        print(f"Verifying {variant['label']} AV1/AAC packet identity", flush=True)
        playlist = directory / 'hls' / variant['label'] / 'index.m3u8'
        item = dict(label=variant['label'], codecs=variant['codecs'], streams={})
        for selector in ('v:0', 'a:0'):
            source = packets(variant['path'], selector)
            packaged = packets(playlist, selector)
            if source != packaged:
                raise ValueError(f'Remuxing changed encoded packets: {variant["label"]} {selector}')
            item['streams'][selector] = dict(**packaged, matches_source=True)
        if full_decode:
            print(f"Fully decoding {variant['label']} local HLS", flush=True)
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '2',
                            '-filter_threads', '2', '-i', str(playlist), '-map', '0:v:0', '-map', '0:a:0',
                            '-f', 'null', '-'], check=True)
            item['full_hls_decode_passed'] = True
        results.append(item)
        w.save_json(directory / 'media-verification.json', dict(checked_at=w.utc_now(), variants=results,
                    complete=len(results) == len(bundle['variants']), real_episode_uploaded=False,
                    video_event_published=False))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--full-decode', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle, args.full_decode), indent=2))
