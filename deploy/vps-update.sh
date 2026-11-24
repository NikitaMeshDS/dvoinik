#!/usr/bin/env bash
# Installed outside the checkout. Nothing is deployed until GitHub promotes a revision.
set -euo pipefail
umask 077

state=/var/lib/dvoinik-cd
repo=https://github.com/NikitaMeshDS/dvoinik.git
ref=refs/heads/deploy/vps
env_file=/etc/dvoinik/runtime.active.env
volume=dvoinik-misisx-data

install -d -m 700 "$state" "$state/backups"
exec 9>"$state/lock"
flock -n 9 || exit 0

result=$(git ls-remote "$repo" "$ref")
[[ -n "$result" ]] || { echo "No tested revision has been promoted yet."; exit 0; }
sha=${result%%$'\t'*}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
running=$(docker inspect -f '{{if .State.Running}}{{index .Config.Labels "org.opencontainers.image.revision"}}{{end}}' dvoinik)
[[ "$running" != "$sha" ]] || exit 0

origin=$(sed -n 's/^DVOINIK_PUBLIC_ORIGIN=//p' "$env_file")
[[ "$origin" =~ ^https://[a-z0-9.-]+$ ]]
host=${origin#https://}
image="dvoinik:git-$sha"
work=$(mktemp -d "$state/build.XXXXXXXX")
candidate="dvoinik-candidate-${sha:0:12}"
previous="dvoinik-previous-$(date -u +%Y%m%d%H%M%S)"
backup_dir="$state/backups/$previous"
candidate_started=0
promoted=0
replacement_started=0
old_stopped=0
cleanup() {
  local status=$?
  trap - EXIT
  if (( candidate_started )); then
    docker rm -f "$candidate" >/dev/null 2>&1 || true
  fi
  if (( status != 0 && promoted )); then
    echo "Deployment failed; restoring $previous." >&2
    if (( replacement_started )); then
      docker rm -f dvoinik >/dev/null 2>&1 || true
    fi
    docker rename "$previous" dvoinik && docker start dvoinik >/dev/null
  elif (( status != 0 && old_stopped )); then
    docker start dvoinik >/dev/null
  fi
  rm -rf -- "$work"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Fetch only the promoted ref. If it moved since ls-remote, try again on the next tick.
git -C "$work" init --quiet
git -C "$work" fetch --quiet --depth=1 "$repo" "$ref"
[[ "$(git -C "$work" rev-parse FETCH_HEAD)" == "$sha" ]]
# Keep the enclosing build directory private, but make image sources readable
# by the unprivileged runtime user after Docker COPY.
(umask 022; git -C "$work" checkout --quiet --detach FETCH_HEAD)

if ! docker image inspect "$image" >/dev/null 2>&1; then
  docker build --label "org.opencontainers.image.revision=$sha" --tag "$image" "$work"
fi
docker run -d --name "$candidate" --network host --no-healthcheck \
  --env-file "$env_file" -e DVOINIK_PORT=8502 \
  --tmpfs /data:uid=10001,gid=10001,mode=0700 "$image" >/dev/null
candidate_started=1

check() {
  local base="$1"
  shift
  local page status
  for _ in {1..20}; do
    if page=$(curl --noproxy '*' -fsS --max-time 3 "$@" "$base/") && [[ "$page" == *'id="root"'* ]]; then
      status=$(curl --noproxy '*' -sS --max-time 3 -o /dev/null -w '%{http_code}' "$@" "$base/api/experiments")
      [[ "$status" == 401 ]] && return 0
    fi
    sleep 1
  done
  return 1
}
if ! check http://127.0.0.1:8502 -H "Host: $host" -H 'X-Forwarded-Proto: https'; then
  docker logs --tail 30 "$candidate" >&2
  exit 1
fi

# Avoid restarting the app if a newer revision was promoted while this image was building.
[[ "$(git ls-remote "$repo" "$ref" | cut -f1)" == "$sha" ]]
test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' dvoinik)" = "$volume"
install -d -m 700 "$backup_dir"
# Online SQLite backup includes committed changes from WAL without copying a live database file.
docker exec -i dvoinik python - > "$backup_dir/experiments.sqlite3.tmp" <<'PY_BACKUP'
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from dvoinik.settings import storage_path

with tempfile.TemporaryDirectory(prefix="dvoinik-cd-") as directory:
    target = Path(directory) / "snapshot.sqlite3"
    with closing(sqlite3.connect(storage_path().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(target)) as snapshot:
            source.backup(snapshot)
    with target.open("rb") as stream:
        shutil.copyfileobj(stream, sys.stdout.buffer)
PY_BACKUP
mv "$backup_dir/experiments.sqlite3.tmp" "$backup_dir/experiments.sqlite3"
test -s "$backup_dir/experiments.sqlite3"
docker stop dvoinik >/dev/null
old_stopped=1
docker rename dvoinik "$previous"
promoted=1
# Set the flag before docker run: Docker may create a container even if starting it fails.
replacement_started=1
docker run -d --name dvoinik --restart unless-stopped --network host --no-healthcheck \
  --env-file "$env_file" -v "$volume:/data" "$image" >/dev/null
check "$origin"
echo "Deployed $sha; rollback container: $previous"
