#!/usr/bin/env bash
# claw-runtime-drift-check.sh — alarm if /home/slimslimchan/claw has
# uncommitted changes that have been sitting dirty for longer than the grace
# window (default 15 min). Designed to be fired by a 5-min systemd timer and
# have stdout/stderr captured by journald.
#
# Exit codes:
#   0  — clean tree, OR dirty tree still within grace window
#   2  — dirty tree past grace window (drift alarm)
#   1  — usage / unexpected error
#
# Env:
#   CLAW_DIR           default /home/slimslimchan/claw
#   DRIFT_MAX_MINUTES  default 15
#
# Tracks: zenc-cp/zenops#1
set -euo pipefail

CLAW_DIR="${CLAW_DIR:-/home/slimslimchan/claw}"
DRIFT_MAX_MINUTES="${DRIFT_MAX_MINUTES:-15}"

if [[ ! -d "${CLAW_DIR}/.git" ]]; then
  echo "ERROR: ${CLAW_DIR} is not a git repo — run claw-runtime-git-init.sh first" >&2
  exit 1
fi

cd "${CLAW_DIR}"

porcelain="$(git status --porcelain)"
if [[ -z "${porcelain}" ]]; then
  exit 0
fi

# Find the oldest mtime across the dirty file set.
now_epoch="$(date +%s)"
oldest_epoch="${now_epoch}"
dirty_files=()
while IFS= read -r line; do
  # porcelain format: "XY path" — strip the 2-char status + space.
  path="${line:3}"
  # Handle renames "old -> new" — take the new path.
  if [[ "${path}" == *" -> "* ]]; then
    path="${path##* -> }"
  fi
  # Strip surrounding quotes git emits for paths with special chars.
  path="${path%\"}"
  path="${path#\"}"
  dirty_files+=("${path}")
  if [[ -e "${path}" ]]; then
    file_epoch="$(stat -c %Y -- "${path}" 2>/dev/null || echo "${now_epoch}")"
    if [[ "${file_epoch}" -lt "${oldest_epoch}" ]]; then
      oldest_epoch="${file_epoch}"
    fi
  fi
done <<< "${porcelain}"

age_seconds=$(( now_epoch - oldest_epoch ))
age_minutes=$(( age_seconds / 60 ))

if (( age_minutes < DRIFT_MAX_MINUTES )); then
  # Within grace window — silent.
  exit 0
fi

echo "DRIFT ALARM: ${CLAW_DIR} has uncommitted changes for ${age_minutes}m (threshold ${DRIFT_MAX_MINUTES}m)"
echo "Dirty files:"
for f in "${dirty_files[@]}"; do
  echo "  ${f}"
done
exit 2
