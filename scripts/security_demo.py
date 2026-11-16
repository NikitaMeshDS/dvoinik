"""Run local access-control proofs and export a report without credentials or HTTP payloads."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    "tests/test_auth.py::test_password_is_hashed_and_username_is_normalized",
    "tests/test_auth.py::test_rate_limit_survives_new_store_and_browser_session",
    "tests/test_auth.py::test_logout_disable_and_reset_revoke_existing_tokens",
    "tests/test_auth.py::test_idle_and_absolute_deadline_are_checked_on_server",
    "tests/test_api.py::test_session_boundary_and_csrf",
    "tests/test_api.py::test_owner_and_session_isolation_and_admin",
    "tests/test_api.py::test_sample_cache_import_compare_and_private_download",
    "tests/test_api.py::test_exports_require_same_cookie_and_expire",
    "tests/test_api.py::test_validation_cas_conflict_preserves_exportable_preview",
    "tests/test_api.py::test_revoke_during_engine_prevents_persist",
    "tests/test_api.py::test_revocation_before_response_withholds_private_payload",
    "tests/test_api.py::test_old_tab_read_is_rejected_after_browser_cookie_switches_account",
    "tests/test_api.py::test_react_shell_rejects_framing_and_limits_scripts_to_local_assets",
    "tests/test_no_egress.py",
]


def read_evidence(xml_path: Path, returncode: int) -> dict:
    counts = dict.fromkeys(["passed", "failed", "error", "skipped"], 0)
    checks = []
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        status = next(
            (tag for tag in ("error", "failure", "skipped") if case.find(tag) is not None), "passed"
        )
        status = "failed" if status == "failure" else status
        counts[status] += 1
        checks.append({"check": case.get("classname", "") + "::" + case.get("name", ""), "status": status})
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Isolated local test accounts and synthetic records; no production data; not a penetration test or compliance certification.",
        "passed": returncode == 0 and bool(checks) and all(case["status"] == "passed" for case in checks),
        "runner_exit_code": returncode,
        "counts": counts,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/security-evidence.json"))
    args = parser.parse_args()
    # Keep raw pytest logs/XML in an automatically removed directory. Only test IDs
    # and outcomes are released; failures can include credentials in tracebacks.
    with tempfile.TemporaryDirectory(prefix="dvoinik-security-") as directory:
        junit = Path(directory) / "result.xml"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *CHECKS, f"--junitxml={junit}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if junit.exists():
            evidence = read_evidence(junit, result.returncode)
        else:
            evidence = {
                "schema_version": 1,
                "passed": False,
                "runner_exit_code": result.returncode,
                "error": "No test report produced",
            }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"passed": evidence["passed"], "counts": evidence.get("counts"), "output": str(args.output)},
            ensure_ascii=False,
        )
    )
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
