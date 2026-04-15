# OpenClaw Server Config (repository-controlled)

Version-controlled mirror of the four agents that participate in the
`requirement-workflow-feishu` pipeline. Out-of-scope agents on the server
(`ai-ops-router`, `ai-investment-assistant`, `main`, `acp`, `claude`, `codex`)
are intentionally **not** tracked here and are left untouched by the sync.

## What's in this directory

```
deploy/openclaw/
├── openclaw.json.template              # server-wide config (redacted)
├── agents/<agent-id>/models.json.template
├── workspace/agents/<agent-id>/
│   ├── IDENTITY.md / SOUL.md / AGENTS.md / TOOLS.md / USER.md / BOOTSTRAP.md
│   └── SKILL.md                        # symlink → docs/agents/<skill-name>/SKILL.md
└── .gitignore                          # blocks any rendered (secret-bearing) artifact
```

### Single source of truth for SKILL.md

`workspace/agents/<agent-id>/SKILL.md` is a **symlink** into
`docs/agents/<skill-name>/SKILL.md`. The canonical skill library lives in
`docs/agents/`; this directory only references it.

Agent id ↔ skill name:

| agent id              | skill name            |
|-----------------------|-----------------------|
| `ai-founder-brief`    | `requirement-author`  |
| `ai-meeting-closeout` | `requirement-reviewer`|
| `spec-author`         | `spec-author`         |
| `spec-reviewer`       | `spec-reviewer`       |

The sync script dereferences the symlink on push and writes the same content
to **both** remote paths:

- `~/.openclaw/skills/<skill-name>/SKILL.md`     — library entry
- `~/.openclaw/workspace/agents/<agent-id>/SKILL.md` — runtime copy (the one
  OpenClaw actually loads)

Keeping these two in parity is a hard requirement — see
`memory/reference_openclaw_skill_dual_sync.md`.

## Secrets — do NOT commit

`openclaw.json` and `agents/*/models.json` contain API keys. Only their
`*.template` counterparts live in the repo. `.gitignore` enforces that
rendered files cannot be committed by accident.

Required env vars for `scripts/sync_openclaw_server.sh`:

| env var                      | sourced from                                 |
|------------------------------|----------------------------------------------|
| `MINIMAX_API_KEY`            | MiniMax console — anthropic-messages key    |
| `OPENCLAW_NODE_AUTH_TOKEN`   | OpenClaw node auth bearer token              |
| `NANO_BANANA_PRO_API_KEY`    | Google API Console — nano-banana-pro skill  |

Rotate secrets at their respective consoles, then rerun the sync script. The
templates stay untouched.

## Deploy SOP

Run **from this repo on a local trusted machine**. Requires `ssh` access
to `admin@47.251.81.45` and the three env vars above.

```bash
# 1. Preview the rendered tree that would be pushed.
scripts/sync_openclaw_server.sh --dry-run

# 2. Real push (renders, scp/tar-over-ssh, restarts openclaw-gateway.service).
scripts/sync_openclaw_server.sh
```

The script:

1. Renders `*.template` files into a temp dir using environment variables
2. Dereferences `SKILL.md` symlinks so remote files are real copies
3. Mirrors every SKILL.md to both `skills/` and `workspace/agents/<id>/`
4. Pushes via `scp` + `tar | ssh` (rsync is not installed on the remote)
5. Restarts `openclaw-gateway.service` via `systemctl --user restart`
6. Verifies the service is active before exiting

If the script fails mid-push the previous `openclaw.json` is preserved on the
server as `openclaw.json.bak-<timestamp>`.

## Out of scope (intentionally)

- **CI automation.** No GitHub workflow triggers this sync — the remote
  secrets are not in GitHub secrets, and pushing from CI would require
  exporting them. Ops run the script manually for now. Re-evaluate after the
  structure has proven itself through a few real deploys.
- **Other server agents.** Only the four in-scope agents are touched.
- **Backups and runtime state.** `HEARTBEAT.md`, `inbox/`, `drafts/`,
  `confirmed/`, `logs/`, `memory/`, `*.bak-*` are left on the server and
  never pulled into the repo (see `.gitignore`).
