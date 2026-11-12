"""Reviewed native-video and announcement metadata; no network or text rewriting."""
import re
from urllib.parse import urlsplit


def metadata(value):
    required = {'d', 'title', 'description', 'announcement'}
    optional = {'published_at', 'source_url', 'hashtags', 'previous_event_id',
                'participants', 'announcement_mentions', 'announce'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ValueError('Explicit Nostr d/title/description/announcement metadata is required')
    if any(not isinstance(value[k], str) for k in required) or not value['d'] or not value['title']:
        raise ValueError('Nostr identity/title/description/announcement must be text with a nonempty identity/title')
    if 'announce' in value and type(value['announce']) is not bool:raise ValueError('Nostr announce must be an explicit boolean')
    if value.get('announce') is False and (value['announcement'] or value.get('announcement_mentions')):
        raise ValueError('No-announcement metadata requires empty announcement text and mention tags')
    for field in ('participants', 'announcement_mentions'):
        keys = value.get(field, [])
        if not isinstance(keys, list) or any(not isinstance(k, str) or not re.fullmatch('[0-9a-f]{64}', k) for k in keys):
            raise ValueError(f'Nostr {field} must be a list of lowercase hex public keys')
        if len(keys) != len(set(keys)):
            raise ValueError(f'Nostr {field} contains duplicate public keys')
    if 'hashtags' in value and (not isinstance(value['hashtags'], list) or
                               any(not isinstance(t, str) or not t for t in value['hashtags'])):
        raise ValueError('Nostr hashtags must be a list of nonempty strings')
    if 'source_url' in value and not isinstance(value['source_url'], str):
        raise ValueError('Nostr source URL must be public HTTPS')
    if value.get('source_url'):
        url = urlsplit(value['source_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Nostr source URL must be public HTTPS')
    return value
