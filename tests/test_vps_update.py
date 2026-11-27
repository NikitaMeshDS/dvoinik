"""An interrupted deployment must recover the exact previous Docker container before reading GitHub."""

import os
import subprocess
from pathlib import Path

import pytest

UPDATER = Path(__file__).resolve().parents[1] / "deploy" / "vps-update.sh"
PREVIOUS_ID = "a" * 64
TOKEN = "Test1234"


@pytest.mark.parametrize(
    "live",
    [
        "missing",
        "old",
        "replacement",
        "foreign",
        "busy",
        "no-settings",
        "no-lock",
        "cleanup-error",
        "health-error",
    ],
)
def test_recovers_after_interruption(tmp_path, live):
    state = tmp_path / "state"
    state.mkdir()
    (state / "pending").write_text(f"{PREVIOUS_ID} {TOKEN}\n")
    volume = tmp_path / "volume"
    volume.mkdir()
    if live != "no-lock":
        (volume / ".deploy-jobs.lock").touch()
    runtime = tmp_path / "runtime.env"
    if live != "no-settings":
        runtime.write_text("DVOINIK_PUBLIC_ORIGIN=https://demo.example\n")
    trace = tmp_path / "recovery.log"
    stubs = {
        "flock": """if [[ "$*" == *"75 8"* && "$LIVE" == busy ]]; then exit 75; fi""",
        "sync": "exit 0",
        "sleep": "exit 0",
        "git": "exit 97",
        "curl": r"""printf 'curl\n' >> "$TRACE"
if [[ "$LIVE" == health-error ]]; then exit 22; fi
if [[ "$*" == *"/api/experiments"* ]]; then printf 401; else printf '<div id="root"></div>'; fi""",
        "docker": """
printf '%s %s\n' "$1" "$2" >> "$TRACE"
case "$1,$2" in
  ps,*) if [[ "$*" == *'^/dvoinik$'* ]]; then
    if grep -Fqx "rename $OLD_ID" "$TRACE"; then echo "$OLD_ID"; else
      case "$LIVE" in old|no-lock) echo "$OLD_ID";; replacement|foreign|busy) echo "$NEW_ID";; esac
    fi
  elif [[ "$LIVE" == replacement || "$LIVE" == no-lock || "$LIVE" == cleanup-error || "$LIVE" == no-settings || "$LIVE" == health-error ]]; then echo "$CANDIDATE_ID"; fi;;
  container,inspect) case "${@: -1}" in
    "$OLD_ID") if [[ "$LIVE" == no-lock ]] || grep -Fqx "start $OLD_ID" "$TRACE"; then echo true; else echo false; fi;;
    "$NEW_ID"|"$CANDIDATE_ID") if [[ "$LIVE" == foreign ]]; then echo another; else echo "$TOKEN"; fi;;
    *) exit 1;;
  esac;;
  rm,-f) if [[ "$LIVE" == cleanup-error ]]; then exit 1; else echo "removed $3" >> "$TRACE"; fi;;
  volume,inspect) echo "$VOLUME";;
  rename,"$OLD_ID") [[ $3 == dvoinik ]];;
  start,"$OLD_ID") exit 0;;
  *) exit 90;;
esac
""",
    }
    for name, body in stubs.items():
        target = tmp_path / name
        target.write_text("#!/bin/bash\n" + body + "\n")
        target.chmod(0o700)

    script = (
        UPDATER.read_text()
        .replace("/var/lib/dvoinik-cd", str(state))
        .replace("/etc/dvoinik/runtime.active.env", str(runtime))
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "TRACE": str(trace),
            "OLD_ID": PREVIOUS_ID,
            "NEW_ID": "b" * 64,
            "CANDIDATE_ID": "c" * 64,
            "TOKEN": TOKEN,
            "LIVE": live,
            "VOLUME": str(volume),
        },
        capture_output=True,
        text=True,
    )
    calls = trace.read_text().splitlines()
    deferred = live in {"foreign", "busy"}
    assert (result.returncode != 0) is (
        live in {"foreign", "no-settings", "cleanup-error", "health-error"}
    ), result.stderr
    assert (state / "pending").exists() is (
        deferred or live in {"no-settings", "cleanup-error", "health-error"}
    )
    assert (f"rename {PREVIOUS_ID}" in calls) is (
        live in {"missing", "replacement", "no-settings", "cleanup-error", "health-error"}
    )
    assert (f"start {PREVIOUS_ID}" in calls) is (not deferred and live != "no-lock")
    expected_removed = (
        {"removed " + "c" * 64}
        if live in {"replacement", "no-lock", "no-settings", "health-error"}
        else set()
    )
    if live == "replacement":
        expected_removed.add("removed " + "b" * 64)
    assert {call for call in calls if call.startswith("removed ")} == expected_removed
    if live in {"replacement", "no-settings", "cleanup-error", "health-error"}:
        assert calls.index(f"start {PREVIOUS_ID}") < max(
            index for index, call in enumerate(calls) if call == "rm -f"
        )
    if live == "health-error":
        assert calls.index("removed " + "c" * 64) < calls.index("curl")


