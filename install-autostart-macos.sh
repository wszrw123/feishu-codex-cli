#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.zhengrongwei.feishu-codex-cli"
WATCHDOG_LABEL="${LABEL}.watchdog"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
WATCHDOG_PLIST_PATH="${LAUNCH_AGENTS_DIR}/${WATCHDOG_LABEL}.plist"
RUNTIME_DIR="${ROOT}/.runtime"

mkdir -p "${LAUNCH_AGENTS_DIR}" "${RUNTIME_DIR}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${ROOT}/start-feishu-codex.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${ROOT}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>

  <key>StandardOutPath</key>
  <string>${RUNTIME_DIR}/launchd.stdout.log</string>

  <key>StandardErrorPath</key>
  <string>${RUNTIME_DIR}/launchd.stderr.log</string>
</dict>
</plist>
EOF

cat > "${WATCHDOG_PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${WATCHDOG_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${ROOT}/watchdog-feishu-codex.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${ROOT}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>60</integer>

  <key>StandardOutPath</key>
  <string>${RUNTIME_DIR}/watchdog.stdout.log</string>

  <key>StandardErrorPath</key>
  <string>${RUNTIME_DIR}/watchdog.stderr.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)/${WATCHDOG_LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl bootstrap "gui/$(id -u)" "${WATCHDOG_PLIST_PATH}"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl enable "gui/$(id -u)/${WATCHDOG_LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${WATCHDOG_LABEL}"

echo "Installed launch agent: ${PLIST_PATH}"
echo "Service label: ${LABEL}"
echo "Installed watchdog agent: ${WATCHDOG_PLIST_PATH}"
echo "Watchdog label: ${WATCHDOG_LABEL}"
