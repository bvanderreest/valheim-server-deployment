# Security

This repository is **public** — it is mirrored from Gitea to
`github.com/bvanderreest/valheim-server-deployment`. Anything committed here is
published, including anything committed in the past.

## Known exposure: server password in git history

**Status: unresolved — requires an operator decision.**

Commits predating the introduction of `.env` hard-coded the live Valheim server
password in `config.conf`, `config.sh` and `valheim-server-manager.sh`. It appears
in **54 commits**.

It is **not** in the current tree, so browsing the repository does not reveal it —
but `git log -p`, GitHub's commit view, and any clone do.

**Recommended response: rotate the password, do not rewrite history.**

A published secret cannot be un-published. Rewriting history with `git filter-repo`
and force-pushing is disruptive (it breaks every existing clone) and incomplete —
GitHub retains orphaned commit objects that stay reachable by SHA until support
purges them. Rotating the credential makes the leaked value worthless, which is the
only outcome fully under your control.

To rotate:

```bash
# on the server host
sed -i 's/^PASSWORD=.*/PASSWORD="<new-password>"/' .env
sudo systemctl restart valheim-server
./valheim-server-manager.sh stats     # confirm, then tell the players
```

Note the password change invalidates the one every current player has.

## Where secrets actually live

| Kind | Location | Notes |
|---|---|---|
| Server password, API keys | `.env` on the host | gitignored, `chmod 600`, **never committed** |
| API key of record | Infisical `/games/VALHEIM_API_KEY` | source of truth |
| Host SSH credentials | Infisical `/games/vdrgaming-ssh-*` | never written to disk in a workspace |
| Example values only | `env.example` | placeholders, safe to commit |

`.env` is untracked and gitignored. Verified: the current API key appears **zero**
times in git history.

## The guard

`scripts/check-secrets.sh` refuses to commit secret-shaped content. Install it:

```bash
ln -sf ../../scripts/check-secrets.sh .git/hooks/pre-commit
```

It blocks files that must never be tracked (`.env`, `*.pem`, private keys) and
credential-shaped assignments, while allowing documented placeholders. It prints
only the key name, never the value. Run it in CI as well as locally — a hook only
protects the machine it is installed on.

## Reporting

Open an issue with the `security` label, or contact the maintainer directly if the
issue is exploitable.
