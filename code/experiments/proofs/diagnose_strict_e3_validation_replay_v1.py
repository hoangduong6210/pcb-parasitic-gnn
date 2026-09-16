#!/usr/bin/env python3
"""Validation-only, process-isolated thread-count replay of frozen checkpoints.

This diagnostic cannot admit checkpoints or change the frozen replay tolerance.
Each subprocess loads task zero and predicts only its split-40 validation rows.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

FROZEN_COMMIT = "efeb123c9975ae481d10cd7c0af899406c46e787"
SCRIPT = "code/experiments/proofs/diagnose_strict_e3_validation_replay_v1.py"
WRAPPER = "code/jobs/submit_diagnose_strict_e3_validation_replay_v1.sh"
PIPELINE = "code/experiments/proofs/corpus_v4_strict_e3_fem_v2_v1.py"
PROTOCOL = "protocols/corpus_v4_strict_e3_fem_v2_v1.json"
LOCK = "protocols/corpus_v4_strict_e3_fem_v2_execution_lock_v1.json"
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def real_file(root: Path, name: str) -> Path:
    path = root / name
    if Path(name).is_absolute() or path.resolve() != path.absolute() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError(f"noncanonical file: {name}")
    return path


def scheduler() -> dict[str, Any]:
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdigit() or not os.environ.get("SLURM_CPUS_PER_TASK", "").isdigit() or int(os.environ["SLURM_CPUS_PER_TASK"]) < 8:
        raise ValueError("diagnostic requires an eight-CPU SLURM allocation")
    text = subprocess.check_output(["scontrol", "show", "job", job, "-o"], text=True).strip()
    fields = dict(item.split("=", 1) for item in text.split() if "=" in item)
    for key, expected in {"JobId": job, "JobState": "RUNNING", "Requeue": "0", "Restarts": "0", "Partition": "nextgen", "Account": "pgs0407", "TimeLimit": "00:30:00", "NumTasks": "1", "MinMemoryNode": "48G"}.items():
        if fields.get(key) != expected:
            raise ValueError(f"scheduler field {key} differs: {fields.get(key)}")
    requested = dict(item.split("=", 1) for item in fields.get("ReqTRES", "").split(",") if "=" in item)
    allocated = dict(item.split("=", 1) for item in fields.get("AllocTRES", "").split(",") if "=" in item)
    if requested.get("cpu") != "8" or requested.get("mem") != "48G" or allocated.get("mem") != "48G" or any(key in fields for key in ("ArrayJobId", "ArrayTaskId")):
        raise ValueError("scheduler resource request differs")
    if allocated.get("cpu") != os.environ["SLURM_CPUS_PER_TASK"] or fields.get("NumCPUs") != allocated["cpu"] or fields.get("CPUs/Task") != allocated["cpu"]:
        raise ValueError("scheduler allocated CPU count differs from environment")
    return {"job_id": job, "scontrol": fields, "raw_scontrol": text}


def bootstrap(args: argparse.Namespace) -> tuple[Any, dict, dict, dict]:
    root = args.frozen_root.resolve()
    own = Path(__file__).resolve().parents[3]
    for directory, head in ((root, FROZEN_COMMIT), (own, args.expected_diagnostic_commit)):
        if git(directory, "rev-parse", "HEAD") != head or git(directory, "status", "--porcelain", "--untracked-files=no") or git(directory, "status", "--porcelain", "--untracked-files=all", "--", "code", "protocols", "requirements-proof.txt"):
            raise ValueError("source checkout is not clean at its pinned commit")
    if sha(real_file(root, PROTOCOL)) != args.expected_protocol_sha256 or sha(real_file(root, LOCK)) != args.expected_lock_sha256:
        raise ValueError("protocol or execution-lock hash mismatch")
    lock = json.loads(real_file(root, LOCK).read_text())
    for name, digest in lock["source_sha256"].items():
        if sha(real_file(root, name)) != digest:
            raise ValueError(f"frozen source hash mismatch: {name}")
    executed = Path(os.environ["PCB_GNN_EXECUTED_BATCH_SCRIPT"])
    if sha(executed) != sha(real_file(own, WRAPPER)):
        raise ValueError("executed batch script differs from diagnostic checkout")
    spec = importlib.util.spec_from_file_location("frozen_e3_pipeline", real_file(root, PIPELINE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if set(lock["source_sha256"]) != set(module.SOURCES):
        raise ValueError("frozen source inventory mismatch")
    protocol = module.load_json(root / PROTOCOL)
    module.validate_protocol_config(protocol)
    if module.runtime() != protocol["runtime"] or lock["runtime"] != protocol["runtime"]:
        raise ValueError("runtime differs from training")
    provenance = {"diagnostic_commit": args.expected_diagnostic_commit,
        "diagnostic_source_sha256": {name: sha(real_file(own, name)) for name in (SCRIPT, WRAPPER)},
        "frozen_commit": FROZEN_COMMIT, "protocol_sha256": args.expected_protocol_sha256,
        "execution_lock_sha256": args.expected_lock_sha256, "source_sha256": lock["source_sha256"],
        "runtime": module.runtime(), "hostname": platform.node(),
        "cpu_model_lines": sorted(set(line for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith(("model name", "vendor_id", "flags")))),
        "torch_cpu_capability": module.torch.backends.cpu.get_cpu_capability(),
        "torch_build_configuration": module.torch.__config__.show()}
    return module, protocol, lock, provenance


def differences(stored: Any, replay: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Report the exact directional numpy gate used by frozen admission."""
    import numpy as np
    if isinstance(stored, dict):
        if not isinstance(replay, dict) or set(stored) != set(replay):
            raise ValueError("metric dictionaries differ")
        return [row for key in sorted(stored) for row in differences(stored[key], replay[key], f"{prefix}.{key}".lstrip("."))]
    if isinstance(stored, list):
        if not isinstance(replay, list) or len(stored) != len(replay):
            raise ValueError("metric lists differ")
        return [row for i, value in enumerate(stored) for row in differences(value, replay[i], f"{prefix}[{i}]")]
    if isinstance(stored, (int, float)) and not isinstance(stored, bool):
        if not isinstance(replay, (int, float)) or isinstance(replay, bool) or not np.isfinite(stored) or not np.isfinite(replay):
            raise ValueError("nonfinite or nonnumeric metric")
        delta = abs(stored - replay)
        return [{"metric": prefix, "stored": stored, "replay": replay, "absolute_difference": delta,
            "relative_difference_to_replay": delta / abs(replay) if replay else (0.0 if delta == 0 else None),
            "original_gate_limit": 1e-10 + 1e-8 * abs(replay),
            "original_gate_passed": bool(np.isclose(stored, replay, rtol=1e-8, atol=1e-10))}]
    if stored != replay:
        raise ValueError("nonnumeric metric differs")
    return [{"metric": prefix, "stored": stored, "replay": replay, "equal": True}]


