# Authorize an OpenAI project

An OpenAI project ID identifies a project; it is not a login or credential. Create
keys while that project is selected in the Platform dashboard. A project-scoped
key authorizes API calls; the Agents API is not a ChatGPT/Codex sign-in flow.

## One isolated account, two processes and two keys

The selected setup runs the small application/controller and `codex exec-server`
as the **same isolated podcast user**. The controller creates sessions, submits
tasks and follows progress/usage. The executor performs the requested commands.
The maintainer account edits/syncs code only; it holds no OpenAI runtime key and
is not required to trigger normal tasks. No additional Linux user is required.

Create these keys in the same organization/project and under the same user or
service-account identity:

1. **Application key:** create it on [API keys](https://platform.openai.com/api-keys).
   Restrict permissions to `api.agents.read`, `api.agents.write` and
   `api.responses.write`. Other APIs are unnecessary for the first check. Do not
   use an organization admin key. This key is for the local controller.
2. **Environment key:** create it on the
   [Agents environment-key tab](https://platform.openai.com/agents?environment_view=keys&tab=environments).
   It is the restricted executor credential, permitting environment connections;
   leave every other permission None. A general application key is not a substitute.
   If the UI or permissions are unavailable, resolve project/account access before
   relying on a paid test; a credit balance alone does not establish access.

If creating a project service account immediately gives you a key, that is the
application/controller key. Restrict it to the permissions above. Those narrow
permissions do not grant key administration; the documented executor-key creation
path is the Agents environment-key tab. The environment key must have the same
service-account owner, not a personal owner just sharing the project. If the UI
does not offer that owner, resolve the mismatch rather than expanding the
controller's permissions or substituting an unrelated personal key.

Successful session listing/creation does not prove model-inference permission.
The first tested service-account key could create a session and connect its
matching executor, but task submission returned `401` with missing scope
`api.responses.write`. Enable Responses Write on the application key, retaining
Agents read/write; do not broaden the restricted environment key. Retry the same
saved submission only after inspecting whether any turn was actually created.
In the key editor, expand the collapsed **Model capabilities** row to find the
Responses endpoint permission. **Agents → Write** alone is insufficient; the
separate **Prompts → Write** permission is not needed by this inline smoke task.

The key editor can warn that permission changes take a few minutes to apply.
Wait before retrying; do not repeatedly broaden permissions when the key details
already show the required scopes. Verify privately that the saved application key
matches the dashboard entry, and inspect the session's turns before resubmitting.
The [RBAC documentation](https://developers.openai.com/api/docs/guides/rbac) allows
up to 30 minutes for role changes/group sync; it does not establish a timing
guarantee for editing an API key's scopes.
If the rejection persists after propagation, check the service account's project
role and organization/project restrictions: key scopes cannot grant permissions
outside that role. The official [service-account guidance](https://developers.openai.com/api/docs/guides/terraform/service-accounts)
describes this intersection. Keep the environment key restricted throughout.
The initial check eventually passed with the displayed Agents/Responses scopes;
the setup did not widen the service account's role or environment-key permissions.
The transient rejection alone did not establish that a role change was needed.

These roles and permissions follow the official
[self-hosted executor instructions](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted).
The executor gets the environment key as `CODEX_API_KEY`; it is not given the
application key as an environment variable. Under one UID, however, executor code
can still read that UID's application-key file. Separate processes/keys do not
isolate files from each other. An enforced filesystem/process sandbox or a separate
controller environment would be needed to protect it from arbitrary executor code.
The current setup preserves isolation from the operator's other Linux account.
Temporary maintainer SSH access used for bootstrap is still a privileged path
into the isolated account. Restrict/revoke it after replacement maintenance access
is validated; a separate UID does not block an explicitly authorized SSH key.
Source updates also remain trusted code, even when synchronized by Git.

## Save directly as the isolated user

Do not send either key through the maintainer account, chat, shell arguments or
history. From the isolated user's interactive terminal:

```sh
umask 077
SP_REPO="$HOME/src/sovereign-podcaster"
python3 "$SP_REPO/adapters/openai-agents/save-key.py" \
  "$HOME/.config/sovereign-podcaster/openai/application.key"
python3 "$SP_REPO/adapters/openai-agents/save-key.py" \
  "$HOME/.config/sovereign-podcaster/openai/environment.key"
```

Each command prompts for hidden input. Paste the matching key only at that prompt.
The helper refuses overwrites, repository destinations and noninteractive input;
it writes an owner-only directory/file (0700/0600). Never print the files to verify
them. Check ownership/modes or report that saving succeeded. The controller can
read application.key directly and pass only environment.key to the executor.

## Runtime and first test

System dependencies on the Ubuntu agent machine:

```sh
sudo apt install --no-install-recommends python3 ca-certificates nodejs node-corepack
```

The official instructions install `@openai/codex@alpha`. For reproduction, use the
version that passed this setup's live check, with an isolated user-owned prefix:

```sh
corepack npm install --global --prefix "$HOME/.local" @openai/codex@0.166.0-alpha.6
"$HOME/.local/bin/codex" --version
"$HOME/.local/bin/codex" exec-server --help
```

The inspected Ubuntu 26.04.1 installation resolved to `0.166.0-alpha.6`. It passed
version/help checks, a live restricted-key executor connection and the read-only
YouTube check with `gpt-6.1-sol`. Its
installer warned that the selected npm 12 expects a newer Node patch than the
installed Node 22.22.1; installation completed and the executor binary ran. Pin
the successfully live-tested executor version when recording a reproducible setup.

The first authorized task is only to run the existing YouTube helper's `check`
command, using private instance paths, and report the expected channel ID. It must
not read credential JSON into model context or mutate videos/playlists. Keep the
session ID, executor environment ID/URL, safe progress/result and usage outside
the source checkout. Stop the executor after this bounded test and inspect actual
turn/tool outcomes and recorded usage.

Use the Agents API for this test. Current
[credit documentation](https://developers.openai.com/api/docs/guides/chatgpt-api-credits)
covers that API with eligible linked API credits and explicitly excludes ordinary
API-key-authenticated Codex usage from the subscription credit benefit. Record the
actual credit grant/expiry and project limits separately; a user-reported balance
has not been verified by this setup. Dashboard usage/billing is authoritative;
recorded session tokens are best-effort, not an invoice. Project budgets should
not be assumed to provide a hard per-run spending cap.

The current reference also describes a `spend_control` session field in USD cents,
but the tested `agents=v1` endpoint rejected it as `unknown_parameter` before
creating a session. The smoke command keeps a spending-limit request as its
default and requires an explicit `--without-server-spend-limit` option to omit it.
The operator explicitly authorized one timeout-only check without a hard dollar
cap. A timeout is not a spending cap; do not silently switch modes for future runs.
The reported free balance and disabled top-up were operator-provided information,
not verified by the application key.

## Usage visibility and independent spending controls

Official documentation checked 2026-11-01 distinguishes three surfaces:

- **Recorded tokens:** the existing Agents read permission can retrieve session
  and turn `usage`; no additional billing privilege is needed. Counts can arrive
  later or change, and missing usage means unknown. Include failed/retried work
  and delegated turns when relevant; do not add session totals to their own turn
  totals. Token counts are not an invoice. See
  [observability and usage](https://developers.openai.com/api/docs/guides/agents-api/observability).
- **Dashboard dollar totals:** the documented
  [Costs endpoint](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs)
  is `GET /v1/organization/costs`, authenticated with a separate Admin API key.
  It supports project filters and daily cost buckets. Filtering a query to a
  project does not restrict what that credential can access. The
  [Admin API guide](https://developers.openai.com/api/docs/guides/admin-apis)
  establishes separate administrative authentication; it does not establish a
  project-only, costs-only credential for this service account. Do not provision
  a broad admin credential merely for telemetry. Continue using the dashboard
  unless a suitably restricted read-only route is verified for the account.
- **Session spending controls:** the
  [Ruby session reference](https://developers.openai.com/api/reference/ruby/resources/beta/subresources/agents/subresources/sessions/methods/create)
  describes `spend_control.limit` in USD cents, scoped to the session, rather
  than each incoming message. Documentation surfaces differ, and the tested
  endpoint rejected this field with `unknown_parameter`. That is not evidence
  of a missing key scope. Do not expand permissions to fix it, and do not claim
  enforcement until an authorized compatibility test confirms acceptance and
  the returned limit. A timeout remains distinct from a dollar limit.

The current [spend-limit guide](https://developers.openai.com/api/docs/guides/spend-limits)
explicitly documents monthly project and organization hard limits, alongside
notification-only spend alerts. An operator can configure Project settings →
Limits → Spend → Edit spend limit and enable **Enforce a hard limit**. Both
organization and project caps can apply; enforcement propagation can allow a
small overshoot. This is documentation, not confirmation that a particular cap
is configured on this account. The guide does not establish a native daily cap.

Keep organization/project limit administration separate from the application's
Agents read/write permission. The controller must not receive authority to
raise/remove the operator's overall caps. A future working session cap would be
an additional constraint, not permission to override those caps. A local daily
usage ledger can provide a stop policy, but delayed accounting and controller
access to its own code/state mean it is not an independent server-enforced cap.
No credentials, roles or production limits were changed for this documentation.
