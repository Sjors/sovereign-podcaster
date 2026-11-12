# Private executor checkout and source synchronization

An administrator may authorize a maintainer to SSH into the isolated agent account
to install source and run local checks. This does not grant GitHub publication,
podcast-host access or production publishing permission. Use no agent forwarding
and verify the agent machine's SSH host key. Its incoming `authorized_keys` contains
public keys only; do not copy a private key or grant the agent access back into the
maintainer's home. Inbound maintainer access and outbound podcast-host access are
separate grants.

Tools: `sudo apt install --no-install-recommends git openssh-client coreutils`
on the machines where needed. SSH client/server access is assumed already set up
by the operator. If the agent machine needs a new SSH server, its administrator
installs `openssh-server` and configures its access policy separately. Do not enable
password authentication or expose a new listener solely to follow this example.

## Bootstrap before GitHub publication

Use a Git bundle to transfer only committed repository source. This works even if
the isolated account cannot read the maintainer's checkout. Example commands run
from a clean maintainer checkout; change the SSH target, branch and paths for your
installation. Both destination directories must be absent. Leave the transfer
files for diagnosis if an operation fails; remove them after successful validation.

```sh
SP_AGENT=podcaster@agent.example.org
SP_CHECKOUT=/home/podcaster/src/sovereign-podcaster
SP_TRANSFER=$(mktemp -d)
git bundle create "$SP_TRANSFER/source.bundle" master
SP_REMOTE_TRANSFER=$(ssh -o ForwardAgent=no "$SP_AGENT" 'umask 077; mktemp -d')
# These example paths are operator-controlled, absolute paths without shell
# metacharacters. Quote/validate other values before using them in remote commands.
ssh -o ForwardAgent=no "$SP_AGENT" \
  "umask 077; cat > '$SP_REMOTE_TRANSFER/source.bundle'" < "$SP_TRANSFER/source.bundle"
ssh -o ForwardAgent=no "$SP_AGENT" \
  "umask 077; git clone --branch master '$SP_REMOTE_TRANSFER/source.bundle' '$SP_CHECKOUT'"
```

On the agent account, after a successful clone, configure the eventual public
origin with no credential helper and a disabled outbound push URL:

```sh
cd /home/podcaster/src/sovereign-podcaster
git remote set-url origin https://github.com/Sjors/sovereign-podcaster.git
git remote set-url --push origin disabled://read-only
git config --local credential.helper ''
git config --local push.default nothing
git fsck --full
git status --short
```

Compare `git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'` on both machines.
Specifying `--branch master` matters: a bundle containing only `master` may lack the
default HEAD that `git clone` otherwise expects.
The bootstrap transfers the actual maintainer commits, without signing/rewriting
them. Delete only the task-owned transfer directories after validation. GitHub
publication remains the maintainer's separate Mac signing/push workflow.

## Configure an explicitly authorized private push remote

On the maintainer checkout:

```sh
git remote add podcaster podcaster@agent.example.org:/home/podcaster/src/sovereign-podcaster
git config --local remote.podcaster.receivepack \
  'git -c receive.denyCurrentBranch=updateInstead -c receive.denyNonFastForwards=true receive-pack'
git config --local remote.podcaster.mirror false
git -c push.followTags=false push --no-follow-tags --recurse-submodules=no \
  podcaster HEAD:refs/heads/master
```

`updateInstead` updates a clean checked-out branch along with its working files.
Tracked local modifications and conflicting files cause refusal. Server-side
non-fast-forward rejection is enabled for this receive invocation. No persistent
server-wide receive setting, force push, tags or other branch refs are needed.
Inspect both checkouts if a push is refused; preserve executor edits and reconcile
them deliberately. A push is source synchronization, not a production deployment.

Keep GitHub `origin` publication disabled on the Linux maintainer checkout. The
private `podcaster` remote is an explicit exception to the no-GitHub-push rule.
If needed, configure this checkout's `core.sshCommand` locally with the operator's
verified host-key file, administrator identity and `ForwardAgent=no`; do not put
host-specific authentication configuration into tracked files. An administrator
can revoke the temporary inbound public key after deciding how future maintenance
will work. Preserve replacement access before removing existing grants.

## Validate under the isolated UID

Run checks through SSH as the isolated user, with a clean environment and `umask
077`. Keep generated artifacts under the configured artifact root. Run the three
unit tests, build a synthetic review revision, verify its manifest, and inspect
permissions and source/commit hashes. Check that administrator homes, private
backups and authentication files are inaccessible without printing their contents.
Report each check's actual scope; a different UID does not hide world-readable
files or prove complete isolation.

New source files and skills become available through subsequent private pushes.
Only reviewed, license-checked skills belong in this repository; no private skill
tree, chat history or credentials are copied by this workflow. Generated caches,
logs, approval evidence and episode media remain outside the checkout.
