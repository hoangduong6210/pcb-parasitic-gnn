#!/usr/bin/env python3
"""Five-seed pairwise versus pointwise ranking on finalized v3 lateral families."""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "models/gnn"):
    sys.path.insert(0, str(directory))

from gnn_baseline import PCBParasiticGNN, collate
from planar_to_graph import build_graph_from_planar_layout
from v3_dataset import sha256

SCHEMA = "pcb-gnn.corpus-v3-ranking-task.v1"
SEEDS = (40, 41, 42, 43, 44)


def load_families(directory: Path) -> tuple[list[list[dict]], dict]:
    summary = json.loads((directory / "summary.json").read_text())
    artifact = directory / "lateral_families.jsonl"
    if sha256(artifact) != summary["artifacts_sha256"][artifact.name]:
        raise ValueError("lateral artifact hash mismatch")
    if summary["gates"] != {"n_families": 70, "n_variants": 490, "n_unique_geometry": 490,
                             "geometry_valid": True, "labels_passive": True}:
        raise ValueError("lateral corpus gates are not canonical")
    rows = [json.loads(line) for line in artifact.read_text().splitlines() if line]
    families = [[row for row in rows if row["family_id"] == family] for family in range(70)]
    for family in families:
        for row in family:
            graph = build_graph_from_planar_layout(row["layout"])
            node, edge, edge_index = graph.to_feature_matrices()
            row["sample"] = {"node_feat": node.astype(np.float32), "edge_feat": edge.astype(np.float32),
                             "edge_index": edge_index.astype(np.int64), "edge_dim": 7,
                             "y": np.zeros(1, dtype=np.float32)}
    return families, summary


class FeatureNorm:
    def __init__(self, samples: list[dict]):
        nodes = np.concatenate([sample["node_feat"] for sample in samples])
        edges = np.concatenate([sample["edge_feat"] for sample in samples])
        self.nm, self.ns = nodes.mean(0), nodes.std(0) + 1e-6
        self.em, self.es = edges.mean(0), edges.std(0) + 1e-6

    def transform(self, sample: dict) -> dict:
        return {"node_feat": ((sample["node_feat"] - self.nm) / self.ns).astype(np.float32),
                "edge_feat": ((sample["edge_feat"] - self.em) / self.es).astype(np.float32),
                "edge_index": sample["edge_index"], "edge_dim": 7, "y": sample["y"]}


def evaluate(model: nn.Module, families: list[list[dict]], norm: FeatureNorm, pointwise: bool,
             target_mean: float, target_std: float) -> tuple[list[dict], np.ndarray]:
    rows, family_loss = [], []
    model.eval()
    with torch.no_grad():
        for family in families:
            scores = model(collate([norm.transform(row["sample"]) for row in family])).squeeze(-1).numpy()
            if pointwise:
                scores = np.expm1(scores * target_std + target_mean)
            cps = np.asarray([row["label"]["Cps_pF"] for row in family])
            rho = float(spearmanr(scores, cps).statistic)
            selected = int(np.argmin(scores))
            optimum = int(np.argmin(cps))
            regret = (cps[selected] - cps[optimum]) / cps[optimum] * 100.0
            random_regret = (cps.mean() - cps[optimum]) / cps[optimum] * 100.0
            rows.append({"family_id": family[0]["family_id"], "spearman_rho": rho,
                         "selection_regret_pct": float(regret),
                         "random_expected_regret_pct": float(random_regret),
                         "selected_variant": selected, "optimal_variant": optimum,
                         "scores": scores.tolist(), "cps_pf": cps.tolist()})
            family_loss.append(1.0 - rho)
    return rows, np.asarray(family_loss)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lateral", type=Path)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 5}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing ranking training outside a SLURM array")
    if args.lateral is None:
        raise SystemExit("--lateral is required")
    dirty = subprocess.run(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing ranking from a dirty tracked worktree")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    seed = SEEDS[task_id]
    families, summary = load_families(args.lateral)
    split_rng = np.random.default_rng(42)
    order = np.arange(70); split_rng.shuffle(order)
    train_ids, test_ids = order[:49].tolist(), order[49:].tolist()
    train_families = [families[index] for index in train_ids]
    test_families = [families[index] for index in test_ids]
    norm = FeatureNorm([row["sample"] for family in train_families for row in family])
    train_cps = np.asarray([row["label"]["Cps_pF"] for family in train_families for row in family])
    target_mean, target_std = float(np.log1p(train_cps).mean()), float(np.log1p(train_cps).std() + 1e-8)
    runs = []
    for name in ("pairwise", "pointwise"):
        torch.manual_seed(seed); np.random.seed(seed)
        model = PCBParasiticGNN(node_dim=9, edge_dim=7, hidden=96, n_layers=4, n_targets=1)
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
        rng = np.random.default_rng(seed)
        for _ in range(args.epochs):
            model.train(); active = np.asarray(train_ids); rng.shuffle(active)
            for family_id in active:
                family = families[int(family_id)]
                score = model(collate([norm.transform(row["sample"]) for row in family])).squeeze(-1)
                cps = torch.as_tensor([row["label"]["Cps_pF"] for row in family], dtype=torch.float32)
                if name == "pairwise":
                    left, right = torch.triu_indices(len(family), len(family), offset=1)
                    sign = torch.sign(cps[left] - cps[right])
                    loss = nn.functional.margin_ranking_loss(score[left], score[right], sign, margin=0.25)
                else:
                    target = (torch.log1p(cps) - target_mean) / target_std
                    loss = nn.functional.smooth_l1_loss(score, target)
                optimizer.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step()
            scheduler.step()
        rows, design_loss = evaluate(model, test_families, norm, name == "pointwise", target_mean, target_std)
        runs.append({"model": name, "seed": seed,
                     "spearman_mean": float(np.mean([row["spearman_rho"] for row in rows])),
                     "spearman_median": float(np.median([row["spearman_rho"] for row in rows])),
                     "selection_regret_median_pct": float(np.median([row["selection_regret_pct"] for row in rows])),
                     "selection_regret_mean_pct": float(np.mean([row["selection_regret_pct"] for row in rows])),
                     "family_loss": design_loss.tolist(), "families": rows})
        print(f"seed={seed} model={name} rho={runs[-1]['spearman_median']:.3f} regret={runs[-1]['selection_regret_median_pct']:.3f}%", flush=True)
    sources = [Path(__file__), CODE / "data/v3_dataset.py", CODE / "core/geometry_contract.py",
               CODE / "core/planar_to_graph.py", CODE / "models/gnn/gnn_baseline.py"]
    result = {"schema": SCHEMA,
              "provenance": {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "slurm_job_id": os.environ["SLURM_JOB_ID"], "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
                  "slurm_array_task_id": task_id, "hostname": socket.gethostname(), "platform": platform.platform(),
                  "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
                  "git_dirty_paths": dirty, "lateral_artifacts_sha256": summary["artifacts_sha256"],
                  "file_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources}},
              "protocol": {"split": "49 training and 21 held-out lateral families at fixed seed 42",
                           "initialization_seed": seed, "variants_per_family": 7,
                           "comparison": "pairwise margin ranking versus pointwise log-Cps regression"},
              "train_family_ids": train_ids, "test_family_ids": test_ids, "runs": runs}
    output = ROOT / "results/corpus_v3/ranking/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"; path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
