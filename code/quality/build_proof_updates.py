#!/usr/bin/env python3
"""Build the manuscript aggregate from immutable job-scoped proof records."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TARGET_MAP = {
    "Cps": "Cps_pF",
    "Lp": "L_pri_nH",
    "Ls": "L_sec_nH",
    "M": "L_mut_nH",
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def portable(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return "external/" + path.name


def require_schema(record: dict[str, Any], expected: str, path: Path) -> None:
    provenance = record.get("provenance", {})
    actual = provenance.get("schema")
    if actual != expected:
        raise ValueError(f"{path}: schema {actual!r}, expected {expected!r}")
    if not provenance.get("slurm_job_id"):
        raise ValueError(f"{path}: missing SLURM job identity")
    if provenance.get("git_dirty_paths"):
        raise ValueError(f"{path}: proof job ran from a dirty checkout")


def build(args: argparse.Namespace) -> dict[str, Any]:
    claim = load(args.claim)
    strict = load(args.strict)
    legacy = load(args.legacy)
    require_schema(claim, "research13.claim-proof.v1", args.claim)
    require_schema(strict, "research13.strict-egnn-ablation.v2", args.strict)
    require_schema(legacy, "research13.legacy-latency-reproduction.v1", args.legacy)

    fem = load(ROOT / "results/run_femcps/results_femcps.json")
    self_l = load(ROOT / "results/run_selfL/results_selfL.json")
    rank = load(ROOT / "results/run_rank/results_rank.json")
    rank_lat = load(ROOT / "results/run_ranklat2/results_ranklat2.json")
    decision = load(ROOT / "results/run_declat/results_declat.json")
    frequency = load(ROOT / "results/run_t3/results_t3.json")

    full_runs = [
        row for row in strict["runs"]
        if row["train_cap"] == "full" and row["model"] == "strict_egnn"
    ]
    if len(full_runs) != len(strict["protocol"]["seeds"]):
        raise ValueError("strict proof is missing one or more full-data seed runs")
    symmetry = [row["symmetry_check"] for row in full_runs]
    paired = strict["paired_analysis"]["full"]
    sensitivity = strict["same_width_sensitivity"]
    sample_eff = strict["sample_efficiency"]
    caps = strict["protocol"]["train_caps"]

    curves: dict[str, list[float]] = {}
    n_train: list[int] = []
    for model in ("invariant_matched", "strict_egnn"):
        model_means = []
        for cap in caps:
            key = str(cap)
            rows = [
                row for row in strict["runs"]
                if str(row["train_cap"]) == key and row["model"] == model
            ]
            if len(rows) != len(strict["protocol"]["seeds"]):
                raise ValueError(f"incomplete learning curve for {model}, cap={cap}")
            model_means.append(statistics.fmean(
                row["metrics"]["primary_mean_absolute_log_error"] for row in rows
            ))
            if model == "invariant_matched":
                n_train.append(int(rows[0]["n_train"]))
        curves[model] = model_means

    accuracy = claim["held_out_accuracy"]
    solver = claim["solver_timing_ms"]["paired_valid_designs"]
    gnn = claim["gnn_timing"]
    speed = claim["derived_claims"]["paired_speedup_solver_vs_end_to_end_gnn"]
    parameter_match = strict["protocol"]["parameter_match"]

    sources = [args.claim, args.strict, args.legacy]
    return {
        "schema": "proof-update-results-v2",
        "scope": "Deterministic manuscript aggregate built from job-scoped proof records.",
        "provenance": {
            "builder": portable(Path(__file__)),
            "sources": [
                {
                    "path": portable(path),
                    "sha256": sha256(path),
                    "job_id": load(path)["provenance"]["slurm_job_id"],
                    "git_head": load(path)["provenance"].get("git_head"),
                }
                for path in sources
            ],
        },
        "field_accuracy_corpus": {
            "valid": claim["corpus"]["n_valid"],
            "train": claim["corpus"]["n_train"],
            "test": claim["corpus"]["n_test"],
            "analytical_median_error_pct": {
                "Cps": fem["analytical_Cps_vs_fastcap_median_pct"],
                "Lp": self_l["L_pri_nH"]["median_rel_err_pct"],
                "Ls": self_l["L_sec_nH"]["median_rel_err_pct"],
                "M": self_l["L_mut_nH"]["median_rel_err_pct"],
            },
            "gnn_median_error_pct": {
                short: accuracy[target]["median_relative_error_pct"]
                for short, target in TARGET_MAP.items()
            },
            "gnn_r2": {
                short: accuracy[target]["r2"] for short, target in TARGET_MAP.items()
            },
        },
        "strict_e3": {
            "attempted": strict["corpus"]["n_candidates"],
            "valid": strict["corpus"]["n_valid"],
            "train": n_train[-1],
            "test": full_runs[0]["n_test"],
            "strict_parameters": parameter_match["strict_params"],
            "matched_invariant_parameters": parameter_match["matched_baseline_params"],
            "same_width_invariant_parameters": parameter_match["same_width_baseline_params"],
            "symmetry_cases": sum(row["n_cases"] for row in symmetry),
            "symmetry_tolerance": symmetry[0]["tolerance"],
            "output_residual_max": max(
                row["output_relative_residual"]["max"] for row in symmetry
            ),
            "coordinate_residual_max": max(
                row["coordinate_relative_residual"]["max"] for row in symmetry
            ),
            "full_data_primary": {
                "invariant": paired["observed_baseline"],
                "strict": paired["observed_strict"],
                "relative_delta_pct": paired["observed_relative_delta_pct"],
                "ci95_pct": paired["relative_delta_95pct_ci"],
                "equivalence_ci90_pct": paired["relative_delta_90pct_ci_for_equivalence"],
                "equivalence_margin_pct": abs(paired["predeclared_equivalence_margin_pct"][1]),
            },
            "same_width_sensitivity": {
                "relative_delta_pct": sensitivity["observed_relative_delta_pct"],
                "ci95_pct": sensitivity["relative_delta_95pct_ci"],
            },
            "learning_curve": {
                "n_train": n_train,
                "invariant_mean_error": curves["invariant_matched"],
                "strict_mean_error": curves["strict_egnn"],
                "aulc_relative_delta_pct": sample_eff["paired_analysis"]["observed_relative_delta_pct"],
                "aulc_ci95_pct": sample_eff["paired_analysis"]["relative_delta_95pct_ci"],
            },
        },
        "latency": {
            "paired_solver_ms": {
                "median": solver["median"], "mean": solver["mean"], "p95": solver["p95"]
            },
            "gnn_ms": {
                "precollated_batch_per_design": gnn["precollated_batch_ms_per_design"]["median"],
                "single_forward": gnn["single_design_forward_ms"]["median"],
                "raw_layout_end_to_end": gnn["graph_build_normalize_collate_forward_ms"]["median"],
            },
            "paired_end_to_end_speedup": {
                "median_x": speed["median_x"],
                "ci95_x": speed["bootstrap_95pct_ci_median_x"],
            },
            "legacy_batch_throughput": {
                "historical_ms": legacy["historical"]["ms_per_design"],
                "reproduced_ms": legacy["reproduction"]["legacy_ms_per_design"]["median"],
            },
        },
        "ranking": {
            "family_disjoint_pairwise_rho_median": rank["spearman_median"],
            "pointwise_rho": rank["baseline_regression_rho"],
            "xy_registration": {
                "gnn_rho": rank_lat["XY_registration"]["gnn_rho_mean"],
                "analytical_blind_fraction": rank_lat["XY_registration"]["peec_blind_frac"],
                "gnn_pick_regret_pct": decision["XY_decision"]["gnn_pick_regret_pct"],
                "analytical_pick_regret_pct": decision["XY_decision"]["peec_pick_regret_pct"],
                "random_pick_regret_pct": decision["XY_decision"]["random_pick_regret_pct"],
            },
            "z_interleaving": {
                "gnn_rho": decision["Z_interleaving"]["gnn_rho_mean"],
                "analytical_rho": decision["Z_interleaving"]["peec_rho_mean"],
                "gnn_pick_regret_pct": decision["Z_decision"]["gnn_pick_regret_pct"],
                "analytical_pick_regret_pct": decision["Z_decision"]["peec_pick_regret_pct"],
            },
        },
        "frequency_extension": {
            "n_samples": frequency["n_samples"],
            "n_test": frequency["n_test"],
            "n_frequency_points": frequency["n_freq_points"],
            "median_error_pct": frequency["curve_median_relerr_pct"],
            "curve_r2": frequency["curve_r2"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", type=Path, required=True)
    parser.add_argument("--strict", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results/proof_updates/results.json",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = json.dumps(build(args), indent=2) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text() != output:
            raise SystemExit(f"stale proof aggregate: {args.output}")
        print(f"OK {args.output}")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
