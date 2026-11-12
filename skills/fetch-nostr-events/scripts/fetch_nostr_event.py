#!/usr/bin/env python3
"""Fetch and verify a public Nostr event from a NIP-19 identifier or URL."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
ENTITY_RE = re.compile(r"(?i)(?:nostr:)?((?:note|nevent|naddr)1[023456789acdefghjklmnpqrstuvwxyz]+)")


def point_add(a: tuple[int, int] | None, b: tuple[int, int] | None) -> tuple[int, int] | None:
    if a is None:
        return b
    if b is None:
        return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % P == 0:
            return None
        slope = (3 * a[0] * a[0]) * pow(2 * a[1], P - 2, P) % P
    else:
        slope = (b[1] - a[1]) * pow((b[0] - a[0]) % P, P - 2, P) % P
    x = (slope * slope - a[0] - b[0]) % P
    return x, (slope * (a[0] - x) - a[1]) % P


def point_mul(k: int, point: tuple[int, int]) -> tuple[int, int] | None:
    result = None
    addend: tuple[int, int] | None = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def lift_x(x: int) -> tuple[int, int] | None:
    if x >= P:
        return None
    y = pow((pow(x, 3, P) + 7) % P, (P + 1) // 4, P)
    if pow(y, 2, P) != (pow(x, 3, P) + 7) % P:
        return None
    return x, y if y % 2 == 0 else P - y


def tagged_hash(tag: str, payload: bytes) -> bytes:
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + payload).digest()


def verify_schnorr(pubkey_hex: str, message: bytes, signature_hex: str) -> bool:
    try:
        pubkey = bytes.fromhex(pubkey_hex)
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    if len(pubkey) != 32 or len(message) != 32 or len(signature) != 64:
        return False
    public_point = lift_x(int.from_bytes(pubkey, "big"))
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    if public_point is None or r >= P or s >= N:
        return False
    challenge = int.from_bytes(
        tagged_hash("BIP0340/challenge", signature[:32] + pubkey + message), "big"
    ) % N
    negative_public = (public_point[0], (-public_point[1]) % P)
    candidate = point_add(point_mul(s, G), point_mul(challenge, negative_public))
    return candidate is not None and candidate[1] % 2 == 0 and candidate[0] == r


def canonical_event_id(event: dict) -> str:
    serializable = [
        0,
        event["pubkey"],
        event["created_at"],
        event["kind"],
        event["tags"],
        event["content"],
    ]
    encoded = json.dumps(serializable, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_event(event: dict) -> None:
    required = {"id", "pubkey", "created_at", "kind", "tags", "content", "sig"}
    missing = required.difference(event)
    if missing:
        raise ValueError(f"event is missing fields: {', '.join(sorted(missing))}")
    expected = canonical_event_id(event)
    if event["id"].lower() != expected:
        raise ValueError(f"invalid event id: expected {expected}, got {event['id']}")
    if not verify_schnorr(event["pubkey"], bytes.fromhex(expected), event["sig"]):
        raise ValueError("invalid BIP-340 event signature")


def extract_entity(target: str) -> str:
    match = ENTITY_RE.search(target.strip())
    if not match:
        raise ValueError("expected a note1, nevent1, or naddr1 identifier or URL containing one")
    return match.group(1).lower()


def parse_event_json(text: str) -> dict:
    candidates = [text.strip(), *text.splitlines()]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict) and "id" in value and "sig" in value:
            return value
    raise ValueError("no Nostr event JSON found")


def fetch_with_nak(entity: str, timeout: float) -> dict:
    result = subprocess.run(
        ["nak", "fetch", entity],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"nak exited with status {result.returncode}")
    return parse_event_json(result.stdout)


def extract_gateway_event(page: str) -> dict:
    marker = re.search(
        r"Event JSON</div>\s*<div[^>]*>(.*?)</div>", page, flags=re.IGNORECASE | re.DOTALL
    )
    if not marker:
        raise ValueError("gateway page did not contain embedded Event JSON")
    raw_json = re.sub(r"<[^>]+>", "", marker.group(1))
    return parse_event_json(html.unescape(raw_json))


def fetch_with_gateway(entity: str, gateway: str, timeout: float) -> dict:
    url = gateway.rstrip("/") + "/" + entity
    request = urllib.request.Request(url, headers={"User-Agent": "fetch-nostr-events/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return extract_gateway_event(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and cryptographically verify a public Nostr event."
    )
    parser.add_argument("target", help="note1/nevent1/naddr1 identifier or a URL containing one")
    parser.add_argument("--gateway", default="https://nostr.eu", help="njump-compatible HTTPS gateway")
    parser.add_argument("--timeout", type=float, default=20.0, help="network timeout in seconds")
    parser.add_argument("--content-only", action="store_true", help="print only the signed content")
    parser.add_argument("--no-nak", action="store_true", help="skip nak even when it is installed")
    args = parser.parse_args()

    try:
        entity = extract_entity(args.target)
        event = None
        source = None
        nak_error = None
        if not args.no_nak and shutil.which("nak"):
            try:
                event = fetch_with_nak(entity, args.timeout)
                source = "nak"
            except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
                nak_error = str(error)
        if event is None:
            event = fetch_with_gateway(entity, args.gateway, args.timeout)
            source = args.gateway
        validate_event(event)
    except (KeyError, ValueError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"verified event {event['id']} fetched via {source}", file=sys.stderr)
    if nak_error:
        print(f"note: nak failed, gateway fallback succeeded: {nak_error}", file=sys.stderr)
    if args.content_only:
        print(event["content"])
    else:
        json.dump(event, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
