"""Contracts for the job-backed Corpus v4 Cps discrepancy audit."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json"
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

from audit_corpus_v4_cps_fidelity_discrepancy import (  # noqa: E402
    FAMILY_SCHEMA,
    PAIR_SCHEMA,
    SUMMARY_SCHEMA,
    DEFAULT_OUTPUT,
    DiscrepancyAuditError,
    _build_pairs,
    _observation_map,
    _validate_output_path,
    build_audit,
    quantile_type7,
    summarize,
    write_outputs,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_protocol_pins_sources_and_forbids_inferential_overreach() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["schema"] == "pcb-gnn.cps-fidelity-discrepancy-protocol.v1"
    assert protocol["design"] == {
        "anchor_selections": 9,
        "families": 66,
        "matched_layouts": 198,
        "non_anchor_selections": 189,
        "selected_per_family": 3,
        "split_seeds": [40, 41, 42, 43, 44],
        "test_families_per_split": 13,
    }
    for record_name in ("implementation", "batch_script"):
        record = protocol[record_name]
        assert _sha256(ROOT / record["path"]) == record["sha256"]
    for record in protocol["inputs"].values():
        assert _sha256(ROOT / record["path"]) == record["sha256"]
    semantics = protocol["scientific_semantics"]
    assert semantics["descriptive_only"] is True
    assert semantics["family_expansion_weight_is_probability"] is False
    assert semantics["no_exclusions_after_discrepancy"] is True
    assert {
        "continuum_convergence",
        "corpus_wide_confidence_interval",
        "global_r3_calibration",
        "ground_truth",
        "independent_split_replicates",
        "physical_accuracy",
    } == set(semantics["forbidden_claims"])


def test_type7_quantiles_and_summary_use_frozen_definition() -> None:
    values = [1.0, 2.0, 4.0, 8.0]
    assert quantile_type7(values, 0.0) == 1.0
    assert quantile_type7(values, 0.25) == 1.75
    assert quantile_type7(values, 0.50) == 3.0
    assert quantile_type7(values, 1.0) == 8.0
    result = summarize(values)
    assert result["count"] == 4
    assert result["mean"] == 3.75
    assert result["median"] == 3.0
    with pytest.raises(DiscrepancyAuditError, match="empty"):
        summarize([])


def test_pair_formula_uses_r4_as_comparator_without_calling_it_truth() -> None:
    selection = [
        {
            "family_id": "turns-04-04",
            "geometry_sha256": "a" * 64,
            "is_mandatory_anchor": False,
            "layout_id": 7,
            "selection_rank_within_family": 0,
        }
    ]
    observations = {
        (7, "r3"): {
            "artifact_sha256": "b" * 64,
            "cps_pf": 11.0,
            "geometry_sha256": "a" * 64,
        },
        (7, "r4"): {
            "artifact_sha256": "c" * 64,
            "cps_pf": 10.0,
            "geometry_sha256": "a" * 64,
        },
    }
    rows = _build_pairs(
        selection,
        observations,
        {"pairing": {"r3_fidelity_id": "r3", "r4_fidelity_id": "r4"}},
    )
    assert rows[0]["signed_delta_percent"] == pytest.approx(10.0)
    assert rows[0]["absolute_delta_percent"] == pytest.approx(10.0)
    assert rows[0]["r3_to_r4_ratio"] == pytest.approx(1.1)
    assert rows[0]["log_r3_to_r4_ratio"] == pytest.approx(math.log(1.1))
    assert rows[0]["r3_task_artifact_sha256"] == "b" * 64
    assert rows[0]["r4_task_artifact_sha256"] == "c" * 64


@pytest.mark.parametrize("bad_cps", (True, 0.0, -1.0, float("inf")))
def test_observation_contract_rejects_invalid_capacitance(bad_cps: object) -> None:
    row = {
        "artifact_sha256": "a" * 64,
        "cps_pf": bad_cps,
        "fidelity_id": "r3",
        "geometry_sha256": "b" * 64,
        "layout_id": 0,
        "units": "pF",
    }
    protocol = {"pairing": {"r3_fidelity_id": "r3", "r4_fidelity_id": "r4"}}
    with pytest.raises(DiscrepancyAuditError, match="invalid or duplicate"):
        _observation_map([row], protocol)


def test_real_archive_build_is_exact_and_retains_every_selected_layout() -> None:
    summary, pairs, families = build_audit(ROOT, PROTOCOL)
    assert summary["schema"] == SUMMARY_SCHEMA
    assert len(pairs) == 198
    assert len(families) == 66
    assert {row["schema"] for row in pairs} == {PAIR_SCHEMA}
    assert {row["schema"] for row in families} == {FAMILY_SCHEMA}
    assert len({(row["layout_id"], row["geometry_sha256"]) for row in pairs}) == 198
    assert {row["n_selected"] for row in families} == {3}
    assert sum(row["is_mandatory_anchor"] for row in pairs) == 9
    assert summary["counts"]["split_test_pairs_per_seed"] == [39]
    assert len(summary["metrics"]["split_test_sets"]) == 5
    assert summary["scientific_semantics"]["selected_registry_scope_only"] is True


def test_output_path_is_job_scoped_and_cannot_escape_repository(
    tmp_path: Path,
) -> None:
    with pytest.raises(DiscrepancyAuditError, match="canonical audit root"):
        _validate_output_path(tmp_path / "job_123", writing=False)
    with pytest.raises(DiscrepancyAuditError, match="canonical audit root"):
        _validate_output_path(
            ROOT
            / "results/corpus_v4/cps_multifidelity/audits/elsewhere/job_123",
            writing=False,
        )


def test_write_path_requires_the_current_slurm_job_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(DiscrepancyAuditError, match="SLURM_JOB_ID"):
        _validate_output_path(DEFAULT_OUTPUT / "job_123", writing=True)


def test_failed_non_slurm_write_does_not_create_an_output_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "99999999"
    output = DEFAULT_OUTPUT / f"job_{job_id}"
    assert not output.exists()
    monkeypatch.setenv("SLURM_JOB_ID", job_id)
    monkeypatch.delenv("PCB_GNN_EXECUTED_BATCH_SCRIPT", raising=False)
    with pytest.raises(DiscrepancyAuditError, match="executed SLURM batch"):
        write_outputs(output, {}, "0" * 64, {}, [], [])
    assert not output.exists()
