#!/usr/bin/env bash
# Creates a distributable .dmg from the PyInstaller-produced FlowSnip.app.
#
# Usage (from repo root, after pyinstaller has run):
#   bash installer/macos/create_dmg.sh <version> <arch>
#   e.g. bash installer/macos/create_dmg.sh 1.0.0 arm64
#
# Produces: dist/FlowSnip-<version>-macos-<arch>.dmg

set -euo pipefail

VERSION="${1:?Usage: create_dmg.sh <version> <arch>}"
ARCH="${2:?Usage: create_dmg.sh <version> <arch>}"

APP_NAME="FlowSnip"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="${APP_NAME}-${VERSION}-macos-${ARCH}.dmg"
DMG_PATH="dist/${DMG_NAME}"
STAGING="dist/dmg_staging"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: ${APP_PATH} not found - run pyinstaller first." >&2
  exit 1
fi

# TODO: code signing - uncomment and fill in when an Apple Developer cert is available
# codesign --deep --force --verify --verbose \
#   --sign "Developer ID Application: <Name> (<Team ID>)" \
#   "${APP_PATH}"

echo "Creating staging area…"
rm -rf "${STAGING}"
mkdir -p "${STAGING}"
cp -R "${APP_PATH}" "${STAGING}/"
ln -s /Applications "${STAGING}/Applications"

echo "Building DMG…"
hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${STAGING}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

rm -rf "${STAGING}"

# TODO: notarization - uncomment when Apple Developer credentials are available
# xcrun notarytool submit "${DMG_PATH}" \
#   --apple-id "<apple-id>" \
#   --password "<app-specific-password>" \
#   --team-id "<team-id>" \
#   --wait
# xcrun stapler staple "${DMG_PATH}"

echo "Created: ${DMG_PATH}"
