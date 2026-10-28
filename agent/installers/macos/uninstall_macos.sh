#!/usr/bin/env bash
# macOS Uninstallation & Restoration Script
# Unloads launchd, reverts DNS settings, and removes Academia Shield artifacts.
set -euo pipefail

echo "==> [Academia Shield] Starting uninstallation on macOS..."

# 1. Disable enforcement and restore DNS
python3 -m agent.cli disable-enforcement || true

# 2. Unload and delete launchd agent
PLIST_PATH="$HOME/Library/LaunchAgents/org.academiashield.agent.plist"
if [[ -f "$PLIST_PATH" ]]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
fi

# 3. Clean up credentials and agent cache
python3 -m agent.cli uninstall || true

# 4. Remove .app from Applications
if [[ -d "/Applications/AcademiaShieldAgent.app" ]]; then
    rm -rf "/Applications/AcademiaShieldAgent.app"
fi

echo "==> [Academia Shield] Uninstallation complete. Network and system settings restored."
