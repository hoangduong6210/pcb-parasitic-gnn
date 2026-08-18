#!/usr/bin/env python3
"""Publish failed JUnit test cases as GitHub Actions annotations.

The normal pytest log remains authoritative.  These compact annotations make
the failing assertion available through the public check-run API, which keeps
CI diagnosable even when the full Actions log requires authentication.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _escape_workflow_command(value: str) -> str:
    """Escape data according to the GitHub workflow-command protocol."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def failure_annotations(report: Path) -> list[str]:
    """Return one GitHub annotation command per failed or errored test case."""
    root = ET.parse(report).getroot()
    annotations: list[str] = []
    for case in root.iter("testcase"):
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            continue

        classname = case.attrib.get("classname", "pytest")
        test_name = case.attrib.get("name", "unknown-test")
        title = _escape_workflow_command(f"pytest: {classname}.{test_name}")
        detail = problem.text or problem.attrib.get("message", "test failed")
        message = _escape_workflow_command(detail.strip())
        annotations.append(f"::error title={title}::{message}")
    return annotations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="JUnit XML report from pytest")
    args = parser.parse_args(argv)

    if not args.report.is_file():
        print(f"JUnit report not found: {args.report}", file=sys.stderr)
        return 2

    try:
        annotations = failure_annotations(args.report)
    except ET.ParseError as exc:
        print(f"Invalid JUnit report {args.report}: {exc}", file=sys.stderr)
        return 2

    for annotation in annotations:
        print(annotation)
    if not annotations:
        print("JUnit report contains no failed test cases", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
