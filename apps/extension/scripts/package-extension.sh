#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
version="$(node -p "require('./package.json').version")"
archive="echoscene-extension-${version}.zip"
rm -f "$archive"
cd dist
zip -qr "../$archive" .
echo "Created apps/extension/$archive"
