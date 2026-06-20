#!/usr/bin/env python3
"""
dump_predictions.py — reload the trained checkpoint and dump per-sample test-set
predictions vs reference (for parity / residual figures). No retraining.

Reproduces the exact 80/20 split from run_research13_pipeline.py (np default_rng
seeded shuffle, split BEFORE any other rng use) and the exact normalizations
stored in the checkpoint. Runs via sbatch on a compute node.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from gnn_baseline import PCBParasiticGNN, collate

TARGETS = ["Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../03_datasets/synth_v1")
    ap.add_argument("--ckpt", default="../05_experiments/run_v1/gnn_checkpoint.pt")
    ap.add_argument("--out", default="../05_experiments/run_v1/predictions.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data_dir = Path(args.data)
    layouts = [json.loads(l) for l in open(data_dir / "layouts.jsonl")]
    labels = {d["id"]: d for d in json.load(open(data_dir / "labels.json"))}

    ck = torch.load(args.ckpt, map_location="cpu")
    nf_mean, nf_std = (np.array(x) for x in ck["node_norm"])
    ef_mean, ef_std = (np.array(x) for x in ck["edge_norm"])
    y_mean, y_std = (np.array(x) for x in ck["y_log_norm"])

    samples = []
    for rec in layouts:
        lab = labels[rec["id"]]
        samples.append({
            "node_feat": np.asarray(rec["node_feat"], np.float32),
            "edge_feat": np.asarray(rec["edge_feat"], np.float32),
            "edge_index": np.asarray(rec["edge_index"], np.int64),
            "edge_dim": 7,
            "y_phys": np.array([lab[t] for t in TARGETS], np.float32),
        })
    n = len(samples)

    # exact split reproduction
    rng = np.random.default_rng(args.seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    n_test = max(1, int(0.2 * n))
    test_idx = idx[:n_test]

    # apply stored normalizations
    for s in samples:
        s["node_feat"] = ((s["node_feat"] - nf_mean) / nf_std).astype(np.float32)
        if s["edge_feat"].size:
            s["edge_feat"] = ((s["edge_feat"] - ef_mean) / ef_std).astype(np.float32)
        s["y"] = np.zeros(4, np.float32)

    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=ck["config"]["hidden"], n_layers=ck["config"]["layers"],
                            n_targets=4)
    model.load_state_dict(ck["state_dict"])
    model.eval()

    def from_norm(yn):
        yl = yn * y_std + y_mean
        return np.sign(yl) * np.expm1(np.abs(yl))

    preds, refs = [], []
    with torch.no_grad():
        for j in test_idx:
            b = collate([samples[j]])
            preds.append(from_norm(model(b).numpy()[0]).tolist())
            refs.append(samples[j]["y_phys"].tolist())

    out = {"targets": TARGETS, "pred": preds, "ref": refs, "n_test": len(test_idx)}
    Path(args.out).write_text(json.dumps(out))
    print(f"dumped {len(test_idx)} test predictions -> {args.out}")


if __name__ == "__main__":
    main()
