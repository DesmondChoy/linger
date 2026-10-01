#!/usr/bin/env bash
set -euo pipefail

# Checksums from the v0.74.0 release, reviewed with the workflow changes.
version=0.74.0
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) platform=Linux-64bit; checksum=2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a ;;
  Linux-aarch64) platform=Linux-ARM64; checksum=b94ce1976bbf3c15b514b605ee88be7c6d94a29be2302847ff01cb794d47aad5 ;;
  Darwin-arm64) platform=macOS-ARM64; checksum=1caada5e0e2091909357c7525d3aa76f4b660b13821bc143b190c7483e31cc11 ;;
  *) echo 'Unsupported Trivy installation platform' >&2; exit 1 ;;
esac
destination="${1:?Usage: install-trivy.sh DESTINATION}"
mkdir -p "$destination"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
archive="trivy_${version}_${platform}.tar.gz"
curl --fail --silent --show-error --location \
  "https://github.com/aquasecurity/trivy/releases/download/v${version}/${archive}" \
  --output "$temporary/$archive"
printf '%s  %s\n' "$checksum" "$temporary/$archive" | shasum -a 256 --check
tar -xzf "$temporary/$archive" -C "$destination" trivy
"$destination/trivy" --version