@pytest.mark.parametrize("flaky", [False, True], ids=["rollback", "retry-api"])
def test_switch_with_public_check_errors(tmp_path, flaky):
    state = tmp_path / "state"
    volume = tmp_path / "volume"
    volume.mkdir()
    (volume / ".deploy-jobs.lock").touch()
    runtime = tmp_path / "runtime.env"
    runtime.write_text("DVOINIK_PUBLIC_ORIGIN=https://demo.example\n")
    trace = tmp_path / "deploy.log"
    stubs = {
        "flock": "exit 0",
        "sync": "exit 0",
        "sleep": "exit 0",
        "timeout": r"""printf '%s\trefs/heads/deploy/vps\n' "$SHA" """,
        "date": r"""if [[ $1 == +%s ]]; then echo "$NOW"; else echo 20261127090000; fi""",
        "curl": r"""
if [[ "$*" == *https://demo.example* && -f "$REPLACEMENT" ]]; then
  if [[ "$FLAKY" == 0 ]]; then exit 22; fi
  if [[ "$*" == *"/api/experiments"* ]] && ! grep -qx api-timeout "$TRACE"; then
    echo api-timeout >> "$TRACE"
    exit 28
  fi
fi
if [[ "$*" == *"/api/experiments"* ]]; then printf 401; else printf '<div id="root"></div>'; fi
""",
        "docker": r"""
printf '%s\n' "$1" >> "$TRACE"
case "$1" in
  ps)
    if [[ "$*" == *'^/dvoinik$'* ]]; then
      if [[ -f "$REPLACEMENT" ]]; then echo "$NEW_ID"; else echo "$OLD_ID"; fi
    fi;;
  inspect)
    case "$*" in
      *Config.Env*) echo DVOINIK_DEPLOY_LOCK=/data/.deploy-jobs.lock;;
      *.Mounts*) echo dvoinik-misisx-data;;
      *) echo "true $OLD_SHA";;
    esac;;
  image) echo "$SHA";;
  container)
    if [[ ${@: -1} == "$OLD_ID" ]]; then
      if grep -qx start "$TRACE"; then echo true; else echo false; fi
    else
      read -r original token < "$PENDING"
      echo "$token"
    fi;;
  volume) echo "$VOLUME";;
  exec) if [[ $2 == -i ]]; then echo sqlite; fi;;
  run) if [[ "$*" == *'--name dvoinik --restart'* ]]; then touch "$REPLACEMENT"; fi;;
  stop|rename|start) :;;
  rm) rm -f "$REPLACEMENT";;
  *) exit 90;;
esac
""",
    }
    for name, body in stubs.items():
        target = tmp_path / name
        target.write_text("#!/bin/bash\n" + body + "\n")
        target.chmod(0o700)

    script = (
        UPDATER.read_text()
        .replace("/var/lib/dvoinik-cd", str(state))
        .replace("/etc/dvoinik/runtime.active.env", str(runtime))
    )

    def run(sha, now):
        trace.write_text("")
        result = subprocess.run(
            ["bash", "-c", script],
            env={
                **os.environ,
                "PATH": f"{tmp_path}:{os.environ['PATH']}",
                "TRACE": str(trace),
                "OLD_ID": PREVIOUS_ID,
                "NEW_ID": "b" * 64,
                "OLD_SHA": "c" * 40 if flaky else "",
                "SHA": sha,
                "NOW": str(now),
                "FLAKY": str(int(flaky)),
                "PENDING": str(state / "pending"),
                "REPLACEMENT": str(tmp_path / "replacement"),
                "VOLUME": str(volume),
            },
            capture_output=True,
            text=True,
        )
        return result, trace.read_text().splitlines()

    failed_sha = "d" * 40
    now = 1_800_000_000
    result, calls = run(failed_sha, now)
    if flaky:
        assert "api-timeout" in calls
        assert result.returncode == 0 and "Deployed " + failed_sha in result.stdout, result.stderr
        assert "start" not in calls
        assert not (state / "pending").exists()
        return

    assert result.returncode != 0 and {"stop", "start"} <= set(calls), result.stderr
    assert not (state / "pending").exists()
    result, calls = run(failed_sha, now + 899)
    assert result.returncode == 0 and calls == ["inspect"], result.stderr
    result, calls = run(failed_sha, now + 900)
    assert result.returncode != 0 and "stop" in calls, result.stderr
    new_sha = "e" * 40
    result, calls = run(new_sha, now + 901)
    assert result.returncode != 0 and "stop" in calls, result.stderr
    result, calls = run(new_sha, now + 800)
    assert result.returncode == 0 and calls == ["inspect"], result.stderr
    result, calls = run(new_sha, now + 1700)
    assert result.returncode != 0 and "stop" in calls, result.stderr
