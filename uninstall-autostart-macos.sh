#!/bin/bash
set -euo pipefail

LABEL="com.zhengrongwei.feishu-codex-cli"
WATCHDOG_LABEL="${LABEL}.watchdog"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
WATCHDOG_PLIST_PATH="${HOME}/Library/LaunchAgents/${WATCHDOG_LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/${WATCHDOG_LABEL}" >/dev/null 2>&1 || true
rm -f "${PLIST_PATH}"
rm -f "${WATCHDOG_PLIST_PATH}"

echo "Removed launch agent: ${PLIST_PATH}"
echo "Removed watchdog agent: ${WATCHDOG_PLIST_PATH}"
