#!/usr/bin/env bash
# Installed outside the checkout. Nothing is deployed until GitHub promotes a revision.
set -euo pipefail
umask 077

state=/var/lib/dvoinik-cd
repo=https://github.com/NikitaMeshDS/dvoinik.git
ref=refs/heads/deploy/vps
env_file=/etc/dvoinik/runtime.active.env
volume=dvoinik-misisx-data

git_remote() {
  local limit=$1 attempt status output
  shift
  for attempt in 1 2; do
    if output=$(timeout --kill-after=5s "$limit" git "$@"); then
      printf '%s' "$output"
      return 0
    else
      status=$?
    fi
    echo "Git network operation failed (attempt $attempt, exit $status)." >&2
    if (( attempt == 1 )); then sleep 2; fi
  done
  return "$status"
}

install -d -m 700 "$state" "$state/backups"
exec 9>"$state/lock"
flock -n 9 || exit 0

pending="$state/pending"
origin=$(sed -n 's/^DVOINIK_PUBLIC_ORIGIN=//p' "$env_file")
[[ "$origin" =~ ^https://[a-z0-9.-]+$ ]]

lock_jobs() {
  local volume_path
  volume_path=$(docker volume inspect -f '{{.Mountpoint}}' "$volume") || return
  # Keep the inode open through backup, replacement and rollback.
  exec 8<"$volume_path/.deploy-jobs.lock" || return
  flock -n -E 75 8
}

container_id() {
  docker ps -a --no-trunc --filter "name=^/$1$" --format '{{.ID}}'
}

remove_transaction_container() {
  local id=$1 expected=$2 actual
  actual=$(docker container inspect -f '{{index .Config.Labels "io.dvoinik.deploy-attempt"}}' "$id") || return
  if [[ "$actual" != "$expected" ]]; then
    echo "Refusing to remove a container outside the pending deployment." >&2
    return 1
  fi
  docker rm -f "$id" >/dev/null
}

remove_candidate() {
  local token=$1 id
  id=$(container_id "dvoinik-candidate-$token") || return
  [[ -z "$id" ]] || remove_transaction_container "$id" "$token"
}

clear_pending() {
  rm -- "$pending" || return
  sync -f "$state"
}

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

recover_pending() {
  local original token extra live running
  read -r original token extra < "$pending" || return
  if [[ ! "$original" =~ ^[0-9a-f]{64}$ || ! "$token" =~ ^[A-Za-z0-9]{8}$ || -n "$extra" ]]; then
    echo "Invalid pending deployment journal." >&2
    return 1
  fi
  running=$(docker container inspect -f '{{.State.Running}}' "$original") || return
  live=$(container_id dvoinik) || return
  remove_candidate "$token" || return
  if [[ "$live" != "$original" ]]; then
    if [[ -n "$live" ]]; then remove_transaction_container "$live" "$token" || return; fi
    docker rename "$original" dvoinik || return
  fi
  if [[ "$running" != true ]]; then docker start "$original" >/dev/null || return; fi
  check "$origin" || return
  live=$(container_id dvoinik) || return
  running=$(docker container inspect -f '{{.State.Running}}' "$original") || return
  [[ "$live" == "$original" && "$running" == true ]] || return 1
  clear_pending || return
  echo "Recovered the previous container from the pending deployment."
}

if [[ -f "$pending" ]]; then
  if lock_jobs; then
    recover_pending
    exit $?
  else
    status=$?
    if (( status == 75 )); then
      echo "Active research jobs; deferring deployment recovery."
      exit 0
    fi
    exit "$status"
  fi
fi

result=$(git_remote 35s ls-remote "$repo" "$ref") || exit $?
[[ -n "$result" ]] || { echo "No tested revision has been promoted yet."; exit 0; }
sha=${result%%$'\t'*}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]]
running=$(docker inspect -f '{{if .State.Running}}{{index .Config.Labels "org.opencontainers.image.revision"}}{{end}}' dvoinik)
[[ "$running" != "$sha" ]] || exit 0

host=${origin#https://}
image="dvoinik:git-$sha"
work=$(mktemp -d "$state/build.XXXXXXXX")
token=${work##*.}
candidate="dvoinik-candidate-$token"
previous="dvoinik-previous-$(date -u +%Y%m%d%H%M%S)"
backup_dir="$state/backups/$previous"
cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )) && [[ -f "$pending" ]]; then
    recover_pending || echo "Recovery pending; the timer will retry." >&2
  fi
  rm -rf -- "$work"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

image_sha=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image" 2>/dev/null) || image_sha=""
if [[ "$image_sha" != "$sha" ]]; then
  # Fetch only the promoted ref. If it moved since ls-remote, try on the next tick.
  git -C "$work" init --quiet
  git_remote 120s -C "$work" fetch --quiet --depth=1 "$repo" "$ref" || exit $?
  [[ "$(git -C "$work" rev-parse FETCH_HEAD)" == "$sha" ]] || exit 1
  # Keep the enclosing build directory private, but make image sources readable
  # by the unprivileged runtime user after Docker COPY.
  (umask 022; git -C "$work" checkout --quiet --detach FETCH_HEAD)
  docker build --label "org.opencontainers.image.revision=$sha" --tag "$image" "$work"
fi
image_sha=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
if [[ "$image_sha" != "$sha" ]]; then
  echo "Image revision does not match the promoted commit." >&2
  exit 1
fi
original=$(container_id dvoinik)
[[ "$original" =~ ^[0-9a-f]{64}$ ]] || exit 1
printf '%s %s\n' "$original" "$token" > "$work/pending"
mv "$work/pending" "$pending"
sync -f "$state"
docker run -d --name "$candidate" --network host --no-healthcheck \
  --label "io.dvoinik.deploy-attempt=$token" --env-file "$env_file" -e DVOINIK_PORT=8502 \
  --tmpfs /data:uid=10001,gid=10001,mode=0700 "$image" >/dev/null

if ! check http://127.0.0.1:8502 -H "Host: $host" -H 'X-Forwarded-Proto: https'; then
  docker logs --tail 30 "$candidate" >&2
  exit 1
fi
docker exec "$candidate" test -f /data/.deploy-jobs.lock

# Avoid restarting the app if a newer revision was promoted while this image was building.
result=$(git_remote 35s ls-remote "$repo" "$ref") || exit $?
if [[ "${result%%$'\t'*}" != "$sha" ]]; then
  echo "Promoted commit changed during deployment; retrying on the next timer tick." >&2
  exit 1
fi
test "$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' dvoinik)" = "$volume"
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' dvoinik |
  grep -Fx 'DVOINIK_DEPLOY_LOCK=/data/.deploy-jobs.lock' >/dev/null || {
    echo "The running container must support the deployment lock before enabling this updater." >&2
    exit 1
  }
if lock_jobs; then
  :
else
  status=$?
  if (( status == 75 )); then
    echo "Active research jobs; deferring $sha to the next timer tick."
    exit 0
  fi
  exit "$status"
fi
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
docker stop "$original" >/dev/null
docker rename "$original" "$previous"
docker run -d --name dvoinik --restart unless-stopped --network host --no-healthcheck \
  --label "io.dvoinik.deploy-attempt=$token" --env-file "$env_file" -v "$volume:/data" "$image" >/dev/null
check "$origin"
remove_candidate "$token"
clear_pending
echo "Deployed $sha; rollback container: $previous"
