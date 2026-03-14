#!/bin/bash
set -euo pipefail

LABEL="com.zhengrongwei.feishu-codex-cli"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
rm -f "${PLIST_PATH}"

echo "Removed launch agent: ${PLIST_PATH}"
