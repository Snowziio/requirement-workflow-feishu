#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <harness_scaffold_dir> <target_repo_dir>"
  exit 1
fi

HARNESS_SCAFFOLD_DIR="$1"
TARGET_REPO_DIR="$2"
SOURCE_REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$HARNESS_SCAFFOLD_DIR" ]]; then
  echo "Harness scaffold directory not found: $HARNESS_SCAFFOLD_DIR"
  exit 1
fi

mkdir -p "$TARGET_REPO_DIR"

rsync -a --delete \
  --exclude ".git" \
  --exclude ".github/workflows/*" \
  --exclude "services/checkpoint-handler" \
  "$HARNESS_SCAFFOLD_DIR"/ "$TARGET_REPO_DIR"/

mkdir -p "$TARGET_REPO_DIR/services"
mkdir -p "$TARGET_REPO_DIR/src"
mkdir -p "$TARGET_REPO_DIR/docs"
mkdir -p "$TARGET_REPO_DIR/docker"
mkdir -p "$TARGET_REPO_DIR/deploy/customers"

rsync -a "$SOURCE_REPO_DIR/services/coordinator-service/" "$TARGET_REPO_DIR/services/coordinator-service/"
rsync -a "$SOURCE_REPO_DIR/src/requirement_workflow_v12/" "$TARGET_REPO_DIR/src/requirement_workflow_v12/"
rsync -a "$SOURCE_REPO_DIR/docs/" "$TARGET_REPO_DIR/docs/"
rsync -a "$SOURCE_REPO_DIR/docker/" "$TARGET_REPO_DIR/docker/"
rsync -a "$SOURCE_REPO_DIR/deploy/customers/" "$TARGET_REPO_DIR/deploy/customers/"
rsync -a "$SOURCE_REPO_DIR/.github/workflows/" "$TARGET_REPO_DIR/.github/workflows/"

cp "$SOURCE_REPO_DIR/README.md" "$TARGET_REPO_DIR/README.md"
cp "$SOURCE_REPO_DIR/requirements.txt" "$TARGET_REPO_DIR/requirements.txt"

echo "Bootstrap completed: $TARGET_REPO_DIR"
echo "Next steps:"
echo "  1. cd $TARGET_REPO_DIR"
echo "  2. git init"
echo "  3. git remote add origin <new-repo-url>"
echo "  4. configure GitHub secrets for deploy-coordinator-service.yml"
