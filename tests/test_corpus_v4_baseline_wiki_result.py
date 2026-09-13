"""Bind baseline wiki tables to immutable admitted analysis; no model replay."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "results/corpus_v4/baseline_fem_v2"
ANALYSIS = EVIDENCE / "final/job_7273521"
PAGE = ROOT / "wiki/results/Corpus-V4-FEM-v2-Baselines.md"
MODELS = {"constant": "Constant", "ridge": "Ridge", "random_forest": "Random Forest", "extra_trees": "Extra Trees"}
TARGETS = {"Cps_pF": "Cps", "L_pri_nH": "Lp", "L_sec_nH": "Ls", "L_mut_nH": "M"}
HASHES = {
    "summary.json": "f16404ede4220b0b3fec9002e75ebe0507322b29e94bc5c56ab1943857db6163",
    "ANALYSIS_MANIFEST.json": "f750b4257160b623eb5554f380601ce5a7a20e9342d90bec7e2ddbdd592edd28",
    "metrics.json": "d588cd5899ce2d0bf319ef4f5274e6fd44d03fe8d71127064ab59da2a4368bdc",
    "predictions.jsonl": "795c1690745b19106017c96344102b495b809aafad2d908146d31926369c9fec",
}


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads((ANALYSIS / "summary.json").read_text())


@pytest.fixture(scope="module")
def metrics() -> list[dict]:
    return json.loads((ANALYSIS / "metrics.json").read_text())["cells"]


@pytest.fixture(scope="module")
def table_rows() -> list[list[str]]:
    return [[cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
            for line in PAGE.read_text().splitlines() if line.startswith("|")]


@pytest.mark.parametrize("name", HASHES)
def test_final_analysis_bytes_are_immutable(name: str) -> None:
    assert hashlib.sha256((ANALYSIS / name).read_bytes()).hexdigest() == HASHES[name]


def test_manifest_summary_and_archive_have_complete_bindings(summary: dict) -> None:
    manifest = json.loads((ANALYSIS / "ANALYSIS_MANIFEST.json").read_text())
    archive = json.loads((EVIDENCE / "ARCHIVE_MANIFEST.json").read_text())
    assert manifest["files"] == {name: digest for name, digest in HASHES.items() if name != "ANALYSIS_MANIFEST.json"}
    assert manifest["bindings"] == summary["bindings"] == archive["bindings"]
    assert summary["bindings"]["source_git_head"] == "23ca6d046528e0da22d5fbaa24454da9101c7315"
    assert archive["analysis_manifest"] == {"path": (ANALYSIS / "ANALYSIS_MANIFEST.json").relative_to(ROOT).as_posix(),
                                           "sha256": HASHES["ANALYSIS_MANIFEST.json"]}
    assert archive["numerical_reconstruction_passed"] is True
    assert archive["claim_eligible"] is False  # Scientific admission is a separate wiki decision.
    assert summary["claim_eligible"] is False
    assert archive["finalizer_terminal"]["State"] == "COMPLETED"
    assert archive["finalizer_terminal"]["ExitCode"] == "0:0"
    assert archive["finalizer_terminal"]["Restarts"] == "0"
    assert archive["finalizer_terminal"]["JobIDRaw"] == summary["scheduler"]["job_id"] == "7273521"
    accepted = ROOT / archive["accepted_set"]["path"]
    assert hashlib.sha256(accepted.read_bytes()).hexdigest() == summary["accepted_set_sha256"] == archive["accepted_set"]["sha256"]


@pytest.mark.parametrize("model,label", MODELS.items())
def test_mean_error_table_matches_unrounded_summary(model: str, label: str, summary: dict, table_rows: list) -> None:
    expected = [label] + [f'{summary["results"]["models"][model][target]["mean_family_macro_mape_pct"]:.3f}' for target in TARGETS]
    assert expected in table_rows


def test_gnn_row_is_paired_cell_mean_not_rounded_difference(metrics: list, table_rows: list) -> None:
    means = []
    for target in TARGETS:
        selected = [row for row in metrics if row["model"] == "constant" and row["target"] == target]
        assert len(selected) == 25
        means.append(f'{statistics.mean(row["gnn_metrics"]["family_macro_mape_pct"] for row in selected):.3f}')
    assert ["GNN", *means] in table_rows


@pytest.mark.parametrize("model,label", MODELS.items())
@pytest.mark.parametrize("target,target_label", TARGETS.items())
def test_paired_interval_table_matches_every_frozen_cell(model: str, label: str, target: str, target_label: str,
                                                        summary: dict, table_rows: list) -> None:
    cell = summary["results"]["models"][model][target]
    interval = cell["paired_difference_crossed_axis_95pct_interval_pp"]
    rows = [row for row in table_rows if row[:2] == [label, target_label]]
    assert len(rows) == 1
    numeric_text = " | ".join(rows[0][2:])
    assert f'{cell["mean_paired_difference_pp"]:.3f}' in numeric_text
    assert all(f"{value:.3f}" in numeric_text for value in interval)


def test_metric_and_prediction_coverage_is_exact(metrics: list, summary: dict) -> None:
    assert summary["results"]["n_cells"] == 25
    assert len(metrics) == 400
    expected = {(task, model, target) for task in range(25) for model in MODELS for target in TARGETS}
    assert {(row["task_id"], row["model"], row["target"]) for row in metrics} == expected
    for row in metrics:
        assert row["split_seed"] == 40 + row["task_id"] // 5
        assert row["init_seed"] == 40 + row["task_id"] % 5
        assert row["metrics"]["family_macro_mape_pct"] - row["gnn_metrics"]["family_macro_mape_pct"] == row["paired_family_macro_mape_difference_pp"]
    counts: Counter = Counter()
    keys = set()
    with (ANALYSIS / "predictions.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["task_id"], row["model"], row["layout_id"])
            assert key not in keys
            keys.add(key)
            counts[(row["task_id"], row["model"])] += 1
    assert len(keys) == 29400
    assert set(counts) == {(task, model) for task in range(25) for model in MODELS}
    for row in metrics:
        assert counts[(row["task_id"], row["model"])] == row["metrics"]["n_samples"]


def test_scope_and_resampling_are_not_upgraded_by_documentation(summary: dict) -> None:
    page = " ".join(PAGE.read_text().lower().split())
    assert "claim_ids: c-base-femv2-001" in page
    for phrase in ("family-macro", "post-hoc", "fixed-budget", "not a population", "percentage points"):
        assert phrase in page
    result = summary["results"]
    assert result["split_panels_independent"] is False
    assert result["hyperparameter_search_trials"] == 0
    assert result["resampling"]["axes"] == ["split", "initialization"]
    assert result["resampling"]["resamples"] == 10000
    for model in MODELS:
        for target in TARGETS:
            assert result["models"][model][target]["deterministic_model_repeated_initializations"] == (model in ("constant", "ridge"))
