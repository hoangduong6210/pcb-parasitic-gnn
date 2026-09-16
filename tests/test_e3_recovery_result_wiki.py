"""Bind the coordinate-ablation wiki's reported numbers to its JSON evidence.

These tests read prose and summary JSON only. They perform no model inference.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "wiki/results/Corpus-V4-FEM-v2-Coordinate-Ablation.md"
SUMMARY = ROOT / "results/corpus_v4/strict_e3_fem_v2/recovery/v1/final/job_7326179/summary.json"
CLAIMS = ROOT / "wiki/claims/Current-Claim-Language.md"
PROJECT_STATUS = ROOT / "wiki/status/Project-Status.md"
EVIDENCE = ROOT / "wiki/evidence/Evidence-Ledger.md"
INDEX = ROOT / "wiki/INDEX.md"
TARGETS = (("Cps", "Cps_pF"), ("Lp", "L_pri_nH"), ("Ls", "L_sec_nH"), ("M", "L_mut_nH"))


def evidence() -> tuple[str, dict]:
    return PAGE.read_text(), json.loads(SUMMARY.read_text())["results"]


def table_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.startswith("|")]


def test_wiki_mean_mape_table_matches_all_twelve_summary_values() -> None:
    text, results = evidence()
    rows = table_rows(text)
    for arm in ("strict96", "fixed96", "fixed_matched"):
        selected = [row for row in rows if f"(`{arm}`)" in row[0]]
        assert len(selected) == 1
        assert selected[0][1:] == [
            f"{results['arms'][arm][target]['mean_family_macro_mape_pct']:.3f}"
            for _, target in TARGETS
        ]


def test_wiki_paired_table_preserves_sign_target_and_interval_endpoints() -> None:
    text, results = evidence()
    rows = table_rows(text)
    expected = []
    for label, control in (("Fixed width 96", "fixed96"), ("Capacity control", "fixed_matched")):
        for target_label, target in TARGETS:
            item = results["paired_contrasts"][control][target]
            low, high = item["crossed_axis_95pct_interval_pp"]
            expected.append([label, target_label,
                             f"{item['mean_strict96_minus_control_pp']:.3f}",
                             f"{low:.3f} to {high:.3f}"])
    actual = [row for row in rows if row[0] in {"Fixed width 96", "Capacity control"}]
    assert actual == expected


def test_wiki_zero_interval_and_direction_statements_match_evidence() -> None:
    text, results = evidence()
    contrasts = results["paired_contrasts"]
    intervals = [item["crossed_axis_95pct_interval_pp"]
                 for control in contrasts.values() for item in control.values()]
    assert len(intervals) == 8
    assert all(low <= 0 <= high for low, high in intervals)
    assert "All eight intervals include zero." in text
    assert sum(item["mean_strict96_minus_control_pp"] < 0
               for item in contrasts["fixed96"].values()) == 3
    assert all(item["mean_strict96_minus_control_pp"] > 0
               for item in contrasts["fixed_matched"].values())
    assert "Positive values\nfavor the fixed-coordinate control." in text
    assert results["resampling"]["resamples"] == 10_000
    assert "10,000 shared crossed-axis" in text
    assert "not a population confidence interval" in results["resampling"]["semantics"]
    assert "not population confidence" in text


def compact_exponent(value: float) -> str:
    return re.sub(r"e([+-])0+(\d+)$", r"e\1\2", f"{value:.4e}")


def test_wiki_symmetry_numbers_and_zero_diagnostics_match_summary() -> None:
    text, results = evidence()
    symmetry = results["trained_symmetry"]
    assert symmetry["all_passed"] is True
    assert symmetry["checkpoint_receipts"] == 75
    assert symmetry["transforms_per_checkpoint"] == 40
    assert symmetry["validation_family_fixtures_per_checkpoint"] == 7
    assert symmetry["graph_transform_evaluations"] == 21_000
    assert "All 75 trained checkpoints" in text and "40 transforms" in text
    assert "seven validation-family fixtures" in text and "21,000 graph-transform" in text
    labels = {"strict96": "for the moving", "fixed96": "for the fixed-width arm", "fixed_matched": "for the capacity control"}
    for arm, label in labels.items():
        value = symmetry["maximum_scalar_invariance_residual_by_arm"][arm]
        assert f"{compact_exponent(value)} {label}" in text
        assert value < symmetry["relative_tolerance"]
    coordinate = symmetry["maximum_strict96_coordinate_equivariance_residual"]
    assert f"equivariance residual was {compact_exponent(coordinate)}" in text
    assert coordinate < symmetry["relative_tolerance"] == 2e-5
    assert "relative tolerance of 2e-5" in text
    assert all(value == 0 for value in symmetry["maximum_fixed_coordinate_unchanged_residual"].values())
    for arm in results["arms"].values():
        for target in arm.values():
            assert target["nonpositive_predictions_across_cells"] == 0
            assert target["inductance_psd_violations_across_cells"] == 0


def test_wiki_capacity_coverage_and_evidence_link_match_summary() -> None:
    text, results = evidence()
    match = re.search(r"\[summary\]\(([^)]+)\)", text)
    assert match is not None
    assert (PAGE.parent / match.group(1)).resolve() == SUMMARY
    parameter = results["parameter_match"]
    assert f"{parameter['fixed_matched']:,} parameters versus {parameter['strict96']:,}" in text
    counts = results["counts"]
    assert f"{counts['prediction_rows']:,} prediction rows" in text
    assert f"{counts['arm_target_metric_rows']}\narm-target metric rows" in text
    assert f"{counts['paired_contrast_rows']} paired contrasts" in text
    assert results["inference_runtime_claim"] is False


def test_coordinate_ablation_claim_is_admitted_with_exact_evidence_mapping() -> None:
    claims = CLAIMS.read_text()
    admitted, remainder = claims.split("## Validated or finalized artifacts", 1)
    assert "`C-E3-FEMV2-001`" in admitted
    assert "did not establish a consistent accuracy gain from coordinate updates" in admitted
    assert "same-width and approximately parameter-matched fixed-coordinate controls" in admitted
    assert "all eight descriptive crossed-axis 95% intervals included zero" in admitted
    assert "`E-C4-E3-FEMV2-ANALYSIS-01`" in admitted
    assert "remains PROPOSED" not in remainder


def test_admitted_claim_retains_non_equivalence_and_non_universal_boundaries() -> None:
    claims = CLAIMS.read_text()
    assert "not population confidence or equivalence" in claims
    assert "not an equivariance-versus-non-equivariance comparison" in claims
    assert "a universal statement about EGNNs" in claims
    assert "Only the scoped absence of an established\nconsistent gain" in claims


def test_admission_status_is_synchronized_without_exporting_a_paper_source() -> None:
    page = PAGE.read_text()
    assert "status: ADMITTED; VERSION-SCOPED" in page
    assert "paper_source: false" in page
    assert "`ADMITTED; VERSION-SCOPED`" in PROJECT_STATUS.read_text()
    assert "`C-E3-FEMV2-001` ADMITTED on 2026-09-15" in EVIDENCE.read_text()
    assert "Admitted version-scoped absence of an established consistent coordinate-update gain" in INDEX.read_text()
