#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist/native
for target_os in linux darwin; do
  for target_arch in amd64 arm64; do
    echo "Building $target_os/$target_arch ..."
    CGO_ENABLED=0 GOOS="$target_os" GOARCH="$target_arch" \
      go build -trimpath -ldflags='-s -w' -o "dist/native/ai-$target_os-$target_arch" ./cmd/ai
  done
done
cp install.sh dist/native/install.sh
cd dist/native
if command -v sha256sum >/dev/null; then
  sha256sum ai-* install.sh > SHA256SUMS
else
  shasum -a 256 ai-* install.sh > SHA256SUMS
fi
echo 'Binaries and checksums: dist/native/'
