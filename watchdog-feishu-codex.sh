#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${ROOT}/.runtime"
HEARTBEAT_PATH="${RUNTIME_DIR}/heartbeat.json"
LABEL="com.zhengrongwei.feishu-codex-cli"
MAX_AGE_SECONDS="${WATCHDOG_MAX_AGE_SECONDS:-180}"

mkdir -p "${RUNTIME_DIR}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

current_ts="$(date +%s)"
heartbeat_ts=""

if [ -f "${HEARTBEAT_PATH}" ]; then
  heartbeat_ts="$(python3 - <<'PY' "${HEARTBEAT_PATH}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
value = payload.get("timestamp", "")
print(value if isinstance(value, int) else "")
PY
)"
fi

if [ -n "${heartbeat_ts}" ] && [ $((current_ts - heartbeat_ts)) -le "${MAX_AGE_SECONDS}" ]; then
  exit 0
fi

launchctl kickstart -k "gui/$(id -u)/${LABEL}"
echo "$(date '+%Y-%m-%d %H:%M:%S') restarted ${LABEL} because heartbeat is stale" >> "${RUNTIME_DIR}/watchdog.log"
