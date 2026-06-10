#!/usr/bin/env bash
# claw-runtime-pre-commit-hook.sh — guard against _check_auth bypass commits
# in /home/slimslimchan/claw/mcp-server.py (fronts ~25 high-blast-radius MCP
# tools — disabling bearer auth = public unauthenticated RPC).
#
# Detects the exact attack pattern surfaced in the leaked transcript that
# motivated zenc-cp/zenops#1: an edit inside _check_auth whose first executable
# statement is `return True`, `return 1`, or a bare `pass` (i.e. the function
# becomes a no-op that accepts every request).
#
# Mode: ADVISORY (exit 0 with a WARN banner). To upgrade to blocking, change
# the final `exit 0` to `exit 1` in the `block_or_warn` function below — search
# for "UPGRADE-TO-BLOCKING".
#
# Install:
#   cp deploy/claw-runtime-pre-commit-hook.sh \
#      /home/slimslimchan/claw/.git/hooks/pre-commit
#   chmod +x /home/slimslimchan/claw/.git/hooks/pre-commit
#
# Test (without committing):
#   DIFF_OVERRIDE=/tmp/fake.diff bash deploy/claw-runtime-pre-commit-hook.sh
#
# Tracks: zenc-cp/zenops#1
set -euo pipefail

TARGET_FILE="${TARGET_FILE:-mcp-server.py}"
TARGET_FUNC="${TARGET_FUNC:-_check_auth}"

# Allow tests / dry-runs to inject a diff file instead of asking git.
if [[ -n "${DIFF_OVERRIDE:-}" ]]; then
  diff_text="$(cat "${DIFF_OVERRIDE}")"
else
  # Staged diff against HEAD (or empty tree on the initial commit).
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    diff_text="$(git diff --cached --unified=0 -- "${TARGET_FILE}" || true)"
  else
    diff_text="$(git diff --cached --unified=0 --no-index /dev/null "${TARGET_FILE}" || true)"
  fi
fi

if [[ -z "${diff_text}" ]]; then
  exit 0
fi

# Extract just the added lines that fall inside a hunk whose @@ context mentions
# _check_auth, OR added lines following a `+def _check_auth` marker.
suspect_hunk=""
in_target_hunk=0
while IFS= read -r line; do
  case "${line}" in
    @@*)
      if [[ "${line}" == *"${TARGET_FUNC}"* ]]; then
        in_target_hunk=1
      else
        in_target_hunk=0
      fi
      ;;
    "+def ${TARGET_FUNC}"*|"+    def ${TARGET_FUNC}"*|"+  def ${TARGET_FUNC}"*)
      in_target_hunk=1
      ;;
  esac
  if [[ ${in_target_hunk} -eq 1 ]]; then
    suspect_hunk+="${line}"$'\n'
  fi
done <<< "${diff_text}"

if [[ -z "${suspect_hunk}" ]]; then
  exit 0
fi

# Look at *added* lines only (start with '+', not '+++') and scan for the
# first non-blank, non-comment statement. If it matches a bypass pattern, warn.
first_stmt=""
while IFS= read -r line; do
  [[ "${line}" == +++* ]] && continue
  [[ "${line}" != +* ]] && continue
  body="${line#+}"
  trimmed="${body#"${body%%[![:space:]]*}"}"
  [[ -z "${trimmed}" ]] && continue
  [[ "${trimmed}" == \#* ]] && continue
  [[ "${trimmed}" == def\ * ]] && continue
  [[ "${trimmed}" == \"\"\"* ]] && continue
  [[ "${trimmed}" == \'\'\'* ]] && continue
  first_stmt="${trimmed}"
  break
done <<< "${suspect_hunk}"

block_or_warn() {
  local reason="$1"
  cat >&2 <<EOF
================================================================================
 ⚠️  WARN: claw-runtime pre-commit hook flagged a suspicious change
--------------------------------------------------------------------------------
 File      : ${TARGET_FILE}
 Function  : ${TARGET_FUNC}
 Pattern   : ${reason}

 Offending hunk:
$(printf '%s' "${suspect_hunk}" | sed 's/^/   /')

 This looks like a bearer-auth bypass (zenops#1). Review carefully before
 pushing. The hook is currently ADVISORY — commit will proceed.

 To make this BLOCKING, edit the hook and flip the final \`exit 0\` below the
 "UPGRADE-TO-BLOCKING" marker to \`exit 1\`.
================================================================================
EOF
  # UPGRADE-TO-BLOCKING: change the next line to `exit 1` to enforce.
  exit 0
}

case "${first_stmt}" in
  "return True"*)  block_or_warn "first statement in ${TARGET_FUNC} is 'return True'" ;;
  "return 1"*)     block_or_warn "first statement in ${TARGET_FUNC} is 'return 1'" ;;
  "pass"*)         block_or_warn "first statement in ${TARGET_FUNC} is bare 'pass'" ;;
esac

exit 0
