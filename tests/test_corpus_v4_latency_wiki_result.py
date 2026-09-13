"""Bind the admitted wiki runtime numbers to the committed analysis closure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "results/corpus_v4/latency_fem_v2"


def test_runtime_page_matches_admitted_summary_and_terminal_archive() -> None:
    archive = json.loads((EVIDENCE / "ARCHIVE_MANIFEST.json").read_text())
    reference = archive["analysis_manifest"]
    manifest_path = ROOT / reference["path"]
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == reference["sha256"]
    summary_path = manifest_path.parent / "summary.json"
    assert hashlib.sha256(summary_path.read_bytes()).hexdigest() == archive[
        "verified_analysis_files_sha256"
    ]["summary.json"]
    payload = json.loads(summary_path.read_text())
    summary = payload["summary"]
    completion = archive["finalizer_scheduler_completion"]
    assert completion["State"] == "COMPLETED"
    assert completion["ExitCode"] == "0:0"
    assert completion["JobID"] == payload["provenance"]["scheduler"]["job_id"]
    assert summary["n_designs"] == 306
    assert summary["n_families"] == 13
    assert payload["bindings"]["expected_source_git_head"] != payload[
        "bindings"
    ]["expected_finalizer_source_git_head"]

    page = (ROOT / "wiki/results/Corpus-V4-FEM-v2-Latency.md").read_text()
    assert "status: admitted version-scoped result" in page
    assert "claim_ids: C-LAT-FEMV2-001" in page
    assert f'{summary["median_speedup_x"]["paired_four_target"]:,.3f}' in page
    for endpoint in summary["family_cluster_bootstrap_95_sensitivity_interval_x"][
        "paired_four_target"
    ]:
        assert f"{endpoint:,.3f}" in page
    components = summary["component_medians_ms"]
    assert f'{components["warm_loaded_raw_record_gnn"]:.5f} ms' in page
    assert f'{components["paired_four_target"] / 1000:.5f} s' in page
    assert "not a population or" in page
    assert "one-thread FEM-v2 R3P16" in page
    assert "Model loading, training," in page
