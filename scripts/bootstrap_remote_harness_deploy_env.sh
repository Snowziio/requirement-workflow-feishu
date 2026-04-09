#!/usr/bin/env bash
set -euo pipefail

REMOTE="${1:-admin@47.251.81.45}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

ssh -o BatchMode=yes "$REMOTE" 'mkdir -p ~/deploy/customers ~/customers'
scp -o BatchMode=yes "$REPO_ROOT/deploy/deploy.sh" "$REMOTE:~/deploy/deploy.sh"
scp -o BatchMode=yes "$REPO_ROOT/deploy/customers/example.env.template" "$REMOTE:~/deploy/customers/example.env.template"
ssh -o BatchMode=yes "$REMOTE" 'chmod +x ~/deploy/deploy.sh'

echo "Remote harness deploy environment prepared on $REMOTE"
