#!/usr/bin/env bash
# hermes-edit-config — safely add or update KEY=VALUE in a chattr+i hermes config file.
#
# Background: ~/.hermes/.env, ~/.hermes/config.yaml, and ~/.hermes/webui/settings.json
# are deliberately marked immutable (chattr +i) on nanoclaw-az. Editing them by hand
# requires lifting the immutable bit, editing, restoring the bit.
#
# Background: claw-stack-jp#165 outage (2026-06-03 → 2026-06-12) was caused in part
# by API_SERVER_KEY being missing from .env. The chattr ritual is non-obvious;
# this helper makes it boring + safe.
#
# Usage:
#   hermes-edit-config KEY=VALUE                    # default file ~/.hermes/.env
#   hermes-edit-config --file <path> KEY=VALUE      # explicit target
#   hermes-edit-config --get KEY                    # read-only lookup
#   hermes-edit-config --restart hermes-gateway     # also restart unit after edit
#
# Exit codes:
#   0 OK
#   1 usage error
#   2 file missing / unwritable
#   3 chattr unavailable (non-Linux?)

set -euo pipefail

DEFAULT_FILE="${HOME}/.hermes/.env"
TARGET_FILE="$DEFAULT_FILE"
ACTION="upsert"
RESTART_UNIT=""

usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)   TARGET_FILE="$2"; shift 2 ;;
    --get)    ACTION="get";     KEY="$2"; shift 2 ;;
    --restart) RESTART_UNIT="$2"; shift 2 ;;
    -h|--help) usage ;;
    *=*)      KV="$1"; KEY="${KV%%=*}"; VALUE="${KV#*=}"; shift ;;
    *)        echo "ERROR: unknown arg: $1" >&2; usage ;;
  esac
done

[[ -f "$TARGET_FILE" ]] || { echo "ERROR: target file missing: $TARGET_FILE" >&2; exit 2; }
command -v chattr >/dev/null 2>&1 || { echo "ERROR: chattr not available" >&2; exit 3; }

if [[ "$ACTION" == "get" ]]; then
  # Missing key returns empty, exit 0 (not a script failure).
  set +o pipefail
  grep -E "^${KEY}=" "$TARGET_FILE" | tail -1 | cut -d= -f2-
  set -o pipefail
  exit 0
fi

[[ -n "${KEY:-}" ]] || { echo "ERROR: no KEY=VALUE supplied" >&2; usage; }

BACKUP="${TARGET_FILE}.bak-$(date +%s)"
sudo cp -p "$TARGET_FILE" "$BACKUP"
sudo chattr -i "$TARGET_FILE"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if grep -qE "^${KEY}=" "$TARGET_FILE"; then
  sudo awk -v k="$KEY" -v v="$VALUE" 'BEGIN{FS=OFS="="} $1==k {print k"="v; next} {print}' "$TARGET_FILE" > "$TMP"
  ACTION_TAKEN="updated"
else
  sudo cat "$TARGET_FILE" > "$TMP"
  printf "\n%s=%s\n" "$KEY" "$VALUE" >> "$TMP"
  ACTION_TAKEN="appended"
fi

sudo cp "$TMP" "$TARGET_FILE"
sudo chmod 600 "$TARGET_FILE"
sudo chown "$(stat -c %U "$BACKUP"):$(stat -c %G "$BACKUP")" "$TARGET_FILE"
sudo chattr +i "$TARGET_FILE"

echo "OK ${ACTION_TAKEN} ${KEY} in ${TARGET_FILE} (backup: ${BACKUP})"

if [[ -n "$RESTART_UNIT" ]]; then
  echo "Restarting $RESTART_UNIT..."
  sudo systemctl restart "$RESTART_UNIT"
  sleep 3
  systemctl is-active "$RESTART_UNIT"
fi
