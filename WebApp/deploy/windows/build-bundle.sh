#!/usr/bin/env bash
# Builds the offline Windows bundle: one folder that, copied to a USB drive,
# installs KANAT on a Windows 10/11 PC with no internet (install.ps1).
#
#   WebApp/deploy/windows/build-bundle.sh [version]      (default: today, 2026.10.25)
#   KANAT_GPU=1 WebApp/deploy/windows/build-bundle.sh    also the CUDA image (+4 GB)
#
# Run on a Mac or Linux PC with internet, Docker (with buildx) and Node: it
# downloads the Windows installers (each checked against its pinned SHA-256),
# builds the backend and Detection Service images for x64 Windows PCs and the
# KANAT app's installer. No data goes in: the SQLite database starts empty on the PC.
#
# The Detection Service runs on the CPU. With KANAT_GPU=1 the bundle also
# carries its CUDA image, which install.ps1 runs on a PC where Docker can use
# an NVIDIA GPU.
#
# Output: $KANAT_BUNDLE_DIR (default ~/KanatBundle)/KANAT-<version>/ (about
# 2.5 GB, 6.5 GB with the GPU image) and KANAT-<version>.zip of it, to copy
# to a USB drive (exFAT or NTFS) and extract on the PC. Downloads are kept in
# ~/KanatBundle/downloads for the next build.
set -euo pipefail

VERSION="${1:-$(date +%Y.%m.%d)}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ROOT="${KANAT_BUNDLE_DIR:-$HOME/KanatBundle}"
CACHE="$ROOT/downloads"
OUT="$ROOT/KANAT-$VERSION"
PLATFORM=linux/amd64

# Pinned: each at least two weeks old when chosen, its hash the publisher's own
DOCKER_DESKTOP_URL="https://desktop.docker.com/win/main/amd64/241994/Docker%20Desktop%20Installer.exe"   # 4.94.0
DOCKER_DESKTOP_SHA=a9814e31049d66156477a86614e83365669677733014ec72f74229623ff3890a
WSL_URL="https://github.com/microsoft/WSL/releases/download/2.7.14/wsl.2.7.14.0.x64.msi"
WSL_SHA=db084e536279a59e90a26ec598d8aa8a4dff8309f41d078fd06242953ac1ebcd
GSTREAMER_URL="https://gstreamer.freedesktop.org/data/pkg/windows/1.28.8/msvc/gstreamer-1.0-msvc-x86_64-1.28.8.exe"
GSTREAMER_SHA=e4c41ee6ee9c6c32a45d198463ec08d79bac3bd5fa58adc93d13fe4a08abc9d9
MEDIAMTX_URL="https://github.com/bluenviron/mediamtx/releases/download/v1.21.2/mediamtx_v1.21.2_windows_amd64.zip"
MEDIAMTX_SHA=a84224f5a490855684e62ba6fb71e80ea2a5e16aed61883bb58380290e93e467
CUDA_TORCH_INDEX=https://download.pytorch.org/whl/cu126

say() { printf '\n==> %s\n' "$*"; }

# download <url> <sha256> <file name>: into the cache, once, checked every time
download() {
  local file="$CACHE/$3"
  if [[ ! -f "$file" ]]; then
    curl -fL --progress-bar -o "$file.part" "$1"
    mv "$file.part" "$file"
  fi
  echo "$2  $file" | shasum -a 256 -c --quiet - || { echo "checksum mismatch: $file" >&2; exit 1; }
}

mkdir -p "$CACHE"
if [[ -e "$OUT" ]]; then
  echo "$OUT already exists: remove it or give another version" >&2
  exit 1
fi
mkdir -p "$OUT/installers" "$OUT/images" "$OUT/app/WebApp" "$OUT/app/VideoService"
echo "$VERSION" > "$OUT/VERSION"

say "Installers"
download "$DOCKER_DESKTOP_URL" $DOCKER_DESKTOP_SHA "Docker Desktop Installer.exe"
download "$WSL_URL" $WSL_SHA "$(basename "$WSL_URL")"
download "$GSTREAMER_URL" $GSTREAMER_SHA "$(basename "$GSTREAMER_URL")"
download "$MEDIAMTX_URL" $MEDIAMTX_SHA "$(basename "$MEDIAMTX_URL")"
cp "$CACHE/Docker Desktop Installer.exe" "$CACHE/$(basename "$WSL_URL")" "$CACHE/$(basename "$GSTREAMER_URL")" "$OUT/installers/"

say "The KANAT app's installer"
(cd "$REPO/WebApp/frontend" && npm ci --no-audit --no-fund && npm run dist:win)
cp "$REPO"/WebApp/frontend/release/KANAT-Setup-*.exe "$OUT/installers/"

say "KANAT's images, for $PLATFORM"
build() {   # build <tag> <context> [build args...]
  local tag=$1 context=$2; shift 2
  docker buildx build --platform $PLATFORM "$@" -t "$tag" \
    --output "type=docker,dest=$OUT/images/${tag//[:\/]/_}.tar" "$context"
}
build "kanat-backend:$VERSION" "$REPO/WebApp/backend"
build "kanat-detection:$VERSION" "$REPO/ImageRecognitionService"
if [[ "${KANAT_GPU:-0}" == 1 ]]; then
  build "kanat-detection:$VERSION-cuda" "$REPO/ImageRecognitionService" --build-arg TORCH_INDEX=$CUDA_TORCH_INDEX
fi

say "MediaMTX, VideoService and the WebApp's configuration"
unzip -q -o "$CACHE/$(basename "$MEDIAMTX_URL")" mediamtx.exe -d "$OUT/app/VideoService"
cp "$REPO/VideoService/mediamtx.yml" "$REPO/VideoService/run_record.ps1" "$REPO/VideoService/LICENSE" "$OUT/app/VideoService/"
cp "$REPO/WebApp/docker-compose.yml" "$REPO/WebApp/docker-compose.gpu.yml" "$REPO/WebApp/.env.example" "$OUT/app/WebApp/"
cp "$REPO/WebApp/deploy/windows/install.ps1" "$REPO/WebApp/deploy/windows/README.md" "$OUT/"

say "Checksums"
(cd "$OUT" && find . -type f ! -name SHA256SUMS.txt ! -name .DS_Store -print0 | sort -z | xargs -0 shasum -a 256 > SHA256SUMS.txt)

say "Zip"
# The images' layers and the installers are compressed already, so this
# saves little; it makes one file to copy
(cd "$ROOT" && rm -f "KANAT-$VERSION.zip" && zip -q -r -X "KANAT-$VERSION.zip" "KANAT-$VERSION" -x "*.DS_Store")

say "Done: $OUT ($(du -sh "$OUT" | cut -f1)), $ROOT/KANAT-$VERSION.zip ($(du -h "$ROOT/KANAT-$VERSION.zip" | cut -f1))"
