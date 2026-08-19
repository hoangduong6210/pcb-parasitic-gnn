"""Regression tests for public paper-source prose boundaries."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/quality"))

from audit_research_prose import audit_latex, audit_page  # noqa: E402


def test_inline_code_cannot_hide_private_paths_or_job_ids(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        "---\n"
        "title: Fixture\n"
        "paper_source: true\n"
        "prose_reviewed: true\n"
        "claim_ids: C-TEST-001\n"
        "---\n"
        "The internal records are `/users/example/run` and `job_6893754`.\n"
    )
    errors = audit_page(page)
    assert "private absolute path appears in paper-source prose" in errors
    assert "raw scheduler identifier appears in paper-source prose" in errors


def test_latex_audit_applies_the_same_sensitive_identifier_gate(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "main.tex"
    paper.write_text(r"Evidence: \texttt{/scratch/run}, batch 6893754.")
    assert "internal path or scheduler identifier appears" in audit_latex(paper)


def test_latex_audit_distinguishes_raw_double_hyphen_from_tex_em_dash(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "main.tex"
    paper.write_text("A---B")
    assert audit_latex(paper) == []
    paper.write_text("A--B")
    assert "raw double hyphen appears in LaTeX" in audit_latex(paper)
