#!/usr/bin/env bash
# macOS Developer ID Signing, Hardened Runtime, and Notarization Workflow
set -euo pipefail

APP_PATH="${1:-dist/AcademiaShieldAgent.app}"
IDENTITY_APP="${DEVELOPER_ID_APP:-Developer ID Application: Academia Shield Inc (TEAMID1234)}"
IDENTITY_INSTALLER="${DEVELOPER_ID_INSTALLER:-Developer ID Installer: Academia Shield Inc (TEAMID1234)}"
ENTITLEMENTS="agent/platforms/macos/swift_helper/AcademiaShieldExtension.entitlements"

echo "==> Signing macOS Application Bundle: ${APP_PATH}"

codesign --deep --force --verify --verbose \
    --options runtime \
    --entitlements "${ENTITLEMENTS}" \
    --sign "${IDENTITY_APP}" \
    "${APP_PATH}"

echo "==> Verifying codesign signature..."
codesign -vvv --deep --strict "${APP_PATH}"

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_ID_PASSWORD:-}" && -n "${TEAM_ID:-}" ]]; then
    echo "==> Packaging DMG/ZIP for Notarization..."
    ZIP_PATH="dist/AcademiaShieldAgent.zip"
    ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"

    echo "==> Submitting to Apple Notary Service via notarytool..."
    xcrun notarytool submit "${ZIP_PATH}" \
        --apple-id "${APPLE_ID}" \
        --password "${APPLE_ID_PASSWORD}" \
        --team-id "${TEAM_ID}" \
        --wait

    echo "==> Stapling notarization ticket to .app..."
    xcrun stapler staple "${APP_PATH}"
else
    echo "==> Notarization credentials not configured in environment. Skipping notary submission (Development Mode)."
fi
