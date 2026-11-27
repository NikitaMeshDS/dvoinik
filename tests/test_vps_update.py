"""An interrupted deployment must recover the exact previous Docker container before reading GitHub."""

import os
import subprocess
from pathlib import Path

import pytest

UPDATER = Path(__file__).resolve().parents[1] / "deploy" / "vps-update.sh"
PREVIOUS_ID = "a" * 64
TOKEN = "Test1234"


@pytest.mark.parametrize(
    "live", ["missing", "old", "replacement", "foreign", "busy", "no-settings", "no-lock"]
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
    trace = tmp_path / "docker.log"
    stubs = {
        "flock": """if [[ "$*" == *"75 8"* && "$LIVE" == busy ]]; then exit 75; fi""",
        "sync": "exit 0",
        "git": "exit 97",
        "curl": """if [[ "$*" == *"/api/experiments"* ]]; then printf 401; else printf '<div id="root"></div>'; fi""",
        "docker": """
printf '%s %s\n' "$1" "$2" >> "$TRACE"
case "$1,$2" in
  ps,*) if [[ "$*" == *'^/dvoinik$'* ]]; then
    if grep -Fqx "rename $OLD_ID" "$TRACE"; then echo "$OLD_ID"; else
      case "$LIVE" in old|no-lock) echo "$OLD_ID";; replacement|foreign|busy) echo "$NEW_ID";; esac
    fi
  elif [[ "$LIVE" == replacement || "$LIVE" == no-lock ]]; then echo "$CANDIDATE_ID"; fi;;
  container,inspect) case "${@: -1}" in
    "$OLD_ID") if [[ "$LIVE" == no-lock ]] || grep -Fqx "start $OLD_ID" "$TRACE"; then echo true; else echo false; fi;;
    "$NEW_ID"|"$CANDIDATE_ID") if [[ "$LIVE" == foreign ]]; then echo another; else echo "$TOKEN"; fi;;
    *) exit 1;;
  esac;;
  rm,-f) echo "removed $3" >> "$TRACE";;
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
    assert (result.returncode != 0) is (live in {"foreign", "no-settings"}), result.stderr
    assert (state / "pending").exists() is (deferred or live == "no-settings")
    assert (f"rename {PREVIOUS_ID}" in calls) is (live in {"missing", "replacement", "no-settings"})
    assert (f"start {PREVIOUS_ID}" in calls) is (not deferred and live != "no-lock")
    expected_removed = {"removed " + "c" * 64} if live in {"replacement", "no-lock"} else set()
    if live == "replacement":
        expected_removed.add("removed " + "b" * 64)
    assert {call for call in calls if call.startswith("removed ")} == expected_removed
