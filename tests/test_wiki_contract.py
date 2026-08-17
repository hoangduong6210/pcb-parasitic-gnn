"""Contract tests for the canonical research wiki.

The wiki deliberately separates manuscript-safe prose from machine provenance.
These tests keep that boundary explicit while pinning the convergence values that
support the current FEM claim language.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"

REQUIRED_PAGES = (
    "README.md",
    "INDEX.md",
    "START-HERE.md",
    "GLOSSARY.md",
    "CONTRIBUTING.md",
    "LIMITATIONS.md",
    "REPRODUCIBILITY.md",
    "architecture/Research-System-Map.md",
    "claims/Current-Claim-Language.md",
    "claims/Historical-Claim-Ledger.md",
    "datasets/Corpus-and-Target-Contract.md",
    "datasets/Dataset-Registry.md",
    "datasets/Vendor-Geometry-Track.md",
    "decisions/0001-cps-multifidelity.md",
    "evidence/Evidence-Ledger.md",
    "evidence/FEM-Convergence-Ledger.md",
    "governance/License-and-Assets.md",
    "manuscript/FEM-Cps-Sections.md",
    "manuscript/Paper-Export-Contract.md",
    "manuscript/Paper-Outline.md",
    "methods/FEM-Cps-Reference.md",
    "methods/FastHenry-Inductance.md",
    "methods/Geometry-Family-Splits.md",
    "methods/Graph-Surrogate.md",
    "methods/Runtime-Benchmark.md",
    "methods/Strict-E3-and-EGNN.md",
    "operations/Prose-Audit.md",
    "operations/Research-Workflow.md",
    "operations/SLURM-Resource-Plan.md",
    "operations/SLURM-Submission-Playbook.md",
    "references/Technical-Source-Map.md",
    "results/FEM-R3-R4-Convergence.md",
    "status/Live-Execution.md",
    "status/Project-Status.md",
)
REQUIRED_FRONT_MATTER = {"title", "status", "paper_source"}

CONVERGENCE_ARTIFACT = (
    ROOT
    / "results/corpus_v4/refine34_convergence/final/job_6843343/"
    "results_corpus_v4_refine34_convergence.json"
)
EXPECTED_CONVERGENCE = {
    "domain_12mm_vs_16mm_at_refine3": {
        "median_relative_difference_pct": Decimal("0.18965828868643042"),
        "max_relative_difference_pct": Decimal("2.4915657825781667"),
    },
    "mesh_refine3_vs_refine4_at_16mm": {
        "median_relative_difference_pct": Decimal("8.273878711170813"),
        "max_relative_difference_pct": Decimal("13.886398757245729"),
    },
}
EXPECTED_RESULT_ROWS = (
    "| Refine-3, 12 versus 16 mm padding | 0.189658% | 2.491566% | Pass |",
    "| Refine-3 versus refine-4 at 16 mm | 8.273879% | 13.886399% | Reject |",
)

# A numeric token alone is not enough to identify a scheduler job. These
# patterns therefore require scheduler/job context and avoid false positives on
# dates, measurements, layout identifiers, and reported metrics.
RAW_JOB_ID_PATTERNS = (
    re.compile(r"\bSLURM_(?:JOB|ARRAY_JOB|ARRAY_TASK)_ID\b", re.IGNORECASE),
    re.compile(r"\b(?:slurm|array|batch|job)[_ -]?(?:id[_ -]?)?\d{5,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:sacct|squeue|scontrol|scancel)\b[^\n]*?(?:-j\s*|job\s+)\d{5,}\b",
        re.IGNORECASE,
    ),
)
ABSOLUTE_PATH_PATTERNS = (
    re.compile(
        r"(?<![\w.])/(?:users|home|tmp|scratch|var|opt|mnt|gpfs|fs|projects?)(?:/|\b)",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z]:\\", re.IGNORECASE),
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _parse_front_matter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.relative_to(ROOT)} must start with front matter"

    header, separator, body = text[4:].partition("\n---\n")
    assert separator, f"{path.relative_to(ROOT)} has unterminated front matter"

    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, colon, value = line.partition(":")
        assert colon and key.strip(), (
            f"{path.relative_to(ROOT)} has an invalid front-matter line: {line!r}"
        )
        metadata[key.strip()] = value.strip()
    return metadata, body


@pytest.mark.parametrize("relative_path", REQUIRED_PAGES)
def test_required_wiki_page_has_valid_front_matter(relative_path: str) -> None:
    path = WIKI / relative_path
    assert path.is_file(), f"missing required wiki page: wiki/{relative_path}"

    metadata, _ = _parse_front_matter(path)
    assert not REQUIRED_FRONT_MATTER.difference(metadata), (
        f"wiki/{relative_path} is missing required front-matter fields"
    )
    assert metadata["title"], f"wiki/{relative_path} has an empty title"
    assert metadata["status"], f"wiki/{relative_path} has an empty status"
    timestamp_fields = {"last_updated", "date"}.intersection(metadata)
    assert len(timestamp_fields) == 1, (
        f"wiki/{relative_path} must declare exactly one of last_updated or date"
    )
    date.fromisoformat(metadata[timestamp_fields.pop()])
    assert metadata["paper_source"] in {"true", "false"}, (
        f"wiki/{relative_path} paper_source must be true or false"
    )


def test_all_wiki_markdown_is_covered_by_the_front_matter_contract() -> None:
    markdown_pages = sorted(WIKI.rglob("*.md"))
    assert markdown_pages, "wiki must contain Markdown pages"

    for path in markdown_pages:
        metadata, _ = _parse_front_matter(path)
        assert REQUIRED_FRONT_MATTER <= metadata.keys(), (
            f"{path.relative_to(ROOT)} must use the canonical front-matter schema"
        )


def test_paper_source_pages_record_human_prose_review() -> None:
    claim_registry = _read("wiki/claims/Current-Claim-Language.md")
    for path in sorted(WIKI.rglob("*.md")):
        metadata, _ = _parse_front_matter(path)
        if metadata.get("paper_source") == "true":
            assert metadata.get("prose_reviewed") == "true", (
                f"{path.relative_to(ROOT)} must declare prose_reviewed: true"
            )
            assert metadata.get("claim_ids"), (
                f"{path.relative_to(ROOT)} must declare its claim_ids export boundary"
            )
            if metadata["claim_ids"] != "none":
                for claim_id in metadata["claim_ids"].split(","):
                    claim_id = claim_id.strip()
                    assert f"`{claim_id}`" in claim_registry, (
                        f"{path.relative_to(ROOT)} references unknown claim {claim_id}"
                    )


def test_current_claim_evidence_ids_resolve_to_the_evidence_ledger() -> None:
    claims = _read("wiki/claims/Current-Claim-Language.md")
    evidence = _read("wiki/evidence/Evidence-Ledger.md")
    evidence_ids = set(re.findall(r"`(E-[A-Z0-9-]+)`", claims))
    assert evidence_ids
    for evidence_id in evidence_ids:
        assert f"## {evidence_id}" in evidence, (
            f"current claim references missing evidence entry {evidence_id}"
        )


def test_exhaustive_index_lists_every_wiki_page() -> None:
    index = _read("wiki/INDEX.md")
    for path in sorted(WIKI.rglob("*.md")):
        relative = path.relative_to(WIKI).as_posix()
        if relative == "INDEX.md":
            continue
        target = relative if "/" not in relative else relative
        assert f"({target})" in index, f"wiki/INDEX.md does not index {relative}"


def test_all_relative_wiki_links_resolve() -> None:
    for path in sorted(WIKI.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            assert resolved.exists(), (
                f"{path.relative_to(ROOT)} links to missing target {target!r}"
            )


def test_research_prose_audit_passes() -> None:
    checked = subprocess.run(
        [sys.executable, str(ROOT / "code/quality/audit_research_prose.py")],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_paper_source_pages_exclude_raw_provenance() -> None:
    for path in sorted(WIKI.rglob("*.md")):
        metadata, body = _parse_front_matter(path)
        if metadata.get("paper_source") != "true":
            continue

        for pattern in (*RAW_JOB_ID_PATTERNS, *ABSOLUTE_PATH_PATTERNS):
            match = pattern.search(body)
            assert match is None, (
                f"{path.relative_to(ROOT)} is paper_source=true but contains raw "
                f"provenance {match.group(0)!r}"
            )


def test_wiki_reports_exact_convergence_metrics() -> None:
    artifact = json.loads(CONVERGENCE_ARTIFACT.read_text(encoding="utf-8"))
    comparisons = artifact["comparisons"]

    for comparison_name, expected_metrics in EXPECTED_CONVERGENCE.items():
        for metric_name, expected_value in expected_metrics.items():
            actual_value = Decimal(str(comparisons[comparison_name][metric_name]))
            assert actual_value == expected_value

    results_page = _read("wiki/results/FEM-R3-R4-Convergence.md")
    for expected_row in EXPECTED_RESULT_ROWS:
        assert expected_row in results_page

    manuscript_page = _read("wiki/manuscript/FEM-Cps-Sections.md")
    for metrics in EXPECTED_CONVERGENCE.values():
        for value in metrics.values():
            assert f"{value:.6f}%" in manuscript_page


@pytest.mark.parametrize(
    ("readme_path", "target_pattern"),
    (
        ("README.md", r"wiki/(?:README\.md)?"),
        ("Paper_Summary/README.md", r"\.\./wiki/(?:README\.md)?"),
    ),
)
def test_readmes_link_to_the_canonical_wiki(
    readme_path: str, target_pattern: str
) -> None:
    readme = _read(readme_path)
    links = list(re.finditer(rf"\[[^]]+\]\(({target_pattern})\)", readme))
    assert links, f"{readme_path} must contain a Markdown link to the canonical wiki"

    authority_terms = {"authoritative", "canonical"}
    assert any(
        authority_terms.intersection(
            readme[max(0, link.start() - 180) : link.end() + 180].lower().split()
        )
        for link in links
    ), f"{readme_path} must identify its wiki link as canonical or authoritative"


def test_slurm_playbook_indexes_cluster_specific_failure_prevention() -> None:
    index = _read("wiki/README.md")
    playbook = _read("wiki/operations/SLURM-Submission-Playbook.md")
    assert "operations/SLURM-Submission-Playbook.md" in index
    for required in (
        "paper_source: false",
        "MaxArraySize=1001",
        "MaxSubmitJobsPU=1000",
        "-A pgs0407",
        "0-399%8",
        "0-299%8",
        "afterany",
        "ReqTRES",
        "AllocTRES",
        "6845922",
        "plan_corpus_v4_cps_submission_shards.py",
        "build_corpus_v4_cps_candidate_index.py",
        "--expected-candidate-index-sha256",
        "submit_finalize_corpus_v4_cps_multifidelity.sh",
        "git status --short --untracked-files=all -- code protocols",
        "--expected-task-set-sha256",
        "R3_RETRY_JOB_IDS",
        "R4_RETRY_JOB_IDS",
        "R4_RETRY_JOB_ID",
        "Retry only pending tasks",
        "RETRY_ROUND=$((RETRY_ROUND + 1))",
        "R3_ATTEMPT_DIR_ARGS+=(",
        "R4_ATTEMPT_DIR_ARGS+=(",
        'R3_PENDING="results/corpus_v4/cps_multifidelity/resume/r3_${RETRY_SUFFIX}/pending_task_set.json"',
        'R4_PENDING="results/corpus_v4/cps_multifidelity/resume/r4_${RETRY_SUFFIX}/pending_task_set.json"',
        "Do not reinitialize them from `*_initial`",
        "Initialize the cumulative state exactly once",
        "begins with `printf -v RETRY_SUFFIX`",
        'PCB_GNN_JOB_ENV="$PCB_JOB_ENV"',
        "--chdir` changes the batch working directory but does **not** change",
        "400 + 400 + 198 = 998",
        "1000 - R3_RETRY_TASKS",
        "--max-array-size 1",
        "corpus_v4_cps_execution_lock_v2.json",
        "Rejected candidates are retained audit history",
    ):
        assert required in playbook
    assert playbook.count('PCB_GNN_JOB_ENV="$PCB_JOB_ENV"') >= 8
    assert re.search(r"<[^>]+>", playbook) is None
    for line in playbook.splitlines():
        if "sbatch" in line and not line.lstrip().startswith("|"):
            assert "-A pgs0407" in line


def test_slurm_playbook_bash_blocks_are_syntactically_valid() -> None:
    playbook = _read("wiki/operations/SLURM-Submission-Playbook.md")
    blocks = re.findall(r"```bash\n(.*?)\n```", playbook, flags=re.DOTALL)
    assert blocks
    checked = subprocess.run(
        ["bash", "-n"],
        input="\n".join(blocks),
        capture_output=True,
        check=False,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr
