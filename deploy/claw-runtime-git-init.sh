#!/usr/bin/env bash
# claw-runtime-git-init.sh — one-shot bootstrap that turns /home/slimslimchan/claw
# into a tracked git repo so every edit to mcp-server.py (and the other ~25
# high-blast-radius tool fronts) leaves an audit trail.
#
# Idempotent: re-running on an already-initialised tree is a no-op.
# Run as the slimslimchan user on nanoclaw-az (NOT as root).
#
# Usage:
#   bash deploy/claw-runtime-git-init.sh
#
# Post-run, the operator picks the private repo name and wires the remote:
#   git -C /home/slimslimchan/claw remote add origin <TODO-set-remote>
#   git -C /home/slimslimchan/claw push -u origin main
#
# Tracks: zenc-cp/zenops#1
set -euo pipefail

CLAW_DIR="${CLAW_DIR:-/home/slimslimchan/claw}"

if [[ ! -d "${CLAW_DIR}" ]]; then
  echo "ERROR: ${CLAW_DIR} does not exist" >&2
  exit 1
fi

cd "${CLAW_DIR}"

if [[ ! -d .git ]]; then
  echo "[init] git init -b main in ${CLAW_DIR}"
  git init -b main >/dev/null
else
  echo "[init] ${CLAW_DIR}/.git already present — skipping git init"
fi

GITIGNORE_MARK="# managed-by: claw-runtime-git-init.sh"
if [[ ! -f .gitignore ]] || ! grep -qF "${GITIGNORE_MARK}" .gitignore; then
  echo "[init] writing .gitignore"
  cat > .gitignore <<EOF
${GITIGNORE_MARK}
# Python
*.pyc
__pycache__/
.venv/
venv/

# Secrets / env
.env
.env.*
*.secret

# Runtime artifacts
*.log
tmp/
output/
*.pid
*.sock
EOF
else
  echo "[init] .gitignore already managed — leaving as-is"
fi

git add -A

if git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "[init] repo already has commits — skipping initial commit"
else
  echo "[init] creating initial commit"
  GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-slimslimchan}" \
  GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-slimslimchan@nanoclaw-az.local}" \
  GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-slimslimchan}" \
  GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-slimslimchan@nanoclaw-az.local}" \
    git commit -m "chore: import /home/slimslimchan/claw runtime (zenops#1)" >/dev/null
fi

cat <<'NEXT'

[ok] /home/slimslimchan/claw is now a tracked git repo.

Next steps (operator picks the private repo name):
  git -C /home/slimslimchan/claw remote add origin <TODO-set-remote>
  git -C /home/slimslimchan/claw push -u origin main

Then install the pre-commit hook and drift watchdog:
  cp deploy/claw-runtime-pre-commit-hook.sh \
     /home/slimslimchan/claw/.git/hooks/pre-commit
  chmod +x /home/slimslimchan/claw/.git/hooks/pre-commit

See deploy/RUNBOOK-claw-runtime.md for the full sequence.
NEXT
