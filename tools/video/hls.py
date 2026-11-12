"""Content-addressed HLS packaging, ported from the working podcast workflow."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
from episodes import save as save_json
HLS_MIME = 'application/vnd.apple.mpegurl'
URI = re.compile(r'URI="([^"]+)"')
HASH = re.compile(r'[0-9a-f]{64}')
CHUNK = 1024 * 1024
def utc_now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()

def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)
    ]))

def stream(info, kind):
    return next((s for s in info['streams'] if s['codec_type'] == kind), None)

def playlist_references(text):
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            yield line
        if line.startswith('#'):
            yield from URI.findall(line)

def local_child(parent, reference, root):
    parsed = urllib.parse.urlsplit(reference)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or reference.startswith('/'):
        raise ValueError(f'Expected a local playlist reference: {reference}')
    child = (parent / reference).resolve()
    if not child.is_relative_to(root.resolve()) or not child.is_file():
        raise ValueError(f'Missing or escaped playlist asset: {reference}')
    return child

def package_hls(output, fallback):
    """Rewrite leaves first to relative, extensionless SHA-256 names (BUD-01)."""
    root = output / 'hls'
    blobs = output / 'blobs'
    blobs.mkdir()
    assets, known, active = [], {}, set()

    def add(data, role, mime):
        sha = hashlib.sha256(data).hexdigest()
        target = blobs / sha
        if not target.exists():
            target.write_bytes(data)
            assets.append(dict(sha256=sha, size=len(data), path=f'blobs/{sha}', role=role, mime=mime))
        return sha

    # A full MP4 is streamed/copied in bounded memory, unlike small HLS objects.
    sha = digest(fallback)
    import shutil
    shutil.copyfile(fallback, blobs / sha)
    assets.append(dict(sha256=sha, size=fallback.stat().st_size, path=f'blobs/{sha}', role='fallback', mime='video/mp4'))
    fallback_sha = sha

    def visit(path):
        path = path.resolve()
        if path in active:
            raise ValueError('Playlist reference cycle')
        if path in known:
            return known[path]
        active.add(path)
        if path.suffix == '.m3u8':
            text = path.read_text()
            refs = {ref: visit(local_child(path.parent, ref, root)) for ref in playlist_references(text)}
            lines = []
            for line in text.splitlines():
                if line.strip() and not line.startswith('#'):
                    line = refs[line.strip()]
                elif line.startswith('#'):
                    line = URI.sub(lambda m: f'URI="{refs[m[1]]}"', line)
                lines.append(line)
            role = 'master' if path.name == 'master.m3u8' else 'playlist'
            sha = add(('\n'.join(lines) + '\n').encode(), role, HLS_MIME)
        else:
            sha = add(path.read_bytes(), 'init' if path.suffix == '.mp4' else 'segment',
                      'video/mp4' if path.suffix == '.mp4' else 'video/iso.segment')
        active.remove(path)
        known[path] = sha
        return sha

    master_sha = visit(root / 'master.m3u8')
    return assets, master_sha, fallback_sha

def validate_bundle(directory):
    directory = Path(directory).resolve()
    bundle = json.loads((directory / 'bundle.json').read_text())
    if bundle['version'] not in (1, 2):
        raise ValueError('Unsupported bundle version')
    known = {}
    for asset in bundle['assets']:
        sha = asset['sha256']
        if not HASH.fullmatch(sha) or sha in known:
            raise ValueError('Invalid or duplicate blob hash')
        path = (directory / asset['path']).resolve()
        if not path.is_relative_to(directory) or digest(path) != sha or path.stat().st_size != asset['size']:
            raise ValueError(f'Asset is missing, changed or outside the bundle: {sha}')
        if asset['role'] in ('master', 'playlist'):
            text = path.read_text()
            if not text.startswith('#EXTM3U\n'):
                raise ValueError('Invalid HLS playlist')
            for ref in playlist_references(text):
                if not HASH.fullmatch(ref) or ref not in known:
                    raise ValueError(f'Playlist dependency is missing or ordered incorrectly: {ref}')
        known[sha] = asset
    if known[bundle['master_sha256']]['role'] != 'master' or known[bundle['fallback_sha256']]['role'] != 'fallback':
        raise ValueError('Missing master or MP4 fallback')
    if bundle['assets'][-1]['sha256'] != bundle['master_sha256']:
        raise ValueError('Master playlist must be uploaded last')
    if bundle['version'] == 2:
        fallback = bundle['fallback']
        if fallback['sha256'] != bundle['fallback_sha256'] or fallback['size'] != known[fallback['sha256']]['size']:
            raise ValueError('Independent fallback metadata does not match the packaged bytes')
    return bundle

def media_tags(bundle, servers):
    fallback = bundle.get('fallback', bundle['variants'][0])
    def tag(sha, extension, mime, duration):
        asset = next(a for a in bundle['assets'] if a['sha256'] == sha)
        result = ['imeta', f'url {servers[0]}/{sha}{extension}', f'm {mime}', f'x {sha}', f'size {asset["size"]}',
                  f'duration {duration}']
        result.extend(f'fallback {server}/{sha}{extension}' for server in servers[1:])
        return result
    # The master declares exact CODECS per rendition. A bare playlist MIME also
    # works in clients that compare HLS MIME strings literally before using MSE.
    hls = tag(bundle['master_sha256'], '.m3u8', HLS_MIME, bundle['variants'][0]['duration'])
    mp4_mime = 'video/mp4' + (f'; codecs="{fallback["codecs"]}"' if 'codecs' in fallback else '')
    mp4 = tag(bundle['fallback_sha256'], '.mp4', mp4_mime, fallback['duration'])
    v = fallback
    mp4.extend([f'dim {v["width"]}x{v["height"]}', f'bitrate {v["average_bitrate"]}'])
    return [hls, mp4]
