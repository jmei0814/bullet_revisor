#!/usr/bin/env sh
# One-line reset after a new commit:
#   1. build the website  (--build: rebuild the image from the current tree)
#   2. implement the new one  (--force-recreate: replace the running container)
#   3. delete everything that isn't needed  (prune the images/build cache the
#      rebuild just orphaned — dangling only, never touches tagged images/volumes)
#
# Usage:  ./reset.sh            # serve on :8000
#         PORT=9000 ./reset.sh  # serve on :9000
set -eu

docker compose up -d --build --force-recreate --remove-orphans
docker image prune -f
docker builder prune -f

echo "BulletRevisor is up on http://localhost:${PORT:-8000}"
