#!/usr/bin/env python3
"""SLURM-only initialized-model qualification; no corpus or fitting is used."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/models/gnn"))
import numpy as np
import torch
from gnn_baseline import collate
from strict_e3_ablation_v1 import SymmetryNormalizer, make_arms

SOURCES = (
    "code/models/gnn/strict_e3_ablation_v1.py",
    "code/models/gnn/gnn_baseline.py",
    "code/experiments/proofs/qualify_strict_e3_model_v1.py",
    "code/jobs/submit_qualify_strict_e3_model_v1.sh",
    "protocols/strict_e3_model_qualification_v1.json",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def residual(actual: np.ndarray, expected: np.ndarray) -> float:
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("nonfinite or mismatched qualification state")
    return float(np.max(np.abs(actual - expected)) / max(1.0, float(np.max(np.abs(expected)))))


def fixtures() -> dict:
    """Two artificial graphs, including an edgeless graph; no physical labels."""
    rng = np.random.default_rng(20260913)
    records = {}
    for index, count in enumerate((6, 3)):
        nodes = rng.normal(size=(count, 9))
        edge_index = np.array([(i, j) for i in range(count) for j in range(count) if i != j], dtype=np.int64).T if index == 0 else np.empty((2, 0), dtype=np.int64)
        edge = rng.normal(size=(edge_index.shape[1], 7))
        records[index] = {"node_feat": nodes, "edge_feat": edge,
                          "edge_index": edge_index, "reference_r3": np.array([10., 20., 30., 4.]) + index}
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    args = parser.parse_args()
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdigit() or os.environ.get("SLURM_ARRAY_JOB_ID"):
        raise ValueError("qualification requires a non-array SLURM job")
    if command("git", "rev-parse", "HEAD") != args.expected_source_commit:
        raise ValueError("source commit differs")
    if command("git", "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("tracked checkout must be clean")
    if command("git", "status", "--porcelain", "--untracked-files=all", "--", "code", "protocols"):
        raise ValueError("source namespace must be clean")
    protocol_path = ROOT / SOURCES[-1]
    if digest(protocol_path) != args.expected_protocol_sha256:
        raise ValueError("protocol hash differs")
    protocol = json.loads(protocol_path.read_text())
    runtime = {name: importlib.metadata.version(name) for name in ("numpy", "torch")}
    runtime["python"] = ".".join(map(str, sys.version_info[:3]))
    if runtime != protocol["runtime"]:
        raise ValueError("runtime differs from qualification protocol")
    if os.environ.get("PCB_E3_EXECUTED_BATCH_SHA256") != digest(ROOT / SOURCES[3]):
        raise ValueError("executed batch script differs")
    scheduler = command("scontrol", "show", "job", "-o", job)
    fields = dict(word.split("=", 1) for word in scheduler.split() if "=" in word)
    request = dict(item.split("=", 1) for item in fields.get("ReqTRES", "").split(",") if "=" in item)
    allocation = dict(item.split("=", 1) for item in fields.get("AllocTRES", "").split(",") if "=" in item)
    if fields.get("JobId") != job or fields.get("NumNodes") != "1" or fields.get("NumTasks") != "1" or int(fields.get("Restarts", "0")) != 0 or int(allocation.get("cpu", "0")) < 2:
        raise ValueError("unexpected scheduler identity, topology or restart")
    if fields.get("JobState") != "RUNNING" or fields.get("Partition") != "nextgen" or fields.get("Account") != "pgs0407" or request.get("cpu") != "2" or request.get("mem") != "16G" or fields.get("TimeLimit") != "00:10:00":
        raise ValueError("unexpected scheduler resource profile")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    records = fixtures()
    norm = SymmetryNormalizer(records, [0, 1])
    normalized = [norm.transform(records[i]) for i in (0, 1)]
    base_batch = collate(normalized)
    scale = float(norm.arrays()["norm.coordinate_scale"][0])
    results = []
    with torch.no_grad():
        for seed in protocol["seeds"]:
            arms, initialization = make_arms(seed)
            rng = np.random.default_rng(seed + protocol["transform_seed_offset"])
            transforms = []
            for index in range(protocol["transforms_per_seed"]):
                q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
                q[:, 0] *= (1 if index % 2 == 0 else -1) * np.linalg.det(q)
                transforms.append((q, rng.uniform(-2, 2, size=3)))
            for name, model in arms.items():
                model.eval()
                base_y, _, base_x = model.forward_states(base_batch)
                base_y, base_x = base_y.numpy(), base_x.numpy()
                maxima = {"scalar": 0., "coordinate": 0., "separate_batch": 0.}
                separate = np.concatenate([model(collate([sample])).numpy() for sample in normalized])
                maxima["separate_batch"] = residual(separate, base_y)
                for q, translation in transforms:
                    changed = copy.deepcopy(records)
                    for sample in changed.values():
                        sample["node_feat"][:, :3] = sample["node_feat"][:, :3] @ q.T + translation
                    transformed = collate([norm.transform(changed[i]) for i in (0, 1)])
                    observed_y, _, observed_x = model.forward_states(transformed)
                    maxima["scalar"] = max(maxima["scalar"], residual(observed_y.numpy(), base_y))
                    maxima["coordinate"] = max(maxima["coordinate"], residual(observed_x.numpy(), base_x @ q.T + translation / scale))
                results.append({"seed": seed, "arm": name, "max_relative_residual": maxima,
                                "passed": all(value <= protocol["relative_tolerance"] for value in maxima.values()),
                                "initialization": initialization})
    payload = {"schema": "pcb-gnn.strict-e3-model-qualification.v1", "scheduler_observed": fields,
               "source_git_head": args.expected_source_commit, "source_sha256": {name: digest(ROOT / name) for name in SOURCES},
               "runtime": runtime, "scientific_threads": 2, "protocol": protocol, "results": results,
               "passed": all(row["passed"] for row in results), "training_started": False,
               "corpus_bytes_opened": False, "claim_eligible": False}
    output = ROOT / "results/corpus_v4/strict_e3_fem_v2/qualification" / f"job_{job}" / "result.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open("x") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(output.relative_to(ROOT))
    if not payload["passed"]:
        raise SystemExit("initialized-model symmetry qualification failed")


if __name__ == "__main__":
    main()
