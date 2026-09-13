#!/usr/bin/env python3
"""Post-hoc, fixed-budget FEM-v2 baselines with isolated training and safe trees.

No solver is called. Training and held-out prediction require SLURM; hash-only
preflight and postterminal checkpoint admission are safe on a login node.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for directory in ("code/core", "code/data", "code/inference", "code/models/gnn", "code/experiments/proofs"):
    sys.path.insert(0, str(ROOT / directory))

from scientific_artifact import atomic_write_json, atomic_write_jsonl, sha256_file
from corpus_v4_accuracy_contract_v3 import (
    TARGETS, EXECUTION_SOURCE_NAMES, load_json, load_jsonl, canonical_task_row,
    metric_set, validate_slurm_allocation, validate_terminal_receipt,
    TERMINAL_RECEIPT_KEYS, validate_scheduler_receipt,
)
from corpus_v4_accuracy_dataset_v3 import load_training_split_dataset_v3
from run_corpus_v4_accuracy_task_v3 import (
    TrainOnlyNormalizer, _graph_samples, _source_state, _validate_training_sandbox,
)
from planar_to_graph import build_graph_from_planar_layout
from safe_npz_bundle import ArraySpec, load_safe_npz_bundle, write_safe_npz_bundle

BASE = "results/corpus_v4/baseline_fem_v2"
PLAN = "results/corpus_v4/accuracy_v3/plan/v1"
GNN = "results/corpus_v4/accuracy_v3/final/job_7102842"
PROTOCOL = "protocols/corpus_v4_baseline_fem_v2_v1.json"
WRAPPER = "code/jobs/submit_corpus_v4_baseline_v1.sh"
FINAL_WRAPPER = "code/jobs/submit_finalize_corpus_v4_baseline_v1.sh"
MODELS = ("constant", "ridge", "random_forest", "extra_trees")
SOURCES = sorted(set(EXECUTION_SOURCE_NAMES) | {
    "code/experiments/proofs/corpus_v4_baseline_v1.py", WRAPPER, FINAL_WRAPPER, PROTOCOL,
})


def checked_path(name: str) -> Path:
    """Reject absolute, escaping and symlink-mediated artifact paths."""
    path = Path(name)
    if path.is_absolute() or not path.parts or any(part in ("..", ".") for part in path.parts):
        raise ValueError("expected canonical repository-relative path")
    result = ROOT / path
    if result.resolve() != result.absolute() or not result.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("artifact path escapes root or traverses a symlink")
    return result


def pin(name: str) -> dict[str, str]:
    return {"path": name, "sha256": sha256_file(checked_path(name))}


def authenticate(record: Mapping[str, str]) -> Path:
    if set(record) != {"path", "sha256"}:
        raise ValueError("malformed artifact pin")
    path = checked_path(record["path"])
    if not path.is_file() or sha256_file(path) != record["sha256"]:
        raise ValueError(f"artifact hash mismatch: {record['path']}")
    return path


def canonical_argument(path: Path) -> Path:
    """Validate user-supplied absolute or relative paths before resolving them."""
    path = path if path.is_absolute() else ROOT / path
    if path.absolute() != path.resolve():
        raise ValueError("argument traverses a symlink or noncanonical path")
    return checked_path(path.relative_to(ROOT).as_posix())


def runtime() -> dict[str, str]:
    return {"python": platform.python_version(), **{
        name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn", "torch")
    }}


def pooled(block: np.ndarray) -> np.ndarray:
    """Pool standardized rows: mean, maximum, signed log1p of the sum."""
    block = np.asarray(block, dtype=np.float64)
    if block.ndim != 2 or not len(block) or not np.isfinite(block).all():
        raise ValueError("pooling requires finite nonempty feature rows")
    total = block.sum(axis=0)
    return np.concatenate((block.mean(axis=0), block.max(axis=0), np.sign(total) * np.log1p(np.abs(total))))


def features(sample: Mapping[str, Any], arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    blocks = []
    for kind, dim in (("node", 9), ("edge", 7)):
        raw = np.asarray(sample[f"{kind}_feat"], dtype=np.float64)
        if raw.ndim != 2 or raw.shape[1] != dim:
            raise ValueError("unexpected graph feature dimensions")
        blocks.append(np.zeros(dim * 3) if kind == "edge" and not len(raw) else
            pooled((raw - arrays[f"norm.{kind}_mean"]) / arrays[f"norm.{kind}_scale"]))
    return np.concatenate(blocks)


def pack_forest(model: Any, name: str) -> dict[str, np.ndarray]:
    """Store tree topology as bounded numeric arrays, never sklearn pickle."""
    offsets = np.cumsum([0] + [tree.tree_.node_count for tree in model.estimators_]).astype(np.int64)
    arrays = {f"{name}.offsets": offsets}
    for field in ("children_left", "children_right", "feature", "threshold"):
        arrays[f"{name}.{field}"] = np.concatenate([getattr(tree.tree_, field) for tree in model.estimators_])
    arrays[f"{name}.value"] = np.concatenate([tree.tree_.value[:, :, 0] for tree in model.estimators_])
    return arrays


def forest_predict(arrays: Mapping[str, np.ndarray], name: str, x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)  # sklearn tree prediction has this boundary.
    if x.ndim != 2 or x.shape[1] != 48 or not np.isfinite(x).all():
        raise ValueError("forest inputs must be finite rows of 48 features")
    offsets = arrays[f"{name}.offsets"]
    left, right, feat, threshold, values = [arrays[f"{name}.{field}"] for field in
        ("children_left", "children_right", "feature", "threshold", "value")]
    if offsets.ndim != 1 or offsets.dtype.kind not in "iu" or len(offsets) != 501:
        raise ValueError("forest requires exactly 500 trees")
    if offsets[0] != 0 or np.any(np.diff(offsets) <= 0) or offsets[-1] != len(left):
        raise ValueError("invalid packed forest offsets")
    if values.shape != (len(left), 4) or any(a.shape != left.shape for a in (right, feat, threshold)):
        raise ValueError("forest array shapes disagree")
    if any(a.dtype.kind not in "iu" for a in (left, right, feat)) or not np.isfinite(threshold).all() or not np.isfinite(values).all():
        raise ValueError("forest topology must be integer and values finite")
    output = np.zeros((len(x), 4), dtype=np.float64)
    for start, stop in zip(offsets[:-1], offsets[1:]):
        count = stop - start
        ll, rr, ff = left[start:stop], right[start:stop], feat[start:stop]
        leaves = ll == -1
        internal = ~leaves
        if np.any(rr[leaves] != -1) or np.any(ll[internal] <= np.flatnonzero(internal)) or np.any(rr[internal] <= np.flatnonzero(internal)):
            raise ValueError("tree must be forward ordered and acyclic")
        if np.any(ll[internal] >= count) or np.any(rr[internal] >= count) or np.any((ff[internal] < 0) | (ff[internal] >= 48)):
            raise ValueError("invalid tree child or feature index")
        incoming = np.bincount(np.concatenate((ll[internal], rr[internal])), minlength=count)
        if incoming[0] != 0 or np.any(incoming[1:] != 1):
            raise ValueError("every non-root tree node must have exactly one parent")
        depths = np.zeros(count, dtype=np.int64)
        for node in np.flatnonzero(internal):
            depths[ll[node]] = depths[node] + 1
            depths[rr[node]] = depths[node] + 1
        if depths.max() > 16:
            raise ValueError("forest exceeds frozen depth 16")
        positions = np.zeros(len(x), dtype=np.int64)
        for _depth in range(17):
            active = ll[positions] != -1
            if not active.any():
                break
            rows = np.flatnonzero(active)
            old = positions[rows]
            positions[rows] = np.where(x[rows, ff[old]] <= threshold[start + old], ll[old], rr[old])
        if np.any(ll[positions] != -1):
            raise ValueError("forest exceeds frozen depth 16")
        output += values[start + positions]
    return output / 500.0


def predict(arrays: Mapping[str, np.ndarray], name: str, x: np.ndarray) -> np.ndarray:
    if name == "constant":
        standardized = np.zeros((len(x), 4), dtype=np.float64)
    elif name == "ridge":
        standardized = x @ arrays["ridge.coef"].T + arrays["ridge.intercept"]
    elif name in MODELS[2:]:
        standardized = forest_predict(arrays, name, x)
    else:
        raise ValueError("unknown frozen model")
    with np.errstate(over="raise", invalid="raise"):
        result = np.expm1(standardized * arrays["norm.target_log1p_scale"] + arrays["norm.target_log1p_mean"])
    if not np.isfinite(result).all():
        raise ValueError("nonfinite prediction")
    return result  # Negative predictions are retained and counted, not clipped.


def fit_models(x: np.ndarray, y: np.ndarray, seed: int) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
    from sklearn.linear_model import Ridge
    constructors = {
        "ridge": Ridge(alpha=1.0, solver="svd"),
        "random_forest": RandomForestRegressor(n_estimators=500, max_depth=16, min_samples_leaf=2,
            max_features=1.0, bootstrap=True, criterion="squared_error", random_state=seed, n_jobs=8),
        "extra_trees": ExtraTreesRegressor(n_estimators=500, max_depth=16, min_samples_leaf=2,
            max_features=1.0, bootstrap=False, criterion="squared_error", random_state=seed, n_jobs=8),
    }
    arrays, durations = {}, {"constant": 0.0}
    for name, model in constructors.items():
        started = time.perf_counter()
        model.fit(x, y)
        durations[name] = time.perf_counter() - started
        if name == "ridge":
            arrays.update({"ridge.coef": model.coef_, "ridge.intercept": model.intercept_})
        else:
            arrays.update(pack_forest(model, name))
            np.testing.assert_allclose(forest_predict(arrays, name, x[:5]), model.predict(x[:5]), rtol=1e-12, atol=1e-12)
    return arrays, durations


def build_lock(args: argparse.Namespace) -> None:
    protocol = load_json(args.protocol)
    if sha256_file(args.protocol) != args.expected_protocol_sha256:
        raise ValueError("protocol hash mismatch")
    validate_protocol_config(protocol)
    for name, digest in protocol["upstream"].items():
        authenticate({"path": name, "sha256": digest})
    names = [f"{PLAN}/plan.json", f"{PLAN}/task_manifest.jsonl", f"{PLAN}/evaluation_dataset.jsonl",
        "datasets/corpus_v3/layouts.jsonl", "results/corpus_v4/accuracy_v3/ARCHIVE_MANIFEST.json",
        f"{GNN}/ANALYSIS_MANIFEST.json", f"{GNN}/summary.json"]
    names += [f"{PLAN}/training_split_{seed}.jsonl" for seed in range(40, 45)]
    names += [f"{GNN}/predictions/task_{task:02d}.jsonl" for task in range(25)]
    upstream = load_json(ROOT / "protocols/corpus_v4_accuracy_v3.json")
    plan = load_json(ROOT / PLAN / "plan.json")
    if plan["protocol_sha256"] != protocol["upstream"]["protocols/corpus_v4_accuracy_v3.json"]:
        raise ValueError("admitted plan protocol root mismatch")
    for name, digest in plan["artifact_sha256"].items():
        authenticate({"path": f"{PLAN}/{name}", "sha256": digest})
    for record in upstream["inputs"].values():
        authenticate(record)
    for name, digest in plan["planner_source_sha256"].items():
        authenticate({"path": name, "sha256": digest})
    names += [record["path"] for record in upstream["inputs"].values()]
    archive = load_json(ROOT / "results/corpus_v4/accuracy_v3/ARCHIVE_MANIFEST.json")
    authenticate(archive["analysis_manifest"])
    for name, digest in archive["verified_analysis_files_sha256"].items():
        authenticate({"path": f"{GNN}/{name}", "sha256": digest})
    for task in range(25):
        name = f"predictions/task_{task:02d}.jsonl"
        if sha256_file(ROOT / GNN / name) != archive["verified_analysis_files_sha256"][name]:
            raise ValueError("GNN predictions do not match admitted archive")
    if args.execution_lock.exists():
        raise ValueError("refusing lock overwrite")
    atomic_write_json(args.execution_lock, {"schema": "pcb-gnn.baseline-lock.v1",
        "protocol_sha256": args.expected_protocol_sha256,
        "source_sha256": {name: sha256_file(checked_path(name)) for name in SOURCES},
        "inputs": {name: sha256_file(checked_path(name)) for name in sorted(set(names))},
        "runtime": protocol["runtime"]})


def validate_protocol_config(protocol: dict) -> None:
    """Fail closed if JSON knobs no longer describe the implemented models."""
    if protocol.get("schema") != "pcb-gnn.corpus-v4-baseline-protocol.v1" or protocol.get("seeds") != {
        "split": list(range(40, 45)), "init": list(range(40, 45)), "tasks": 25}:
        raise ValueError("unsupported baseline protocol/grid")
    if protocol.get("targets") != list(TARGETS) or set(protocol.get("models", {})) != set(MODELS):
        raise ValueError("unsupported baseline models/targets")
    expected_trees = {"n_estimators": 500, "max_depth": 16, "min_samples_leaf": 2,
        "max_features": 1.0, "criterion": "squared_error", "n_jobs": 8}
    for name in MODELS[2:]:
        if protocol["models"][name] != {**expected_trees, "bootstrap": name == "random_forest"}:
            raise ValueError("tree configuration differs from implementation")
    if protocol["models"]["ridge"] != {"alpha": 1.0, "solver": "svd", "fit_intercept": True, "deterministic": True}:
        raise ValueError("ridge configuration differs from implementation")
    if protocol["models"]["constant"] != {"prediction": "train mean log1p target", "deterministic": True}:
        raise ValueError("constant configuration differs from implementation")
    if protocol["optimization"] != {"hyperparameter_search_trials": 0, "validation": "diagnostic only",
        "refit_train_plus_validation": False, "model_selection": "none; report every fixed model"}:
        raise ValueError("unsupported optimization policy")
    if tuple(protocol["features"][key] for key in ("node_dim", "edge_dim", "pooled_dim")) != (9, 7, 48):
        raise ValueError("unsupported feature dimensions")
    if protocol["evaluation"]["heldout_inference_before_all_checkpoint_admission"] is not False or protocol["evaluation"]["prediction_clipping"] is not False:
        raise ValueError("unsupported evaluation policy")
    if protocol["evaluation"]["resampling"] != {"resamples": 10000, "seed": 20260913,
        "percentiles": [2.5, 97.5], "axes": ["split", "initialization"], "paired_draws": True,
        "semantics": "descriptive seed-grid sensitivity interval, not a population confidence interval"}:
        raise ValueError("unsupported paired resampling policy")
    if protocol["evaluation"]["joint_prediction_diagnostics"] != {"inductance_psd": True,
        "relative_tolerance": 1e-9, "integrity_gate": False, "repair_predictions": False}:
        raise ValueError("unsupported prediction integrity diagnostic")
    if protocol["checkpoint"] != {"format": "numeric NPZ allow_pickle=False; packed tree arrays",
        "max_archive_bytes": 67108864, "max_expanded_bytes": 268435456}:
        raise ValueError("checkpoint limits differ from safe loader defaults")


def context(args: argparse.Namespace, *, training: bool = False) -> tuple[dict, dict, list]:
    if sha256_file(args.protocol) != args.expected_protocol_sha256 or sha256_file(args.execution_lock) != args.expected_execution_lock_sha256:
        raise ValueError("external protocol/lock hash mismatch")
    protocol, lock = load_json(args.protocol), load_json(args.execution_lock)
    validate_protocol_config(protocol)
    if lock["protocol_sha256"] != args.expected_protocol_sha256 or set(lock["source_sha256"]) != set(SOURCES):
        raise ValueError("lock closure differs")
    for name, digest in lock["source_sha256"].items():
        if sha256_file(checked_path(name)) != digest:
            raise ValueError(f"source mismatch: {name}")
    if runtime() != protocol["runtime"] or lock["runtime"] != protocol["runtime"]:
        raise ValueError("runtime mismatch")
    head, dirty, untracked = _source_state()
    if (head != args.expected_source_git_head and args.stage != "verify") or dirty or untracked:
        raise ValueError("execution must use externally pinned clean source")
    for name in (f"{PLAN}/plan.json", f"{PLAN}/task_manifest.jsonl"):
        if sha256_file(checked_path(name)) != lock["inputs"][name]:
            raise ValueError("upstream plan mismatch")
    rows = load_jsonl(ROOT / PLAN / "task_manifest.jsonl")
    if len(rows) != 25 or any(any(row[k] != v for k, v in canonical_task_row(i).items()) for i, row in enumerate(rows)):
        raise ValueError("task grid differs from frozen upstream")
    if not training:
        for name, digest in lock["inputs"].items():
            if sha256_file(checked_path(name)) != digest:
                raise ValueError(f"upstream input mismatch: {name}")
    return protocol, lock, rows


def execution(args: argparse.Namespace, protocol: dict, lock: dict, stage: str) -> dict:
    scheduler = validate_slurm_allocation(protocol, stage=stage,
        allowed_training_task_ids=[0] if stage == "training" and args.probe_only else None)
    wrapper = WRAPPER if stage == "training" else FINAL_WRAPPER
    actual = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected = lock["source_sha256"][wrapper]
    if not actual.is_file() or sha256_file(actual) != expected or os.environ.get("PCB_GNN_EXECUTED_BATCH_SHA256") != expected:
        raise ValueError("executed scheduler script differs from locked bytes")
    return scheduler


def bindings(args: argparse.Namespace) -> dict:
    return {"protocol_sha256": args.expected_protocol_sha256,
        "execution_lock_sha256": args.expected_execution_lock_sha256,
        "source_git_head": args.expected_source_git_head}


def train(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args, training=True)
    scheduler = execution(args, protocol, lock, "training")
    task = int(scheduler["array_task_id"])
    row = rows[task]
    sandbox = _validate_training_sandbox(protocol, row)
    name = f"{PLAN}/{row['training_dataset']['path']}"
    if lock["inputs"][name] != row["training_dataset"]["sha256"]:
        raise ValueError("training pin mismatch")
    dataset = load_training_split_dataset_v3(authenticate({"path": name, "sha256": lock["inputs"][name]}),
        expected_sha256=lock["inputs"][name], task_row=row)
    output = args.output_root
    if not output.is_dir() or any(output.iterdir()) or output.is_symlink():
        raise ValueError("task-private output must be an existing empty real directory")
    expected_output = ROOT / BASE / ("probes" if args.probe_only else "jobs") / f"job_{scheduler['array_job_id']}" / f"task_{task:02d}"
    if canonical_argument(output) != expected_output:
        raise ValueError("task-private output path differs from scheduler identity")
    if list(expected_output.parent.iterdir()) != [expected_output]:
        raise ValueError("sandbox exposes another task's output")
    forbidden_baseline_roots = [ROOT / BASE / name for name in ("final", "resume", "ARCHIVE_MANIFEST.json")]
    if any(path.exists() for path in forbidden_baseline_roots):
        raise ValueError("sandbox exposes baseline evaluation/admission artifacts")
    sandbox = {**sandbox, "task_private_output_only": True,
        "other_task_checkpoints_visible": False, "baseline_heldout_artifacts_visible": False}
    receipt = {"schema": "pcb-gnn.baseline-task.v1", "bindings": bindings(args),
        "task": canonical_task_row(task), "scheduler": scheduler, "sandbox": sandbox,
        "source_sha256": lock["source_sha256"], "runtime": runtime(),
        "training_dataset": {"path": name, "sha256": lock["inputs"][name]},
        "heldout_bytes_opened": False, "training_started": not args.probe_only}
    if args.probe_only:
        atomic_write_json(output / "probe.json", receipt)
        print(output.resolve().as_posix())
        return
    samples = _graph_samples(dataset)
    train_ids, validation_ids = list(dataset.train_layout_ids), list(dataset.validation_layout_ids)
    normalizer = TrainOnlyNormalizer(samples, train_ids)
    arrays = normalizer.arrays()
    x = np.stack([features(samples[index], arrays) for index in train_ids])
    arrays["norm.pooled_mean"] = x.mean(axis=0)
    arrays["norm.pooled_scale"] = np.maximum(x.std(axis=0), 1e-6)
    x = standardize_pooled(x, arrays)
    y = np.stack([samples[index]["reference_r3"] for index in train_ids])
    y = (np.log1p(y) - arrays["norm.target_log1p_mean"]) / arrays["norm.target_log1p_scale"]
    fitted, durations = fit_models(x, y, row["init_seed"])
    arrays.update(fitted)
    arrays = {name: np.ascontiguousarray(value) for name, value in arrays.items()}
    specs = {name: ArraySpec(value.dtype.str, value.shape) for name, value in arrays.items()}
    receipt["bundle_specs"] = {name: spec.to_json() for name, spec in specs.items()}
    receipt["fit_seconds"] = durations
    xv = standardize_pooled(np.stack([features(samples[index], arrays) for index in validation_ids]), arrays)
    yv = np.stack([samples[index]["reference_r3"] for index in validation_ids])
    families = [samples[index]["family_id"] for index in validation_ids]
    receipt["validation_diagnostic"] = {name: {target: metric_set(predict(arrays, name, xv)[:, j], yv[:, j], families)
        for j, target in enumerate(TARGETS)} for name in MODELS}
    write_safe_npz_bundle(output / "bundle", arrays=arrays, specs=specs,
        payload={"bindings": bindings(args), "task": canonical_task_row(task), "models": list(MODELS)})
    receipt["files"] = {name: sha256_file(output / name) for name in ("bundle/metadata.json", "bundle/weights_and_norm.npz")}
    atomic_write_json(output / "result.json", receipt)
    print(output.resolve().as_posix())


def terminal(scheduler: dict, stage: str) -> dict:
    fields = list(TERMINAL_RECEIPT_KEYS) + ["Restarts", "Partition", "Timelimit"]
    text = subprocess.run(["sacct", "-X", "-n", "-P", "-j", str(scheduler["job_id"]),
        "--format=" + ",".join(fields)], check=True, capture_output=True, text=True).stdout
    rows = [dict(zip(fields, line.split("|"))) for line in text.splitlines() if len(line.split("|")) == len(fields)]
    rows = [row for row in rows if row["JobIDRaw"] == str(scheduler["job_id"])]
    if len(rows) != 1:
        raise ValueError("terminal accounting is unavailable or ambiguous")
    row = rows[0]
    if row["Restarts"] != "0" or row["Partition"] != "nextgen" or row["Timelimit"] != ("04:00:00" if stage == "training" else "00:30:00"):
        raise ValueError("terminal restart/resource boundary mismatch")
    validate_terminal_receipt(scheduler, {key: row[key] for key in TERMINAL_RECEIPT_KEYS}, stage=stage)
    return row


def check_task(args: argparse.Namespace, path: Path, task_id: int, lock: dict, rows: list) -> dict:
    result = load_json(path)
    if result["bindings"] != bindings(args) or result["task"] != canonical_task_row(task_id):
        raise ValueError("task identity or source bindings mismatch")
    validate_scheduler_receipt(result["scheduler"], stage="training", task_id=task_id)
    expected_dir = ROOT / BASE / "jobs" / f"job_{result['scheduler']['array_job_id']}" / f"task_{task_id:02d}"
    if path.parent.absolute() != expected_dir or path.name != "result.json":
        raise ValueError("task path does not match scheduler identity")
    if result["source_sha256"] != lock["source_sha256"] or result["runtime"] != lock["runtime"]:
        raise ValueError("task source/runtime mismatch")
    if result.get("heldout_bytes_opened") is not False or result.get("training_started") is not True or result["sandbox"].get("filesystem_boundary_passed") is not True:
        raise ValueError("task did not satisfy isolated training gate")
    training = rows[task_id]["training_dataset"]
    if result["training_dataset"] != {"path": f"{PLAN}/{training['path']}", "sha256": training["sha256"]}:
        raise ValueError("task used a different training dataset")
    if set(result["files"]) != {"bundle/metadata.json", "bundle/weights_and_norm.npz"}:
        raise ValueError("unexpected checkpoint inventory")
    actual = {p.relative_to(path.parent).as_posix() for p in path.parent.rglob("*") if p.is_file()}
    if actual != {"result.json", *result["files"]} or any(p.is_symlink() for p in path.parent.rglob("*")):
        raise ValueError("unexpected files or symlinks in task")
    for name, digest in result["files"].items():
        if sha256_file(path.parent / name) != digest:
            raise ValueError("checkpoint hash mismatch")
    arrays = load_arrays(path, result)
    for model in MODELS[2:]:
        forest_predict(arrays, model, np.zeros((1, 48), dtype=np.float64))
    return result


def admit(args: argparse.Namespace) -> None:
    _protocol, lock, rows = context(args)
    root = canonical_argument(args.attempt_root)
    if sorted(p.name for p in root.iterdir()) != [f"task_{i:02d}" for i in range(25)]:
        raise ValueError("admission requires exactly 25 tasks and no extra attempts")
    accepted = []
    for task in range(25):
        path = root / f"task_{task:02d}" / "result.json"
        result = check_task(args, path, task, lock, rows)
        accepted.append({"task_id": task, "result": pin(path.relative_to(ROOT).as_posix()),
            "terminal": terminal(result["scheduler"], "training")})
    if len({load_json(authenticate(item["result"]))["scheduler"]["array_job_id"] for item in accepted}) != 1:
        raise ValueError("all cells must come from one fixed no-retry array")
    if args.accepted_set.exists():
        raise ValueError("refusing accepted-set overwrite")
    atomic_write_json(args.accepted_set, {"schema": "pcb-gnn.baseline-accepted.v1", "bindings": bindings(args),
        "accepted": accepted, "heldout_inference_permitted": True, "claim_eligible": False})


def accepted_tasks(args: argparse.Namespace, lock: dict, rows: list) -> list:
    canonical_argument(args.accepted_set)
    if sha256_file(args.accepted_set) != args.expected_accepted_set_sha256:
        raise ValueError("accepted set hash mismatch")
    accepted = load_json(args.accepted_set)
    if accepted["bindings"] != bindings(args) or accepted.get("heldout_inference_permitted") is not True:
        raise ValueError("accepted set bindings/decision mismatch")
    if [row["task_id"] for row in accepted["accepted"]] != list(range(25)):
        raise ValueError("accepted set must cover all 25 tasks exactly")
    results = []
    for item in accepted["accepted"]:
        path = authenticate(item["result"])
        result = check_task(args, path, item["task_id"], lock, rows)
        if terminal(result["scheduler"], "training") != item["terminal"]:
            raise ValueError("accepted terminal receipt changed")
        results.append((path, result))
    if len({result["scheduler"]["job_id"] for _path, result in results}) != 25 or len({result["scheduler"]["array_job_id"] for _path, result in results}) != 1:
        raise ValueError("accepted set requires distinct task jobs from one array")
    return results


def load_arrays(path: Path, result: dict) -> Mapping[str, np.ndarray]:
    required = {"norm.node_mean": (9,), "norm.node_scale": (9,), "norm.edge_mean": (7,),
        "norm.edge_scale": (7,), "norm.target_log1p_mean": (4,), "norm.target_log1p_scale": (4,),
        "norm.pooled_mean": (48,), "norm.pooled_scale": (48,), "ridge.coef": (4, 48), "ridge.intercept": (4,)}
    expected_names = set(required) | {f"{model}.{field}" for model in MODELS[2:] for field in
        ("offsets", "children_left", "children_right", "feature", "threshold", "value")}
    if set(result["bundle_specs"]) != expected_names:
        raise ValueError("checkpoint array names differ from frozen schema")
    specs = {name: ArraySpec(spec["dtype"], tuple(spec["shape"]), spec["strictly_positive"])
        for name, spec in result["bundle_specs"].items()}
    for name, shape in required.items():
        if specs[name].shape != shape or np.dtype(specs[name].dtype) != np.dtype("float64"):
            raise ValueError("normalizer/ridge checkpoint schema mismatch")
    for model in MODELS[2:]:
        count = specs[f"{model}.children_left"].shape[0]
        if not 500 <= count <= 2000000:
            raise ValueError("packed forest node count exceeds bound")
        for field in ("offsets", "children_left", "children_right", "feature", "threshold", "value"):
            expected_shape = (501,) if field == "offsets" else ((count, 4) if field == "value" else (count,))
            expected_dtype = "float64" if field in ("threshold", "value") else "int64"
            if specs[f"{model}.{field}"].shape != expected_shape or np.dtype(specs[f"{model}.{field}"].dtype) != np.dtype(expected_dtype):
                raise ValueError("packed forest schema mismatch")
    loaded = load_safe_npz_bundle(path.parent / "bundle",
        expected_metadata_sha256=result["files"]["bundle/metadata.json"], expected_specs=specs,
        expected_payload={"bindings": result["bindings"], "task": result["task"], "models": list(MODELS)})
    if any(np.any(loaded.arrays[name] <= 0) for name in required if name.endswith("scale")):
        raise ValueError("checkpoint normalizer scales must be positive")
    return loaded.arrays


def standardize_pooled(x: np.ndarray, arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    result = (x - arrays["norm.pooled_mean"]) / arrays["norm.pooled_scale"]
    if not np.isfinite(result).all():
        raise ValueError("nonfinite standardized pooled features")
    return result


def passivity_diagnostic(prediction: np.ndarray) -> dict:
    """Report, never repair, violations of the two-winding inductance PSD test."""
    values = np.asarray(prediction, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 4 or not np.isfinite(values).all():
        raise ValueError("passivity diagnostic requires finite four-target rows")
    lp, ls, mutual = values[:, 1], values[:, 2], values[:, 3]
    tolerance = 1e-9
    invalid_diagonal = (lp < 0) | (ls < 0)
    determinant_bad = mutual ** 2 > np.maximum(lp * ls, 0.0) * (1.0 + tolerance)
    invalid = invalid_diagonal | determinant_bad
    return {"n_samples": len(values), "n_nonpositive_target_predictions": int((values <= 0).sum()),
        "n_inductance_psd_violations": int(invalid.sum()), "inductance_psd_violation_rate_pct": float(100 * invalid.mean()),
        "relative_tolerance": tolerance, "integrity_gate": False, "predictions_repaired": False}


def evaluate(args: argparse.Namespace, lock: dict, rows: list) -> tuple[list, list]:
    accepted = accepted_tasks(args, lock, rows)  # Admission is replayed before held-out materialization.
    layouts = {row["layout_id"]: row for row in load_jsonl(ROOT / "datasets/corpus_v3/layouts.jsonl")}
    refs = {row["layout_id"]: row for row in load_jsonl(ROOT / PLAN / "evaluation_dataset.jsonl")}
    predictions, metrics = [], []
    for task, (path, result) in enumerate(accepted):
        arrays = load_arrays(path, result)
        ids = rows[task]["partitions"]["test"]["layout_ids"]
        samples = []
        for index in ids:
            layout = layouts[index]
            if layout["geometry_sha256"] != refs[index]["geometry_sha256"]:
                raise ValueError("held-out geometry identity mismatch")
            nf, ef, _ei = build_graph_from_planar_layout(layout["layout"]).to_feature_matrices()
            samples.append(features({"node_feat": nf, "edge_feat": ef}, arrays))
        x = standardize_pooled(np.stack(samples), arrays)
        reference = np.array([[refs[index]["training_reference"][target]["value"] for target in TARGETS] for index in ids])
        family = [refs[index]["family_id"] for index in ids]
        gnn = load_jsonl(ROOT / GNN / f"predictions/task_{task:02d}.jsonl")
        if [row["layout_id"] for row in gnn] != ids:
            raise ValueError("GNN pairing membership mismatch")
        for n, row in enumerate(gnn):
            if row["family_id"] != family[n] or row["geometry_sha256"] != refs[ids[n]]["geometry_sha256"] or row["reference_r3"] != reference[n].tolist():
                raise ValueError("GNN pairing reference mismatch")
        gp = np.asarray([row["prediction"] for row in gnn])
        gm = [metric_set(gp[:, j], reference[:, j], family) for j in range(4)]
        for model in MODELS:
            prediction = predict(arrays, model, x)
            for n, index in enumerate(ids):
                predictions.append({"task_id": task, "model": model, "layout_id": index,
                    "family_id": family[n], "geometry_sha256": refs[index]["geometry_sha256"],
                    "prediction": prediction[n].tolist(), "reference_r3": reference[n].tolist()})
            for j, target in enumerate(TARGETS):
                metric = metric_set(prediction[:, j], reference[:, j], family)
                metrics.append({"task_id": task, "split_seed": rows[task]["split_seed"],
                    "init_seed": rows[task]["init_seed"], "model": model, "target": target, "metrics": metric,
                    "joint_prediction_diagnostic": passivity_diagnostic(prediction),
                    "gnn_joint_prediction_diagnostic": passivity_diagnostic(gp),
                    "gnn_metrics": gm[j], "paired_family_macro_mape_difference_pp":
                    metric["family_macro_mape_pct"] - gm[j]["family_macro_mape_pct"]})
    return predictions, metrics


def summarize(metrics: list) -> dict:
    cells = {}
    rng = np.random.default_rng(20260913)
    split_draws = rng.integers(0, 5, size=(10000, 5))
    init_draws = rng.integers(0, 5, size=(10000, 5))
    for model in MODELS:
        cells[model] = {}
        for target in TARGETS:
            selected = [row for row in metrics if row["model"] == model and row["target"] == target]
            if len(selected) != 25 or sorted(row["task_id"] for row in selected) != list(range(25)):
                raise ValueError("metric grid incomplete")
            for row in selected:
                task = canonical_task_row(row["task_id"])
                if any(row[key] != task[key] for key in ("split_seed", "init_seed")):
                    raise ValueError("metric seed mapping differs from frozen task grid")
                expected = row["metrics"]["family_macro_mape_pct"] - row["gnn_metrics"]["family_macro_mape_pct"]
                if not np.isfinite(expected) or abs(row["paired_family_macro_mape_difference_pp"] - expected) > 1e-12:
                    raise ValueError("paired metric difference sign/value mismatch")
            selected.sort(key=lambda row: row["task_id"])
            delta = np.asarray([row["paired_family_macro_mape_difference_pp"] for row in selected])
            resampled = delta.reshape(5, 5)[split_draws[:, :, None], init_draws[:, None, :]].mean(axis=(1, 2))
            cells[model][target] = {"mean_family_macro_mape_pct": float(np.mean([row["metrics"]["family_macro_mape_pct"] for row in selected])),
                "mean_paired_difference_pp": float(delta.mean()), "paired_difference_min_pp": float(delta.min()),
                "paired_difference_max_pp": float(delta.max()), "cells_better_than_gnn": int((delta < 0).sum()),
                "paired_difference_crossed_axis_95pct_interval_pp": np.quantile(resampled, [0.025, 0.975], method="linear").tolist(),
                "deterministic_model_repeated_initializations": model in MODELS[:2]}
    return {"models": cells, "scope": "post-hoc fixed-budget benchmark; no causal graph advantage or population confidence claim",
        "difference_sign": "baseline minus GNN; positive means lower GNN family-macro MAPE",
        "split_panels_independent": False, "n_cells": 25, "hyperparameter_search_trials": 0,
        "resampling": {"resamples": 10000, "seed": 20260913, "axes": ["split", "initialization"],
            "pairing": "shared crossed-axis draws of baseline-minus-GNN cell differences",
            "semantics": "descriptive seed-grid sensitivity interval, not a population confidence interval",
            "deterministic_controls": "initialization resampling reflects paired GNN variability, not additional constant/ridge fits"}}


def finalize(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args)
    scheduler = execution(args, protocol, lock, "finalizer")
    output = args.output_root / f"job_{scheduler['job_id']}"
    output.mkdir(parents=True, exist_ok=False)
    predictions, metrics = evaluate(args, lock, rows)
    summary = {"schema": "pcb-gnn.baseline-analysis.v1", "bindings": bindings(args),
        "accepted_set_sha256": args.expected_accepted_set_sha256, "scheduler": scheduler,
        "results": summarize(metrics), "claim_eligible": False}
    atomic_write_jsonl(output / "predictions.jsonl", predictions)
    atomic_write_json(output / "metrics.json", {"cells": metrics})
    atomic_write_json(output / "summary.json", summary)
    atomic_write_json(output / "ANALYSIS_MANIFEST.json", {"bindings": bindings(args),
        "files": {name: sha256_file(output / name) for name in ("predictions.jsonl", "metrics.json", "summary.json")}})
    print(output.resolve().as_posix())


def verify(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args)
    execution(args, protocol, lock, "finalizer")
    canonical_argument(args.analysis_manifest)
    if sha256_file(args.analysis_manifest) != args.expected_analysis_manifest_sha256:
        raise ValueError("analysis manifest hash mismatch")
    manifest = load_json(args.analysis_manifest)
    if manifest["bindings"] != bindings(args) or set(manifest["files"]) != {"predictions.jsonl", "metrics.json", "summary.json"}:
        raise ValueError("analysis manifest closure mismatch")
    folder = args.analysis_manifest.resolve().parent
    checked_path(folder.relative_to(ROOT).as_posix())
    if {path.name for path in folder.iterdir()} != {"ANALYSIS_MANIFEST.json", "predictions.jsonl", "metrics.json", "summary.json"} or any(path.is_symlink() or not path.is_file() for path in folder.iterdir()):
        raise ValueError("analysis output inventory differs or contains symlinks")
    for name, digest in manifest["files"].items():
        if sha256_file(args.analysis_manifest.parent / name) != digest:
            raise ValueError("analysis artifact hash mismatch")
    summary = load_json(args.analysis_manifest.parent / "summary.json")
    if folder.name != f"job_{summary['scheduler']['job_id']}":
        raise ValueError("finalizer directory differs from scheduler identity")
    completion = terminal(summary["scheduler"], "finalizer")
    predictions, metrics = evaluate(args, lock, rows)
    if load_jsonl(args.analysis_manifest.parent / "predictions.jsonl") != predictions or load_json(args.analysis_manifest.parent / "metrics.json") != {"cells": metrics} or summary["results"] != summarize(metrics):
        raise ValueError("independent numerical replay differs")
    if summary["bindings"] != bindings(args) or summary["accepted_set_sha256"] != args.expected_accepted_set_sha256:
        raise ValueError("summary binding mismatch")
    if args.out.exists():
        if not args.check:
            raise ValueError("refusing archive receipt overwrite")
    receipt = {"schema": "pcb-gnn.baseline-archive.v1", "bindings": bindings(args),
        "analysis_manifest": pin(args.analysis_manifest.resolve().relative_to(ROOT).as_posix()),
        "accepted_set": pin(args.accepted_set.resolve().relative_to(ROOT).as_posix()),
        "finalizer_terminal": completion, "numerical_reconstruction_passed": True, "claim_eligible": False}
    if args.require_git_tracked:
        names = set(lock["source_sha256"]) | set(lock["inputs"])
        names.update(p.relative_to(ROOT).as_posix() for p in args.analysis_manifest.parent.rglob("*") if p.is_file())
        names.update((args.accepted_set.resolve().relative_to(ROOT).as_posix(), args.out.resolve().relative_to(ROOT).as_posix()))
        for item in load_json(args.accepted_set)["accepted"]:
            task_path = authenticate(item["result"])
            names.update(p.relative_to(ROOT).as_posix() for p in task_path.parent.rglob("*") if p.is_file())
        subprocess.run(["git", "ls-files", "--error-unmatch", "--", *sorted(names)], cwd=ROOT, check=True, capture_output=True)
    if args.check:
        if load_json(args.out) != receipt:
            raise ValueError("archive receipt replay differs")
    else:
        atomic_write_json(args.out, receipt)
    print("baseline archive replay passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build-lock", "validate", "train", "admit", "finalize", "verify"))
    parser.add_argument("--protocol", type=Path, default=ROOT / PROTOCOL)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--output-root", type=Path, default=ROOT / BASE / "jobs")
    parser.add_argument("--attempt-root", type=Path)
    parser.add_argument("--accepted-set", type=Path)
    parser.add_argument("--expected-accepted-set-sha256")
    parser.add_argument("--analysis-manifest", type=Path)
    parser.add_argument("--expected-analysis-manifest-sha256")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    if args.stage != "build-lock" and (not args.expected_execution_lock_sha256 or not args.expected_source_git_head):
        parser.error("execution lock SHA and source commit are required")
    if args.stage in ("finalize", "verify") and (not args.accepted_set or not args.expected_accepted_set_sha256):
        parser.error("externally authenticated accepted set required")
    if args.stage == "validate":
        context(args)
        print("baseline validation passed; no training or prediction")
    else:
        {"build-lock": build_lock, "train": train, "admit": admit, "finalize": finalize, "verify": verify}[args.stage](args)


if __name__ == "__main__":
    main()