def worker(args: argparse.Namespace, module: Any, protocol: dict, lock: dict, provenance: dict) -> dict:
    module.configure_torch(args.threads)
    root = args.frozen_root.resolve()
    manifest_name = f"{module.PLAN}/task_manifest.jsonl"
    module.authenticate({"path": manifest_name, "sha256": lock["inputs"][manifest_name]})
    rows = module.load_jsonl(root / manifest_name)
    row = rows[0]
    if any(row[key] != value for key, value in module.canonical_task_row(0).items()):
        raise ValueError("task zero identity differs")
    name = f"{module.PLAN}/{row['training_dataset']['path']}"
    if lock["inputs"][name] != row["training_dataset"]["sha256"]:
        raise ValueError("split table hash differs")
    dataset = module.load_training_split_dataset_v3(module.authenticate({"path": name, "sha256": lock["inputs"][name]}), expected_sha256=lock["inputs"][name], task_row=row)
    ids = list(dataset.validation_layout_ids)
    samples = module._graph_samples(SimpleNamespace(samples=tuple(record for record in dataset.samples if record.layout_id in set(ids))))
    receipt_path = real_file(root, f"{module.BASE}/jobs/job_7318063/task_00/result.json")
    if sha(receipt_path) != args.expected_task_receipt_sha256:
        raise ValueError("task receipt differs from external pin")
    result = module.load_json(receipt_path)
    binding = SimpleNamespace(expected_protocol_sha256=args.expected_protocol_sha256, expected_execution_lock_sha256=args.expected_lock_sha256, expected_source_git_head=FROZEN_COMMIT)
    if result["bindings"] != module.bindings(binding) or result["task"] != module.canonical_task_row(0) or result["source_sha256"] != lock["source_sha256"] or result["runtime"] != lock["runtime"]:
        raise ValueError("training receipt identity differs")
    module.validate_scheduler_receipt(result["scheduler"], stage="training", task_id=0)
    arm_results = {}
    for arm in module.ARMS:
        record = result["arms"][arm]
        for relative, digest in record["files"].items():
            if sha(real_file(root, (receipt_path.parent.relative_to(root) / relative).as_posix())) != digest:
                raise ValueError("checkpoint artifact hash differs")
        arrays, model, normalizer = module.load_arm(binding, protocol, receipt_path, result, arm)
        work = {index: normalizer.transform(samples[index]) for index in ids}
        prediction = module._predict(model, normalizer, work, ids, protocol["optimization"]["batch_size"])
        reference = module.np.stack([samples[index]["reference_r3"] for index in ids])
        families = [samples[index]["family_id"] for index in ids]
        metrics = {target: module.metric_set(prediction[:, index], reference[:, index], families) for index, target in enumerate(module.TARGETS)}
        arm_results[arm] = {"metrics": metrics, "comparison_to_training": differences(record["validation_diagnostic_only"], metrics),
            "prediction_sha256": hashlib.sha256(prediction.tobytes()).hexdigest(),
            "predictions": prediction.tolist(), "reference": reference.tolist(),
            "prediction_dtype": str(prediction.dtype), "target_order": list(module.TARGETS),
            "checkpoint_files": record["files"]}
        del arrays, model, normalizer
    return {"threads": args.threads, "repeat": args.repeat, "provenance": provenance,
        "training_scheduler": result["scheduler"], "task_receipt_sha256": sha(receipt_path),
        "training_table": {"path": name, "sha256": lock["inputs"][name]},
        "validation_layout_ids": ids, "arms": arm_results,
        "heldout_bytes_opened": False, "model_fitting_started": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--expected-diagnostic-commit", required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--expected-task-receipt-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, choices=(2, 8))
    parser.add_argument("--repeat", type=int, choices=(1, 2))
    args = parser.parse_args()
    allocation = scheduler()
    module, protocol, lock, provenance = bootstrap(args)
    if args.threads is not None:
        print(json.dumps(worker(args, module, protocol, lock, provenance), allow_nan=False))
        return
    own = Path(__file__).resolve().parents[3]
    output = args.out.absolute()
    if output.exists() or output.resolve() != output or not output.is_relative_to(own / module.BASE / "diagnostics"):
        raise ValueError("diagnostic output must be a new canonical file under diagnostic checkout results")
    runs = []
    for threads in (2, 8):
        for repeat in (1, 2):
            env = dict(os.environ, **{name: str(threads) for name in THREAD_ENV})
            command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--threads", str(threads), "--repeat", str(repeat)]
            result = subprocess.run(command, env=env, check=False, text=True, capture_output=True)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            result.check_returncode()
            runs.append(json.loads(result.stdout))
    cross = [{"first_run": left, "second_run": right, "arm": arm,
        "metrics": differences(runs[left]["arms"][arm]["metrics"], runs[right]["arms"][arm]["metrics"]),
        "predictions": differences(runs[left]["arms"][arm]["predictions"], runs[right]["arms"][arm]["predictions"], "predictions"),
        "predictions_byte_identical": runs[left]["arms"][arm]["prediction_sha256"] == runs[right]["arms"][arm]["prediction_sha256"]}
        for left, right in ((0, 1), (2, 3), (0, 2), (1, 3)) for arm in module.ARMS]
    module.atomic_write_json(output, {"schema": "pcb-gnn.strict-e3-validation-thread-diagnostic.v1",
        "scheduler": allocation, "provenance": provenance, "runs": runs, "pairwise_replay": cross,
        "original_tolerance": {"rtol": 1e-8, "atol": 1e-10},
        "admission_granted": False, "model_fitting_started": False, "heldout_bytes_opened": False})
    print(str(output))


if __name__ == "__main__":
    main()
