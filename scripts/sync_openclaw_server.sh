#!/usr/bin/env bash
# Sync OpenClaw agent configs from the repo to the remote server.
#
# Usage:
#   scripts/sync_openclaw_server.sh [--dry-run]
#
# Renders *.template files using env vars, then pushes to the remote server
# via `tar | ssh` (rsync is unavailable on the remote). Requires the following
# env vars to be set in the shell that runs this script:
#
#   MINIMAX_API_KEY            - MiniMax anthropic-messages provider key
#   OPENCLAW_NODE_AUTH_TOKEN   - OpenClaw node auth bearer token
#   NANO_BANANA_PRO_API_KEY    - Google API key for nano-banana-pro skill
#
# The six in-scope agents: ai-founder-brief, ai-meeting-closeout,
# spec-author, spec-reviewer, spec-transformer, spec-transformer-reviewer.
# Other agents on the server are left untouched.

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

REMOTE="${OPENCLAW_REMOTE:-admin@47.251.81.45}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/deploy/openclaw"
AGENTS=(ai-founder-brief ai-meeting-closeout plan-author spec-author spec-reviewer spec-transformer spec-transformer-reviewer design-brief-author)

# Agent id → skill name (see reference_openclaw_skill_dual_sync.md).
# Using a case fallback rather than declare -A to stay compatible with bash 3.2
# (default on macOS), where associative arrays are unsupported.
skill_for_agent() {
  case "$1" in
    ai-founder-brief) echo requirement-author ;;
    ai-meeting-closeout) echo requirement-reviewer ;;
    plan-author) echo plan-author ;;
    spec-author) echo spec-author ;;
    spec-reviewer) echo spec-reviewer ;;
    spec-transformer) echo spec-transformer ;;
    spec-transformer-reviewer) echo spec-transformer-reviewer ;;
    design-brief-author) echo design-brief-author ;;
    *) echo "[error] no skill mapping for agent $1" >&2; exit 1 ;;
  esac
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "[error] required env var $name is not set" >&2
    exit 1
  fi
}

require_env MINIMAX_API_KEY
require_env OPENCLAW_NODE_AUTH_TOKEN
require_env NANO_BANANA_PRO_API_KEY

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

echo "[info] staging at ${STAGING}"
echo "[info] remote=${REMOTE}"
if (( DRY_RUN )); then
  echo "[info] dry-run mode — no remote mutations will be performed"
fi

# 1) Render openclaw.json from template (only var substitution — no command eval).
render_template() {
  local src="$1" dst="$2"
  python3 - "$src" "$dst" <<'PY'
import os, re, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8") as f:
    text = f.read()
def sub(m):
    name = m.group(1)
    val = os.environ.get(name)
    if val is None:
        raise SystemExit(f"[error] template references undefined env var ${name}")
    return val
out = re.sub(r"\$\{([A-Z0-9_]+)\}", sub, text)
os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w", encoding="utf-8") as f:
    f.write(out)
PY
}

render_template "${SRC}/openclaw.json.template" "${STAGING}/openclaw.json"

# 2) Per-agent: render models.json and copy workspace md files.
for agent in "${AGENTS[@]}"; do
  render_template \
    "${SRC}/agents/${agent}/models.json.template" \
    "${STAGING}/agents/${agent}/models.json"

  mkdir -p "${STAGING}/workspace/agents/${agent}"
  # Copy plain .md files (non-state, non-backup).
  for md in "${SRC}/workspace/agents/${agent}"/*.md; do
    [[ -f "$md" ]] || continue
    # Dereference SKILL.md symlink so the remote copy is a real file.
    base="$(basename "$md")"
    cp -L "$md" "${STAGING}/workspace/agents/${agent}/${base}"
  done
done

# 3) Verify SKILL.md double-sync parity (skills/ vs workspace/).
#    The remote has two paths that must match: ~/.openclaw/skills/<skill>/SKILL.md
#    and ~/.openclaw/workspace/agents/<agent>/SKILL.md. We push both from the
#    same rendered copy to guarantee parity.
for agent in "${AGENTS[@]}"; do
  skill="$(skill_for_agent "$agent")"
  mkdir -p "${STAGING}/skills/${skill}"
  cp -L "${SRC}/workspace/agents/${agent}/SKILL.md" "${STAGING}/skills/${skill}/SKILL.md"
done

echo "[info] staging tree ready:"
(cd "$STAGING" && find . -type f | sort | sed 's|^\./|  |')

if (( DRY_RUN )); then
  echo "[done] dry-run complete; staging left at ${STAGING} (will be cleaned on exit)"
  exit 0
fi

# 4) Push to remote.
#    Transfer strategy: tar-over-ssh, extract into ~/.openclaw/.
#    We extract into separate subtrees so unrelated agents on the server are
#    not touched.
echo "[info] pushing openclaw.json"
scp -q "${STAGING}/openclaw.json" "${REMOTE}:~/.openclaw/openclaw.json.new"
ssh "${REMOTE}" "mv ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-\$(date +%Y%m%d-%H%M%S) && mv ~/.openclaw/openclaw.json.new ~/.openclaw/openclaw.json"

for agent in "${AGENTS[@]}"; do
  echo "[info] pushing agents/${agent}/agent/models.json"
  ssh "${REMOTE}" "mkdir -p ~/.openclaw/agents/${agent}/agent"
  scp -q "${STAGING}/agents/${agent}/models.json" "${REMOTE}:~/.openclaw/agents/${agent}/agent/models.json"

  echo "[info] pushing workspace/agents/${agent}/*.md"
  ssh "${REMOTE}" "mkdir -p ~/.openclaw/workspace/agents/${agent}"
  (cd "${STAGING}/workspace/agents/${agent}" && tar -cf - *.md) | \
    ssh "${REMOTE}" "cd ~/.openclaw/workspace/agents/${agent} && tar -xf -"

  skill="$(skill_for_agent "$agent")"
  echo "[info] pushing skills/${skill}/SKILL.md (mirror of workspace SKILL.md)"
  ssh "${REMOTE}" "mkdir -p ~/.openclaw/skills/${skill}"
  scp -q "${STAGING}/skills/${skill}/SKILL.md" "${REMOTE}:~/.openclaw/skills/${skill}/SKILL.md"

  # Safety net: models occasionally hallucinate the script path into the
  # agent's own workspace dir (observed with MiniMax-M2.7, 2026-04-24).
  # The canonical copy lives at ~/.openclaw/bin/send_openclaw_callback.py;
  # a symlink in the workspace dir makes both paths work.
  echo "[info] symlinking send_openclaw_callback.py into workspace/agents/${agent}/"
  ssh "${REMOTE}" "ln -sfn /home/admin/.openclaw/bin/send_openclaw_callback.py /home/admin/.openclaw/workspace/agents/${agent}/send_openclaw_callback.py"
done

echo "[info] restarting openclaw-gateway.service"
ssh "${REMOTE}" "systemctl --user restart openclaw-gateway.service && sleep 2 && systemctl --user is-active openclaw-gateway.service"

echo "[done] sync complete"
