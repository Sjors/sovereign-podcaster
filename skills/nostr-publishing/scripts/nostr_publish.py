#!/usr/bin/env python3
"""Create a Nostr identity, sign events locally and publish verified events over WSS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.parse
import urllib.request
import uuid

from bech32 import bech32_encode, convertbits
from coincurve import PrivateKey, PublicKeyXOnly
import websocket


def canonical_id(event):
    value = [0, event['pubkey'], event['created_at'], event['kind'], event['tags'], event['content']]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_unsigned(event):
    if not re.fullmatch('[0-9a-f]{64}', event.get('pubkey', '')):
        raise ValueError('Expected a lowercase hexadecimal public key')
    if type(event.get('created_at')) is not int or event['created_at'] < 0:
        raise ValueError('created_at must be a nonnegative integer')
    if type(event.get('kind')) is not int or not 0 <= event['kind'] <= 65535:
        raise ValueError('Invalid event kind')
    if not isinstance(event.get('content'), str):
        raise ValueError('content must be a string')
    if not isinstance(event.get('tags'), list) or any(
        not isinstance(tag, list) or not tag or any(not isinstance(x, str) for x in tag)
        for tag in event['tags']
    ):
        raise ValueError('tags must contain nonempty string arrays')


def verify(event):
    validate_unsigned(event)
    if event.get('id') != canonical_id(event):
        raise ValueError('Event ID mismatch')
    if not PublicKeyXOnly(bytes.fromhex(event['pubkey'])).verify(bytes.fromhex(event['sig']), bytes.fromhex(event['id'])):
        raise ValueError('Invalid BIP-340 signature')


def encode(prefix, payload):
    return bech32_encode(prefix, convertbits(payload, 8, 5))


def write_new(path, value, mode=0o600):
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def init_identity(directory, name, relays):
    directory = Path(directory).expanduser().absolute()
    if directory.is_symlink():
        raise ValueError('Identity directory must not be a symlink')
    for parent in (directory.resolve(), *directory.resolve().parents):
        git = parent / '.git'
        if git.is_file() or (git / 'HEAD').is_file():
            raise ValueError('Identity secrets must be outside Git repositories')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise ValueError('Identity directory must be owner-owned with mode 0700')
    if (directory / 'MIGRATED.json').exists():
        raise ValueError('Identity migrated; use its recorded replacement instead of generating another key')
    if (directory / 'secret.hex').exists() or (directory / 'identity.json').exists():
        raise ValueError('Identity already exists; refusing to replace keys')
    relays = relay_urls(relays)
    key = PrivateKey()  # coincurve uses the operating system CSPRNG
    pubkey = key.public_key_xonly.format().hex()
    fd = os.open(directory / 'secret.hex', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(key.secret.hex() + '\n')
    config = dict(name=name, pubkey=pubkey, npub=encode('npub', bytes.fromhex(pubkey)),
                  key_file='secret.hex', relays=relays, profile={'name': name})
    write_new(directory / 'identity.json', config)
    return {key: config[key] for key in ('name', 'pubkey', 'npub', 'relays')}


def load_identity(path):
    if (Path(path).parent / 'MIGRATED.json').exists():
        raise ValueError('Identity migrated; use its recorded replacement')
    value = json.loads(Path(path).read_text())
    if not re.fullmatch('[0-9a-f]{64}', value.get('pubkey', '')):
        raise ValueError('Invalid configured public key')
    relay_urls(value['relays'])
    return value


def sign_event(identity_path, unsigned):
    config = load_identity(identity_path)
    key_path = Path(identity_path).parent / config['key_file']
    # Open the actual key once; reject symlinks and broad permissions before reading it.
    fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'r') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('Private key must be an owner-only regular file owned by this user')
        secret = f.read().strip()
    key = PrivateKey(bytes.fromhex(secret))
    if key.public_key_xonly.format().hex() != config['pubkey']:
        raise ValueError('Private key does not match configured public key')
    event = dict(unsigned)
    event.setdefault('created_at', int(time.time()))
    event.setdefault('pubkey', config['pubkey'])
    event.setdefault('tags', [])
    if event['pubkey'] != config['pubkey']:
        raise ValueError('Event specifies a different author')
    validate_unsigned(event)
    # Keep only NIP-01 fields; never copy unrelated input/config fields into a signed event.
    event = {field: event[field] for field in ('pubkey', 'created_at', 'kind', 'tags', 'content')}
    event['id'] = canonical_id(event)
    event['sig'] = key.sign_schnorr(bytes.fromhex(event['id'])).hex()
    verify(event)
    return event


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def resolve_nip05(identifier):
    name, domain = identifier.rsplit('@', 1)
    if not re.fullmatch(r'[a-z0-9_.-]+', name) or not re.fullmatch(r'[A-Za-z0-9.-]+', domain):
        raise ValueError('Invalid NIP-05 identifier')
    url = 'https://' + domain + '/.well-known/nostr.json?' + urllib.parse.urlencode({'name': name})
    request = urllib.request.Request(url, headers={'User-Agent': 'nostr-publishing/1'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
        data = json.load(response)
    pubkey = data['names'][name]
    if not re.fullmatch('[0-9a-f]{64}', pubkey):
        raise ValueError('NIP-05 returned an invalid public key')
    return dict(identifier=identifier, url=url, pubkey=pubkey,
                relays=data.get('relays', {}).get(pubkey, []), checked_at=int(time.time()))


def relay_urls(urls):
    result = list(dict.fromkeys(urls))
    if not result or any(urllib.parse.urlparse(url).scheme != 'wss' or
                         not urllib.parse.urlparse(url).hostname or
                         urllib.parse.urlparse(url).username is not None for url in result):
        raise ValueError('Supply one or more wss:// relay URLs without embedded credentials')
    return result


def query_relay(relay, filters, timeout=8):
    subscription = uuid.uuid4().hex
    events, notices = [], []
    connection = websocket.create_connection(relay, timeout=timeout, suppress_origin=True)
    try:
        connection.send(json.dumps(['REQ', subscription, filters], separators=(',', ':')))
        deadline = time.monotonic() + timeout
        complete = False
        while time.monotonic() < deadline:
            connection.settimeout(max(0.1, deadline - time.monotonic()))
            msg = json.loads(connection.recv())
            if msg[0] == 'EVENT' and msg[1] == subscription:
                verify(msg[2])
                events.append(msg[2])
            elif msg[0] == 'EOSE' and msg[1] == subscription:
                complete = True
                break
            elif msg[0] == 'CLOSED' and msg[1] == subscription:
                notices.append(msg[2])
                break
            elif msg[0] == 'NOTICE':
                notices.append(msg[1])
        return dict(events=events, complete=complete, notices=notices)
    finally:
        connection.close()


def publish_relay(relay, event, timeout=8):
    verify(event)
    connection = websocket.create_connection(relay, timeout=timeout, suppress_origin=True)
    try:
        connection.send(json.dumps(['EVENT', event], ensure_ascii=False, separators=(',', ':')))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            connection.settimeout(max(0.1, deadline - time.monotonic()))
            msg = json.loads(connection.recv())
            if msg[0] == 'OK' and msg[1] == event['id']:
                return dict(accepted=msg[2] is True, message=msg[3])
        return dict(accepted=False, message='No matching OK received')
    finally:
        connection.close()


def publish_and_check(relay, event):
    try:
        result = publish_relay(relay, event)
    except Exception as exc:
        return {'accepted': False, 'retrieved': False, 'error': str(exc)}
    try:
        # A relay OK is an acknowledgement, not proof that a query returns the event.
        found = query_relay(relay, {'ids': [event['id']], 'limit': 1})
        result['retrieved'] = any(e['id'] == event['id'] for e in found['events'])
        return result
    except Exception as exc:
        result.update(retrieved=False, query_error=str(exc))
        return result


def article_event(markdown, title, slug, summary, published_at, source_url=None):
    if not re.fullmatch('[a-z0-9-]+', slug):
        raise ValueError('Use a stable lowercase article slug')
    # HTML is not supported by NIP-23; leave prose and link transformations to review.
    if re.search(r'</?[A-Za-z][^>]*>', markdown):
        raise ValueError('NIP-23 content must be Markdown without HTML')
    tags = [['d', slug], ['title', title], ['summary', summary], ['published_at', str(published_at)]]
    if source_url:
        tags.append(['r', source_url])
    return dict(kind=30023, tags=tags, content=markdown)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'public', 'resolve', 'query', 'sign', 'publish', 'article'))
    parser.add_argument('--identity', type=Path, help='explicit identity.json path')
    parser.add_argument('--directory', type=Path, help='new identity directory for init')
    parser.add_argument('--name')
    parser.add_argument('--relay', action='append', default=[])
    parser.add_argument('--nip05')
    parser.add_argument('--filter', help='NIP-01 JSON filter for query')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true', help='actually publish; otherwise plan offline')
    parser.add_argument('--title')
    parser.add_argument('--slug')
    parser.add_argument('--summary')
    parser.add_argument('--published-at', type=int)
    parser.add_argument('--source-url')
    args = parser.parse_args()
    try:
        if args.action == 'init':
            if not args.directory or not args.name:
                raise ValueError('init requires directory and name')
            result = init_identity(args.directory, args.name, args.relay)
        elif args.action == 'resolve':
            result = resolve_nip05(args.nip05)
        elif args.action == 'article':
            if not all((args.input, args.title, args.slug, args.summary, args.published_at, args.output)):
                raise ValueError('article requires input, title, slug, summary, published-at and output')
            result = article_event(args.input.read_text(), args.title, args.slug, args.summary,
                                   args.published_at, args.source_url)
            write_new(args.output, result)
        elif args.action == 'sign':
            if not args.identity or not args.input or not args.output:
                raise ValueError('sign requires identity, input and output')
            result = sign_event(args.identity, json.loads(args.input.read_text()))
            write_new(args.output, result)
        else:
            config = load_identity(args.identity) if args.identity else None
            if args.action == 'public':
                if config is None:
                    raise ValueError('public requires identity')
                result = {k: config[k] for k in ('name', 'pubkey', 'npub', 'relays')}
            else:
                relays = relay_urls(args.relay or (config['relays'] if config else []))
                if args.action == 'query':
                    result = {}
                    for relay in relays:
                        try:
                            result[relay] = query_relay(relay, json.loads(args.filter))
                        except Exception as exc:
                            result[relay] = {'error': str(exc)}
                else:
                    event = json.loads(args.input.read_text())
                    verify(event)
                    if config and config['pubkey'] != event['pubkey']:
                        raise ValueError('Signed event does not match selected identity')
                    result = {'event_id': event['id'], 'pubkey': event['pubkey'], 'kind': event['kind'],
                              'relays': {r: publish_and_check(r, event) for r in relays} if args.apply else relays,
                              'dry_run': not args.apply}
        if args.output and args.action not in ('article', 'sign'):
            write_new(args.output, result)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        parser.exit(1, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
