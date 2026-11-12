# Autonomous chapter workflow: local validation

Validated locally on 2026-11-03 with Python 3.14, FFmpeg and PHP 8.5.4. The PHP
CLI/common packages were extracted under a temporary directory for testing;
nothing was installed into the isolated executor or hosting service. The
native Castopod interface was inspected in the local 1.15.6 source checkout.

All 183 Python tests passed across:

```sh
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s adapters/openai-agents -p 'test_*.py' -q
python3 -m unittest discover -s skills/castopod-publishing/tests -q
```

The groups ran 87, 68 and 28 tests respectively. PHP helper tests require a PHP
CLI with POSIX support; `PHP_TEST_COMMAND` can select it as a JSON argv list.
All three real-helper entry-point tests ran with synthetic Castopod models,
without a database, SSH or hosting writes. PHP lint passed for the complete
helper cohort and the synthetic model fixture. The existing PHP episode-lock
regression passed contention, independent targets and lock release.

Chapter coverage includes authenticated single-episode intake/routing,
maintenance/source pauses, canonical exports and legacy-list removal, original
Markdown/CRLF preservation, real synthetic-audio decoding and clock derivation,
bounded recognizer receipts, required agent review, native chapter/description
attachment, public JSON/RSS verification, deterministic completion text,
intervening edits, changed sources/destinations, retained unknown outcomes and
read-only recovery without repeating recognition or publication.

Recognition results and public transports are synthetic fixtures. This does not
claim a live Whisper chapter run, Castopod production acceptance, Marmot phone
delivery or podcast-app uptake. Those checks remain pending the owner's first
explicit episode command after deployment. This initial validation respected the
rollout hold: no deployment, service restarts, production task messages, episode
queue or public metadata changes were performed. Instance rollout is separate
from these synthetic validation results; keep live deployment evidence private.

Follow-up local checks for selected published-source intake passed 194 tests
(96 core, 70 adapter, 28 publishing/helper tests), including existing-hold and
changed-audio refusal. These counts precede live deployment acceptance.

The marker-free description generator and explicit HTML content negotiation then
passed 196 local tests (98 core, 70 adapter, 28 publishing/helper tests). Coverage
includes migrating old comment delimiters, rejecting visible escaped markers and
requesting HTML explicitly for public page verification.
