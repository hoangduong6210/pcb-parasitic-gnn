#!/usr/bin/env python3
"""Eight-thread recovery using immutable trained artifacts and scientific code.

All numerical work requires SLURM. Admission replays validation only. Held-out
inference requires an externally pinned, completed recovery admission.
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
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = "results/corpus_v4/strict_e3_fem_v2"
RECOVERY = f"{BASE}/recovery/v1"
SCRIPT = "code/experiments/proofs/recover_strict_e3_fem_v2_v1.py"
WRAPPER = "code/jobs/submit_recover_strict_e3_fem_v2_v1.sh"
PROTOCOL = "protocols/corpus_v4_strict_e3_fem_v2_recovery_v1.json"
FROZEN_PROTOCOL = "protocols/corpus_v4_strict_e3_fem_v2_v1.json"
LOCK = "protocols/corpus_v4_strict_e3_fem_v2_execution_lock_v1.json"
PIPELINE = "code/experiments/proofs/corpus_v4_strict_e3_fem_v2_v1.py"
FROZEN_COMMIT = "efeb123c9975ae481d10cd7c0af899406c46e787"
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


def validate_recovery_protocol(value: dict) -> None:
    expected = {"schema", "frozen_commit", "frozen_protocol_sha256", "frozen_lock_sha256", "training_array", "task_receipt_sha256", "scientific_threads", "resources", "diagnostic", "change", "model_fitting_permitted", "claim_eligible"}
    if set(value) != expected or value["schema"] != "pcb-gnn.strict-e3-recovery-protocol.v1" or value["frozen_commit"] != FROZEN_COMMIT or value["training_array"] != "7318063" or value["scientific_threads"] != 8 or value["model_fitting_permitted"] is not False or value["claim_eligible"] is not False:
        raise ValueError("recovery protocol identity differs")
    if value["resources"] != {"cpus_per_task": 8, "mem": "48G", "time": "00:30:00", "account": "pgs0407", "partition": "nextgen", "requeue": False}:
        raise ValueError("recovery resource profile differs")
    if value["frozen_protocol_sha256"] != "9e6f76f2d2549e660ac7980b7e2a84418489a88598312ec3e735a757490c00fc" or value["frozen_lock_sha256"] != "f8c776604220cc013243eeca9dc6fe16c0ec5455d86fcbb105f9eb19df839c20":
        raise ValueError("immutable protocol or lock pin differs")
    if value["diagnostic"] != {"path": f"{BASE}/diagnostics/job_7326041/result.json", "sha256": "1c674b31020e55dcce74ca9b17c97fa55accd1907cc1e3cbbb26baedb218d859"}:
        raise ValueError("diagnostic evidence pin differs")
    if set(value["task_receipt_sha256"]) != {str(i) for i in range(25)}:
        raise ValueError("receipt pins must cover all 25 tasks")
    for digest in [value["frozen_protocol_sha256"], value["frozen_lock_sha256"], value["diagnostic"]["sha256"], *value["task_receipt_sha256"].values()]:
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid SHA-256 pin")


def scheduler() -> dict:
    job = os.environ.get("SLURM_JOB_ID", "")
    if not job.isdigit() or any(os.environ.get(name) != "8" for name in THREAD_ENV):
        raise ValueError("recovery requires SLURM and eight numerical threads")
    raw = subprocess.check_output(["scontrol", "show", "job", job, "-o"], text=True).strip()
    fields = dict(item.split("=", 1) for item in raw.split() if "=" in item)
    for key, expected in {"JobId": job, "JobState": "RUNNING", "Requeue": "0", "Restarts": "0", "Partition": "nextgen", "Account": "pgs0407", "TimeLimit": "00:30:00", "NumTasks": "1", "MinMemoryNode": "48G"}.items():
        if fields.get(key) != expected:
            raise ValueError(f"scheduler field {key} differs")
    requested = dict(item.split("=", 1) for item in fields.get("ReqTRES", "").split(",") if "=" in item)
    allocated = dict(item.split("=", 1) for item in fields.get("AllocTRES", "").split(",") if "=" in item)
    if requested.get("cpu") != "8" or requested.get("mem") != "48G" or allocated.get("mem") != "48G" or any(key in fields for key in ("ArrayJobId", "ArrayTaskId")):
        raise ValueError("scheduler resource request differs")
    if not allocated.get("cpu", "").isdigit() or int(allocated["cpu"]) < 8 or allocated["cpu"] != os.environ.get("SLURM_CPUS_PER_TASK") or fields.get("NumCPUs") != allocated["cpu"] or fields.get("CPUs/Task") != allocated["cpu"]:
        raise ValueError("allocated CPU count differs")
    return {"job_id": job, "scontrol": fields, "raw_scontrol": raw}


def terminal(receipt: dict) -> dict:
    job = receipt["job_id"]
    stored = receipt["scontrol"]
    for key, expected in {"JobId": job, "JobState": "RUNNING", "Requeue": "0", "Restarts": "0", "Partition": "nextgen", "Account": "pgs0407", "TimeLimit": "00:30:00", "NumTasks": "1", "MinMemoryNode": "48G"}.items():
        if stored.get(key) != expected:
            raise ValueError("stored recovery allocation differs")
    requested = dict(item.split("=", 1) for item in stored.get("ReqTRES", "").split(",") if "=" in item)
    allocated = dict(item.split("=", 1) for item in stored.get("AllocTRES", "").split(",") if "=" in item)
    if requested.get("cpu") != "8" or requested.get("mem") != "48G" or allocated.get("mem") != "48G" or allocated.get("cpu") != stored.get("NumCPUs") or not stored.get("NumCPUs", "").isdigit() or int(stored["NumCPUs"]) < 8 or stored.get("CPUs/Task") != stored["NumCPUs"] or any(key in stored for key in ("ArrayJobId", "ArrayTaskId")):
        raise ValueError("stored recovery resources differ")
    fields = ("JobIDRaw", "State", "ExitCode", "Restarts", "Partition", "Timelimit", "Account", "AllocCPUS", "NodeList")
    raw = subprocess.check_output(["sacct", "-X", "-n", "-P", "-j", job, "--format=" + ",".join(fields)], text=True)
    rows = [dict(zip(fields, line.split("|"))) for line in raw.splitlines() if len(line.split("|")) == len(fields)]
    rows = [row for row in rows if row["JobIDRaw"] == job]
    if len(rows) != 1:
        raise ValueError("recovery terminal accounting unavailable or ambiguous")
    row = rows[0]
    expected = {"State": "COMPLETED", "ExitCode": "0:0", "Restarts": "0", "Partition": "nextgen", "Timelimit": "00:30:00", "Account": "pgs0407", "AllocCPUS": receipt["scontrol"]["NumCPUs"], "NodeList": receipt["scontrol"]["NodeList"]}
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("recovery job did not complete under the pinned profile")
    return row


def bootstrap(args: argparse.Namespace) -> tuple:
    root = args.frozen_root.resolve()
    if git(ROOT, "rev-parse", "HEAD") != args.expected_recovery_commit:
        raise ValueError("recovery checkout differs from external commit pin")
    for directory in (ROOT, root):
        if git(directory, "status", "--porcelain", "--untracked-files=no") or git(directory, "status", "--porcelain", "--untracked-files=all", "--", "code", "protocols", "requirements-proof.txt"):
            raise ValueError("source checkout is dirty")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD"], check=True)
    if sha(real_file(ROOT, PROTOCOL)) != args.expected_recovery_protocol_sha256:
        raise ValueError("recovery protocol differs from external pin")
    recovery = json.loads(real_file(ROOT, PROTOCOL).read_text())
    validate_recovery_protocol(recovery)
    for name, digest in ((FROZEN_PROTOCOL, recovery["frozen_protocol_sha256"]), (LOCK, recovery["frozen_lock_sha256"])):
        if sha(real_file(root, name)) != digest:
            raise ValueError("frozen protocol or lock mismatch")
    if sha(real_file(ROOT, recovery["diagnostic"]["path"])) != recovery["diagnostic"]["sha256"]:
        raise ValueError("diagnostic evidence differs")
    if sha(Path(os.environ["PCB_GNN_EXECUTED_BATCH_SCRIPT"])) != sha(real_file(ROOT, WRAPPER)):
        raise ValueError("executed recovery batch script differs")
    lock = json.loads(real_file(root, LOCK).read_text())
    for name, digest in lock["source_sha256"].items():
        if sha(real_file(root, name)) != digest:
            raise ValueError(f"immutable scientific source differs: {name}")
    spec = importlib.util.spec_from_file_location("immutable_e3_recovery_pipeline", real_file(root, PIPELINE))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binding = SimpleNamespace(protocol=root / FROZEN_PROTOCOL, execution_lock=root / LOCK,
        expected_protocol_sha256=recovery["frozen_protocol_sha256"], expected_execution_lock_sha256=recovery["frozen_lock_sha256"], expected_source_git_head=FROZEN_COMMIT, stage="verify")
    protocol, lock, rows = module.context(binding)
    module.configure_torch(8)
    provenance = {"recovery_commit": args.expected_recovery_commit, "recovery_protocol_sha256": args.expected_recovery_protocol_sha256,
        "recovery_source_sha256": {name: sha(real_file(ROOT, name)) for name in (SCRIPT, WRAPPER, PROTOCOL)},
        "scientific_checkout_commit": git(root, "rev-parse", "HEAD"), "training_bindings": module.bindings(binding),
        "scientific_source_sha256": lock["source_sha256"], "runtime": module.runtime(), "scientific_threads": 8,
        "hostname": platform.node(), "torch_cpu_capability": module.torch.backends.cpu.get_cpu_capability(),
        "torch_build_configuration": module.torch.__config__.show(),
        "cpu_model_lines": sorted(set(line for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith(("model name", "vendor_id", "flags"))))}
    return module, binding, protocol, lock, rows, recovery, provenance


def check_all(module: Any, binding: Any, protocol: dict, lock: dict, rows: list, recovery: dict) -> tuple[list, list]:
    root = module.ROOT / BASE / "jobs" / f"job_{recovery['training_array']}"
    if not root.is_dir() or root.is_symlink() or sorted(p.name for p in root.iterdir()) != [f"task_{i:02d}" for i in range(25)]:
        raise ValueError("training array must contain exactly 25 tasks")
    accepted, records = [], []
    for task_id in range(25):
        relative = f"{BASE}/jobs/job_{recovery['training_array']}/task_{task_id:02d}/result.json"
        path = real_file(module.ROOT, relative)
        if sha(path) != recovery["task_receipt_sha256"][str(task_id)]:
            raise ValueError(f"training receipt external pin differs: {task_id}")
        result = module.check_task(binding, path, task_id, protocol, lock, rows)
        if str(result["scheduler"]["array_job_id"]) != recovery["training_array"]:
            raise ValueError("training scheduler array differs")
        completion = module.terminal(result["scheduler"], "training")
        accepted.append((path, result))
        records.append({"task_id": task_id, "result": {"path": relative, "sha256": sha(path)}, "terminal": completion})
        print(f"validated task {task_id:02d}: three checkpoints", flush=True)
    if len({result["scheduler"]["job_id"] for _, result in accepted}) != 25:
        raise ValueError("training jobs are not unique")
    return accepted, records


def output_folder(stage: str, allocation: dict) -> Path:
    folder = ROOT / RECOVERY / stage / f"job_{allocation['job_id']}"
    if folder.resolve() != folder.absolute() or folder.exists():
        raise ValueError("recovery output must be canonical and new")
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def read_pinned(path: Path, digest: str, stage: str, filename: str) -> dict:
    path = path.absolute()
    if path.resolve() != path or path.name != filename or path.parent.parent != ROOT / RECOVERY / stage or sha(path) != digest:
        raise ValueError("recovery artifact path or external hash differs")
    value = json.loads(path.read_text())
    if path.parent.name != f"job_{value['scheduler']['job_id']}":
        raise ValueError("recovery artifact scheduler path differs")
    return value


def validate_provenance(stored: dict, current: dict) -> None:
    for key in ("recovery_protocol_sha256", "recovery_source_sha256", "training_bindings", "scientific_source_sha256", "runtime", "scientific_threads"):
        if stored.get(key) != current[key]:
            raise ValueError(f"recovery provenance differs: {key}")
    commit = stored.get("recovery_commit", "")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("stored recovery commit is not canonical")
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, current["recovery_commit"]], check=True)
    for name, digest in current["recovery_source_sha256"].items():
        blob = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{name}"])
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError("stored recovery source commit differs from executed bytes")


def validate_admission(args: Any, provenance: dict) -> dict:
    value = read_pinned(args.accepted_set, args.expected_accepted_set_sha256, "admission", "accepted_artifact_set.json")
    if set(value) != {"schema", "provenance", "scheduler", "accepted", "task_count", "checkpoint_count", "heldout_bytes_opened", "heldout_inference_permitted", "model_fitting_started", "claim_eligible"} or value["schema"] != "pcb-gnn.strict-e3-recovery-admission.v1" or value["task_count"] != 25 or value["checkpoint_count"] != 75 or value["heldout_bytes_opened"] is not False or value["heldout_inference_permitted"] is not True or value["model_fitting_started"] is not False or value["claim_eligible"] is not False:
        raise ValueError("recovery admission decision differs")
    validate_provenance(value["provenance"], provenance)
    terminal(value["scheduler"])
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("admit", "finalize", "verify"), required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--expected-recovery-commit", required=True)
    parser.add_argument("--expected-recovery-protocol-sha256", required=True)
    parser.add_argument("--accepted-set", type=Path)
    parser.add_argument("--expected-accepted-set-sha256")
    parser.add_argument("--analysis-manifest", type=Path)
    parser.add_argument("--expected-analysis-manifest-sha256")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    if args.stage != "admit" and (args.accepted_set is None or args.expected_accepted_set_sha256 is None):
        parser.error("finalize and verify require an externally pinned accepted set")
    if args.stage == "verify" and (args.analysis_manifest is None or args.expected_analysis_manifest_sha256 is None):
        parser.error("verify requires an externally pinned analysis manifest")
    if (args.check and args.archive is None) or (args.require_git_tracked and not args.check):
        parser.error("archive checks require an archive; tracked replay also requires --check")
    if args.stage != "verify" and (args.check or args.require_git_tracked or args.archive is not None):
        parser.error("archive options are exclusive to verify")
    allocation = scheduler()
    module, binding, protocol, lock, rows, recovery, provenance = bootstrap(args)
    admission = None if args.stage == "admit" else validate_admission(args, provenance)
    accepted, records = check_all(module, binding, protocol, lock, rows, recovery)
    if args.stage == "admit":
        folder = output_folder("admission", allocation)
        module.atomic_write_json(folder / "accepted_artifact_set.json", {"schema": "pcb-gnn.strict-e3-recovery-admission.v1",
            "provenance": provenance, "scheduler": allocation, "accepted": records, "task_count": 25, "checkpoint_count": 75,
            "heldout_bytes_opened": False, "heldout_inference_permitted": True, "model_fitting_started": False, "claim_eligible": False})
        print(folder)
        return
    if admission["accepted"] != records:
        raise ValueError("admitted training evidence changed")
    # Opening the full input closure is permitted only after admission replay.
    for name, digest in lock["inputs"].items():
        if sha(real_file(module.ROOT, name)) != digest:
            raise ValueError(f"locked upstream evidence differs: {name}")
    predictions, metrics, contrasts = module.evaluate(binding, protocol, lock, rows, accepted)
    results = module.summarize(metrics, contrasts)
    results["trained_symmetry"] = module.summarize_trained_symmetry(accepted)
    if args.stage == "finalize":
        folder = output_folder("final", allocation)
        module.atomic_write_jsonl(folder / "predictions.jsonl", predictions)
        module.atomic_write_json(folder / "metrics.json", {"arm_target_cells": metrics, "paired_contrasts": contrasts})
        module.atomic_write_json(folder / "summary.json", {"schema": "pcb-gnn.strict-e3-recovery-analysis.v1", "provenance": provenance,
            "scheduler": allocation, "accepted_set_sha256": args.expected_accepted_set_sha256, "results": results, "claim_eligible": False})
        module.atomic_write_json(folder / "ANALYSIS_MANIFEST.json", {"schema": "pcb-gnn.strict-e3-recovery-analysis-manifest.v1", "provenance": provenance,
            "scheduler": allocation, "accepted_set_sha256": args.expected_accepted_set_sha256,
            "files": {name: sha(folder / name) for name in ("predictions.jsonl", "metrics.json", "summary.json")}})
        print(folder)
        return
    manifest = read_pinned(args.analysis_manifest, args.expected_analysis_manifest_sha256, "final", "ANALYSIS_MANIFEST.json")
    validate_provenance(manifest["provenance"], provenance)
    if set(manifest) != {"schema", "provenance", "scheduler", "accepted_set_sha256", "files"} or manifest["schema"] != "pcb-gnn.strict-e3-recovery-analysis-manifest.v1" or manifest["accepted_set_sha256"] != args.expected_accepted_set_sha256 or set(manifest["files"]) != {"predictions.jsonl", "metrics.json", "summary.json"}:
        raise ValueError("analysis manifest schema differs")
    folder = args.analysis_manifest.parent
    if {p.name for p in folder.iterdir()} != {"ANALYSIS_MANIFEST.json", *manifest["files"]}:
        raise ValueError("analysis inventory differs")
    for name, digest in manifest["files"].items():
        if sha(real_file(folder, name)) != digest:
            raise ValueError("analysis artifact hash differs")
    summary = module.load_json(folder / "summary.json")
    expected_summary = {"schema": "pcb-gnn.strict-e3-recovery-analysis.v1", "provenance": manifest["provenance"], "scheduler": manifest["scheduler"], "accepted_set_sha256": args.expected_accepted_set_sha256, "results": results, "claim_eligible": False}
    if summary != expected_summary or module.load_jsonl(folder / "predictions.jsonl") != predictions or module.load_json(folder / "metrics.json") != {"arm_target_cells": metrics, "paired_contrasts": contrasts}:
        raise ValueError("independent numerical reconstruction differs")
    completion = terminal(manifest["scheduler"])
    names = set(lock["source_sha256"]) | set(lock["inputs"]) | {LOCK, SCRIPT, WRAPPER, PROTOCOL, recovery["diagnostic"]["path"]}
    names.update(p.relative_to(module.ROOT).as_posix() for path, _ in accepted for p in path.parent.rglob("*") if p.is_file())
    names.update(p.relative_to(ROOT).as_posix() for p in folder.iterdir())
    names.add(args.accepted_set.relative_to(ROOT).as_posix())
    closure = {name: sha(real_file(module.ROOT if name not in {SCRIPT, WRAPPER, PROTOCOL, recovery['diagnostic']['path']} and not name.startswith(RECOVERY) else ROOT, name)) for name in sorted(names)}
    archive = {"schema": "pcb-gnn.strict-e3-recovery-archive.v1", "recovery_protocol_sha256": args.expected_recovery_protocol_sha256,
        "accepted_set_sha256": args.expected_accepted_set_sha256, "analysis_manifest_sha256": args.expected_analysis_manifest_sha256,
        "admission_terminal": terminal(admission["scheduler"]), "finalizer_terminal": completion, "files": closure,
        "counts": results["counts"], "numerical_reconstruction_passed": True, "claim_eligible": False}
    if args.check:
        if args.archive is None or args.archive.resolve() != args.archive.absolute() or args.archive.parent.parent != ROOT / RECOVERY / "verify" or args.archive.name != "ARCHIVE_MANIFEST.json" or module.load_json(args.archive) != archive:
            raise ValueError("archive replay differs")
    if args.require_git_tracked:
        if not args.check or module.ROOT != ROOT:
            raise ValueError("tracked replay requires one clean evidence checkout and existing archive")
        previous_path = real_file(ROOT, (args.archive.parent / "result.json").relative_to(ROOT).as_posix())
        previous = module.load_json(previous_path)
        if set(previous) != {"schema", "provenance", "scheduler", "analysis_manifest_sha256", "archive_sha256", "numerical_reconstruction_passed", "git_tracked_closure_passed", "claim_eligible"} or previous["schema"] != "pcb-gnn.strict-e3-recovery-verification.v1" or previous["archive_sha256"] != sha(args.archive) or previous["analysis_manifest_sha256"] != args.expected_analysis_manifest_sha256 or previous["numerical_reconstruction_passed"] is not True or previous["claim_eligible"] is not False or args.archive.parent.name != f"job_{previous['scheduler']['job_id']}":
            raise ValueError("prior archive replay receipt differs")
        validate_provenance(previous["provenance"], provenance)
        terminal(previous["scheduler"])
        git(ROOT, "ls-files", "--error-unmatch", "--", *sorted(names | {args.archive.relative_to(ROOT).as_posix(), previous_path.relative_to(ROOT).as_posix()}))
    out = output_folder("verify", allocation)
    if not args.check:
        module.atomic_write_json(out / "ARCHIVE_MANIFEST.json", archive)
    module.atomic_write_json(out / "result.json", {"schema": "pcb-gnn.strict-e3-recovery-verification.v1", "provenance": provenance,
        "scheduler": allocation, "analysis_manifest_sha256": args.expected_analysis_manifest_sha256,
        "archive_sha256": sha(args.archive if args.check else out / "ARCHIVE_MANIFEST.json"),
        "numerical_reconstruction_passed": True, "git_tracked_closure_passed": args.require_git_tracked, "claim_eligible": False})
    print(out)


if __name__ == "__main__":
    main()
