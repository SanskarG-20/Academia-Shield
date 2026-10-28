#!/usr/bin/env bash
# macOS .pkg Installer Builder using pkgbuild & productbuild
set -euo pipefail

APP_NAME="AcademiaShieldAgent.app"
APP_SRC="dist/${APP_NAME}"
PKG_NAME="dist/AcademiaShieldAgent.pkg"
IDENTIFIER="org.academiashield.agent"
VERSION="2.3.0"

echo "==> Building macOS Installer Package: ${PKG_NAME}"

mkdir -p dist/pkg_root/Applications
cp -R "${APP_SRC}" dist/pkg_root/Applications/

pkgbuild --root dist/pkg_root \
         --identifier "${IDENTIFIER}" \
         --version "${VERSION}" \
         --install-location "/" \
         dist/AcademiaShieldAgent-component.pkg

productbuild --package dist/AcademiaShieldAgent-component.pkg \
             "${PKG_NAME}"

echo "==> macOS Installer .pkg created successfully at ${PKG_NAME}"
