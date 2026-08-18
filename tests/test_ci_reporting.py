"""Tests for compact GitHub Actions failure reporting."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "code/quality/report_junit_failures.py"
SPEC = importlib.util.spec_from_file_location("report_junit_failures", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
REPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORTER)


def test_failure_annotation_escapes_multiline_output(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite><testcase classname="tests.test_contract" name="test_gate">
<failure message="failed">first line
second % line</failure>
</testcase></testsuite></testsuites>
""",
        encoding="utf-8",
    )

    assert REPORTER.failure_annotations(report) == [
        "::error title=pytest: tests.test_contract.test_gate::"
        "first line%0Asecond %25 line"
    ]


def test_successful_cases_do_not_create_annotations(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuite><testcase classname="tests.test_contract" name="test_gate" />'
        "</testsuite>",
        encoding="utf-8",
    )

    assert REPORTER.failure_annotations(report) == []
