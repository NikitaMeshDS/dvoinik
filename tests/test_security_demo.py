import importlib.util
from pathlib import Path


def test_evidence_marks_failed_skipped_and_runner_errors_as_not_passed(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "security_demo", Path(__file__).parents[1] / "scripts/security_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    xml = tmp_path / "result.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase classname="test_access" name="isolated" time="0.2" />'
        '<testcase classname="test_access" name="denied"><failure message="secret-cookie">private-password</failure></testcase>'
        '<testcase classname="test_access" name="skipped"><skipped /></testcase></testsuite></testsuites>'
    )
    report = module.read_evidence(xml, 1)
    assert report["passed"] is False
    assert report["counts"] == {"passed": 1, "failed": 1, "error": 0, "skipped": 1}
    assert [case["status"] for case in report["checks"]] == ["passed", "failed", "skipped"]
    assert "secret-cookie" not in str(report) and "private-password" not in str(report)
    xml.write_text(
        '<testsuites><testsuite><testcase classname="test_access" name="isolated" /></testsuite></testsuites>'
    )
    assert module.read_evidence(xml, 2)["passed"] is False
