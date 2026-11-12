#!/usr/bin/env python3
"""Plan/upload/verify a Blossom blob, or delete an acknowledged new upload by receipt."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

CHUNK = 1024 * 1024
SIGNER = Path(__file__).resolve().parents[1] / 'skills/nostr-publishing/scripts/nostr_publish.py'


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_server(value):
    p = urllib.parse.urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username is not None or
            p.password is not None or p.path not in ('', '/') or p.query or p.fragment):
        raise ValueError('Use a bare HTTPS origin without credentials')
    return urllib.parse.urlunsplit(('https', p.netloc.lower(), '', '', ''))


class PublicReadRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def __init__(self, allowed_origins):
        self.allowed_origins = set(allowed_origins)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Public CDN retrieval can redirect; authorization and mutations cannot.
        if req.get_method() not in ('GET', 'HEAD') or any(k.lower() == 'authorization' for k, v in req.header_items()):
            return None
        p = urllib.parse.urlsplit(newurl)
        if p.scheme != 'https' or p.username is not None or p.password is not None:
            return None
        origin = urllib.parse.urlunsplit(('https', p.netloc.lower(), '', '', ''))
        if origin not in self.allowed_origins: return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener(read_redirect_origins=()):
    origins = [normalize_server(o) for o in read_redirect_origins]
    return urllib.request.build_opener(PublicReadRedirect(origins), urllib.request.ProxyHandler({}))


def fingerprint(path, mime=None):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Upload input must be a regular file')
    h, size = hashlib.sha256(), 0
    with path.open('rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block); size += len(block)
    mime = mime or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    return {'file': str(path), 'sha256': h.hexdigest(), 'size': size, 'mime': mime}


def save(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.blossom-state-')
    try:
        with os.fdopen(fd, 'w') as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(value, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def receipt_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s = os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
            raise ValueError('Receipt must be an owner-owned regular file with mode 0600')
        return json.load(f)


def signer(identity, expected):
    if not re.fullmatch('[0-9a-f]{64}', expected or ''):
        raise ValueError('Supply the expected lowercase hex public key')
    spec = importlib.util.spec_from_file_location('nostr_publish', SIGNER)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    if m.load_identity(identity)['pubkey'] != expected:
        raise ValueError('Selected identity does not match expected public key')
    return m


def authorization(m, identity, server, sha256, action, encoding):
    if action not in ('upload', 'delete', 'list'):
        raise ValueError('Unsupported Blossom authorization action')
    if action != 'list' and not re.fullmatch('[0-9a-f]{64}', sha256 or ''):
        raise ValueError('Mutating authorization requires the exact blob hash')
    event = m.sign_event(identity, {'kind': 24242, 'created_at': int(time.time()) - 1,
        'content': 'Sovereign podcaster: ' + action + ' selected blob',
        'tags': [['t', action], ['server', urllib.parse.urlsplit(server).hostname],
                 ['expiration', str(int(time.time()) + 300)]] + ([['x', sha256]] if sha256 else [])})
    payload = json.dumps(event, separators=(',', ':')).encode()
    token = base64.b64encode(payload) if encoding == 'standard' else base64.urlsafe_b64encode(payload).rstrip(b'=')
    return 'Nostr ' + token.decode()


def remote_check(client, url, asset, origin, timeout):
    request = urllib.request.Request(url, headers={'Origin': origin, 'User-Agent': 'sovereign-podcaster/1'})
    try:
        with client.open(request, timeout=timeout) as response:
            h, size = hashlib.sha256(), 0
            for block in iter(lambda: response.read(CHUNK), b''):
                size += len(block)
                if size > asset['size']:
                    raise ValueError('Public blob exceeds expected size')
                h.update(block)
            if response.status != 200 or size != asset['size'] or h.hexdigest() != asset['sha256']:
                raise ValueError('Public blob hash/size mismatch')
            if response.headers.get_content_type() != asset['mime']:
                raise ValueError('Public blob MIME mismatch')
            if response.headers.get('Access-Control-Allow-Origin') not in ('*', origin):
                raise ValueError('Public blob does not permit the configured playback origin')
            return {'url': url, 'resolved_url': response.geturl() if hasattr(response, 'geturl') else url,
                    'sha256': h.hexdigest(), 'size': size,
                    'mime': response.headers.get_content_type(), 'origin': origin, 'checked_at': now()}
    except urllib.error.HTTPError as error:
        error.close()
        if error.code in (404, 410): return None
        raise


def public_check(client, server, asset, origins, timeout):
    suffix = '.mp4' if asset['mime'] == 'video/mp4' else ''
    url = server + '/' + asset['sha256'] + suffix
    checks = []
    for origin in origins:
        check = remote_check(client, url, asset, origin, timeout)
        if not check: raise ValueError('Blob is not publicly retrievable')
        if asset['mime'] == 'video/mp4':
            end = min(1023, asset['size'] - 1)
            request = urllib.request.Request(url, headers={'Origin': origin, 'Range': f'bytes=0-{end}'})
            with client.open(request, timeout=timeout) as response:
                if (response.status != 206 or response.headers.get('Content-Range') !=
                        f'bytes 0-{end}/{asset["size"]}' or response.headers.get('Access-Control-Allow-Origin')
                        not in ('*', origin)):
                    raise ValueError('MP4 range/CORS response mismatch')
                with Path(asset['file']).open('rb') as f:
                    if response.read(end + 2) != f.read(end + 1):
                        raise ValueError('MP4 range bytes mismatch')
            check['range_verified'] = True
        checks.append(check)
    return checks


def upload(args):
    server = normalize_server(args.server)
    asset = fingerprint(args.file, args.mime)
    origins = list(dict.fromkeys(normalize_server(o) for o in args.origin))
    binding = dict(asset, server=server, pubkey=args.expected_pubkey, origins=origins)
    if not args.apply:
        return dict(binding, dry_run=True, receipt=str(args.receipt))
    m = signer(args.identity, args.expected_pubkey)
    redirects = getattr(args, 'read_redirect_origin', [])
    client = opener(redirects)
    if args.receipt.exists():
        state = receipt_read(args.receipt)
        if any(state.get(k) != v for k, v in binding.items()):
            raise ValueError('Existing receipt belongs to different bytes, identity or destination')
        if state.get('state', '').startswith('delet'):
            raise ValueError('This receipt has entered cleanup; do not re-upload')
    else:
        found = remote_check(client, server + '/' + asset['sha256'], asset, origins[0], args.timeout)
        state = dict(binding, version=1, state='ready', existed_before=bool(found),
                     upload_acknowledged=False, created_at=now())
        save(args.receipt, state)
        if found:
            state.update(state='verified', reused=True, public_checks=public_check(client, server, asset, origins, args.timeout))
            save(args.receipt, state)
            return state
    # Repeating an ambiguous upload uses exactly the same content-addressed bytes.
    if not state.get('upload_acknowledged'):
        if fingerprint(args.file, args.mime) != asset: raise ValueError('Upload source changed')
        state['state'] = 'uploading'; save(args.receipt, state)
        headers = {'Authorization': authorization(m, args.identity, server, asset['sha256'], 'upload', args.auth_encoding),
                   'Content-Type': asset['mime'], 'Content-Length': str(asset['size']), 'X-SHA-256': asset['sha256']}
        with Path(asset['file']).open('rb') as f:
            request = urllib.request.Request(server + '/upload', data=f, method='PUT', headers=headers)
            with client.open(request, timeout=args.timeout) as response:
                if response.status not in (200, 201): raise ValueError('Upload was not acknowledged')
                descriptor = json.loads(response.read(CHUNK))
                if descriptor.get('sha256') != asset['sha256'] or descriptor.get('size') != asset['size']:
                    raise ValueError('Upload descriptor does not match selected bytes')
                public_descriptor = {k: descriptor[k] for k in ('url', 'sha256', 'size', 'type', 'uploaded') if k in descriptor}
                state.update(upload_acknowledged=True, upload_status=response.status, descriptor=public_descriptor)
                save(args.receipt, state)
        if fingerprint(args.file, args.mime) != asset: raise ValueError('Upload source changed')
    state.update(state='verified', reused=False, public_read_redirect_origins=redirects,
                 public_checks=public_check(client, server, asset, origins, args.timeout))
    save(args.receipt, state)
    return state


def deletion_binding(state, server, expected):
    if (state.get('server') != server or state.get('pubkey') != expected or
            not re.fullmatch('[0-9a-f]{64}', state.get('sha256', ''))):
        raise ValueError('Delete receipt does not match selected server/identity')
    if state.get('existed_before') is not False or state.get('upload_acknowledged') is not True or state.get('reused'):
        raise ValueError('Refusing to delete a pre-existing/reused or unacknowledged blob')


def delete(args):
    server = normalize_server(args.server)
    state = receipt_read(args.receipt)
    deletion_binding(state, server, args.expected_pubkey)
    if not args.apply:
        return {'dry_run': True, 'server': server, 'sha256': state['sha256'], 'pubkey': state['pubkey']}
    m = signer(args.identity, args.expected_pubkey)
    client = opener(getattr(args, 'read_redirect_origin', [])); url = server + '/' + state['sha256']
    found = remote_check(client, url, state, state['origins'][0], args.timeout)
    if found:
        if state.get('state') == 'deleted': raise ValueError('Previously deleted hash reappeared; inspect before retry')
        state['state'] = 'deleting'; save(args.receipt, state)
        request = urllib.request.Request(url, method='DELETE', headers={
            'Authorization': authorization(m, args.identity, server, state['sha256'], 'delete', args.auth_encoding)})
        with client.open(request, timeout=args.timeout) as response:
            if response.status not in (200, 202, 204): raise ValueError('Delete was not acknowledged')
            state['delete_status'] = response.status; save(args.receipt, state)
    urls = [url] + ([url + '.mp4'] if state['mime'] == 'video/mp4' else [])
    for candidate in urls:
        if remote_check(client, candidate, state, state['origins'][0], args.timeout) is not None:
            raise ValueError('Server still returns the blob after deletion')
    state.update(state='deleted', deleted_at=now(), absent_urls=urls)
    save(args.receipt, state)
    return state


def removal_assessment(delete_status, heads, list_complete, listed):
    return (delete_status in (200, 202, 204) and len(heads) >= 1 and
            all(s in (404, 410) for s in heads) and list_complete is True and listed is False)


def removal_status(args):
    """Read-only origin evidence for providers whose missing GET returns a placeholder."""
    server = normalize_server(args.server); state = receipt_read(args.receipt)
    deletion_binding(state, server, args.expected_pubkey)
    m = signer(args.identity, args.expected_pubkey); client = opener(); heads = []
    urls = [server+'/'+state['sha256']]
    if state['mime'] == 'video/mp4': urls.append(urls[0]+'.mp4')
    for url in urls:
        try:
            with client.open(urllib.request.Request(url, method='HEAD'), timeout=args.timeout) as response:
                heads.append({'url': url, 'status': response.status})
        except urllib.error.HTTPError as error:
            heads.append({'url': url, 'status': error.code}); error.close()
    listed, complete, cursor, seen, pages = False, False, None, set(), 0
    listing_error = None
    token = authorization(m, args.identity, server, None, 'list', args.auth_encoding)
    for _ in range(10):
        query = {'limit': 100}
        if cursor: query['cursor'] = cursor
        url = server+'/list/'+state['pubkey']+'?'+urllib.parse.urlencode(query)
        try:
            with client.open(urllib.request.Request(url, headers={'Authorization': token}), timeout=args.timeout) as response:
                values = json.loads(response.read(4*CHUNK))
                if not isinstance(values, list): raise ValueError('Unexpected listing response shape')
        except urllib.error.HTTPError as error:
            listing_error = 'HTTP '+str(error.code); error.close(); break
        pages += 1
        if any(v.get('sha256') == state['sha256'] for v in values): listed = True; break
        if not values: complete = True; break
        last = values[-1].get('sha256')
        if not re.fullmatch('[0-9a-f]{64}', last or '') or last in seen: break
        seen.add(last); cursor = last
    return {'server': server, 'sha256': state['sha256'], 'delete_status': state.get('delete_status'),
            'head_checks': heads, 'list_complete': complete, 'listed': listed, 'list_pages': pages,
            'listing_error': listing_error,
            'origin_removal_evidence_passed': removal_assessment(state.get('delete_status'),
                [h['status'] for h in heads], complete, listed),
            'get_absence_verified': state.get('state') == 'deleted',
            'scope': 'Configured origin only; does not prove erasure from other caches or copies'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    for action in ('upload', 'check', 'delete', 'removal-status'):
        q = sub.add_parser(action)
        q.add_argument('--server', required=True)
        q.add_argument('--timeout', type=float, default=30)
        q.add_argument('--read-redirect-origin', action='append', default=[],
                       help='Explicit HTTPS origin allowed only for unauthenticated GET/HEAD redirects')
        if action in ('upload', 'check'):
            q.add_argument('--file', type=Path, required=True)
            q.add_argument('--mime')
            q.add_argument('--origin', action='append', required=True)
        if action != 'check':
            q.add_argument('--identity', type=Path, required=True)
            q.add_argument('--expected-pubkey', required=True)
            q.add_argument('--receipt', type=Path, required=True)
            q.add_argument('--auth-encoding', choices=['base64url', 'standard'], default='base64url')
            q.add_argument('--apply', action='store_true')
    args = p.parse_args(); os.umask(0o077)
    if args.timeout <= 0 or args.timeout > 120: p.error('timeout must be in (0, 120] seconds')
    try:
        if args.action == 'upload': result = upload(args)
        elif args.action == 'delete': result = delete(args)
        elif args.action == 'removal-status': result = removal_status(args)
        else: result = public_check(opener(args.read_redirect_origin), normalize_server(args.server), fingerprint(args.file, args.mime),
                                   [normalize_server(o) for o in args.origin], args.timeout)
        print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as error:
        p.exit(1, f'Blossom HTTP {error.code}; response body suppressed (may contain authorization data)\n')
    except Exception as error:
        p.exit(1, f'{type(error).__name__}: {error}\n')


if __name__ == '__main__': main()
