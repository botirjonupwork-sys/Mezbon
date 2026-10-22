#!/usr/bin/env bash
set -euo pipefail

echo "== Docker credential helper fixer =="

echo "Looking for docker-credential-desktop in common locations..."
CANDIDATES=(
  "/Applications/Docker.app/Contents/Resources/bin/docker-credential-desktop"
  "/Applications/Docker.app/Contents/Resources/docker-credential-desktop"
  "/opt/homebrew/bin/docker-credential-desktop"
  "/usr/local/bin/docker-credential-desktop"
)

FOUND=""
for p in "${CANDIDATES[@]}"; do
  if [ -x "$p" ]; then
    FOUND="$p"
    break
  fi
done

if [ -n "$FOUND" ]; then
  echo "Found docker-credential-desktop at: $FOUND"
  echo "Creating /usr/local/bin and symlinking (sudo may be required)..."
  sudo mkdir -p /usr/local/bin
  sudo ln -sf "$FOUND" /usr/local/bin/docker-credential-desktop
  sudo chmod +x /usr/local/bin/docker-credential-desktop
  echo "Symlink created: /usr/local/bin/docker-credential-desktop -> $FOUND"
  echo "Now try: docker compose up -d --build"
  exit 0
fi

echo "docker-credential-desktop not found in common locations."
echo "Possible fixes:"
echo "  1) Start Docker Desktop app and re-run this script after it's fully started."
echo "  2) If you installed Docker in a custom location, run:"
echo "       sudo ln -sf /path/to/docker-credential-desktop /usr/local/bin/docker-credential-desktop"
echo "  3) As a temporary workaround you can disable BuildKit for the build:" 
echo "       DOCKER_BUILDKIT=0 docker compose up -d --build"

echo
echo "If you want, open a shell in the project root and run:"
echo "  chmod +x scripts/fix_docker.sh && ./scripts/fix_docker.sh"

exit 0
