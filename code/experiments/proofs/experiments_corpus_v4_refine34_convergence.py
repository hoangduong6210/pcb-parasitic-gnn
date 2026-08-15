#!/usr/bin/env python3
"""Frozen nine-layout refine-3/refine-4 FEM convergence experiment."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from experiments_corpus_v4_refine4_feasibility import (  # noqa: E402
    evaluate_gates,
    solve_bounded,
)
from v3_dataset import load_final_corpus  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-refine34-convergence-task.v1"
PRIOR_FINAL_SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-final.v2"
PRIOR_ARRAY_JOB_ID = "6833715"
PRIOR_FINAL_SHA256 = "d38b0f1f3b22d3dd2580a334f34e001aedae72707e1b298f1600d8cb68d4785b"
PRIOR_TASK_SHA256 = {
    "task_00.json": "12f68203ea7dff41cdd35279e0fe8006aba91d86f17f144947b335e28c6a3275",
    "task_01.json": "bee1419fbab9899157e6c1468de41decf4f35129e5edd822668ca3ecf5e8cba9",
    "task_02.json": "dd230bf13bd57887c5bc9112e876e4622ad95bdd6aeede738b1a4f37a5778a8a",
    "task_03.json": "e82a1f0a7df7b4728cec9dbe7e3d06003779f32969db7fa87fcfdb64cdee0cfa",
    "task_04.json": "a4f31f82feec9c82f30f57060a984919a196d71580f8ae476903d85c94636fe2",
    "task_05.json": "a51a1821114bdf94f3ec53c603915b67511700c3441460a19615adc53802f254",
    "task_06.json": "5f345a007dad2f73060180791440c8628a5d8a8f8f12bf1fd7e220eb44163e83",
    "task_07.json": "942702c37874a62f3ad250d8b7103c9e32489404e559a80449c44ef6135e9de5",
    "task_08.json": "61d0653a0409bc31051528e78cb8d6bdaffedd714a5f981956881e3c9a040efd",
}
SETTINGS = ((3, 12.0), (3, 16.0), (4, 16.0))
EXPECTED_CORPUS_SHA256 = {
    "layouts.jsonl": "17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b",
    "labels.jsonl": "48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327",
}
LAYOUTS = (
    (1055, "b1d837fc6357a278ef823510dd7c5e162fa5b686c8e4827ec383d2d14fe2c590"),
    (407, "5cc53be678ba4bb99fb0ea35a8cf5ef32c94bb5a44b4210a595f7ed46e0a3d4f"),
    (1351, "4222c3ba94b2ebd609325a5cbbaecf72ed6857a9053b84b5b35cb7d77396114d"),
    (149, "0e2aef8a6ec688d3b271569091cd9a3d8ad786a1bc5f54bb3456ec292eda96b4"),
    (275, "4c4fd2bb497d7ff0dd0230c8ba2de38edc1a5cf6bdeebb66d5f5362b60400eaa"),
    (897, "b3c7d59b256d0c8be29350058f32a6f6fb3f1904300e6329bd5b6e8989d9c8b3"),
    (2, "10814d8ca1c0e84e6991ec01a56d862a9068ef2e3f4b1484c25bddd26fe81ad0"),
    (173, "46c646aa28dc248a0e0d1c2017ba88d4f99c4a574905622998611f41613364f5"),
    (1400, "c4e6703313879d673d12f5eefb0c2a0fbc0a5b556d05300cfcfa209dc86f311f"),
)
FEASIBILITY = {
    149: {
        "sha256": "6115d234071dfd8884f5d88c575c4baf695fc911abb9980f8ba5f965360fd32b",
        "geometry_sha256": LAYOUTS[3][1],
        "slurm_job_id": "6834616",
    },
    407: {
        "sha256": "397074e8690bbff4b4b29ef7f3567b90493f45910dc438dee1c1e34290ec80e3",
        "geometry_sha256": LAYOUTS[1][1],
        "slurm_job_id": "6837051",
    },
}
FEASIBILITY_COMPARABLE_SOURCES = (
    "requirements-proof.txt",
    "code/experiments/proofs/experiments_corpus_v4_convergence_preflight.py",
    "code/experiments/proofs/experiments_corpus_v4_refine4_feasibility.py",
    "code/data/v3_dataset.py",
    "code/core/geometry_contract.py",
    "code/solvers/fem_capacitance_3d.py",
    "code/solvers/fem_cps_diagnostic_worker.py",
    "code/solvers/fem_cps_bounded_worker.py",
)
COMPUTATIONAL_SOURCES = (
    *FEASIBILITY_COMPARABLE_SOURCES,
    "code/core/runtime_paths.py",
    "code/core/planar_to_graph.py",
    "code/core/pcb_graph.py",
    "code/core/trace_peec.py",
)
SOURCE_NAMES = (
    "code/experiments/proofs/experiments_corpus_v4_refine34_convergence.py",
    *COMPUTATIONAL_SOURCES,
    "code/jobs/submit_corpus_v4_refine34_convergence.sh",
    "code/experiments/proofs/finalize_corpus_v4_refine34_convergence.py",
    "code/jobs/submit_finalize_corpus_v4_refine34_convergence.sh",
)
THREAD_NAMES = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "PCB_GNN_GMSH_THREADS",
)
FEASIBILITY_THREAD_NAMES = tuple(
    name for name in THREAD_NAMES if name != "BLIS_NUM_THREADS"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def runtime_environment() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "scikit-fem", "gmsh", "meshio", "pyamg")
        },
        "thread_environment": {name: os.environ.get(name) for name in THREAD_NAMES},
    }


def validate_prior_and_feasibility(
    prior_final_path: Path,
    feasibility_paths: dict[int, Path],
    current_computational_hashes: dict[str, str],
    environment: dict[str, Any],
) -> dict[str, Any]:
    """Bind the run to the rejected r2/r3 gate and both passing r4 probes."""
    if file_sha256(prior_final_path) != PRIOR_FINAL_SHA256:
        raise ValueError("prior convergence final artifact hash mismatch")
    prior_final = json.loads(prior_final_path.read_text())
    if (
        prior_final.get("schema") != PRIOR_FINAL_SCHEMA
        or prior_final.get("gate_pass") is not False
        or str(prior_final.get("provenance", {}).get("source_array_job_id"))
        != PRIOR_ARRAY_JOB_ID
    ):
        raise ValueError("prior convergence artifact is not canonical")

    task_hashes = prior_final["provenance"]["task_artifacts_sha256"]
    if task_hashes != PRIOR_TASK_SHA256:
        raise ValueError("prior convergence task hash map mismatch")
    prior_task_dir = ROOT / "results/corpus_v4/convergence_preflight/jobs" / (
        f"job_{PRIOR_ARRAY_JOB_ID}"
    )
    for task_id, (layout_id, geometry_sha256) in enumerate(LAYOUTS):
        name = f"task_{task_id:02d}.json"
        path = prior_task_dir / name
        if file_sha256(path) != task_hashes.get(name):
            raise ValueError(f"prior task artifact hash mismatch: {name}")
        task = json.loads(path.read_text())
        if (
            not task.get("task_pass")
            or int(task["selection"]["layout_id"]) != layout_id
            or task["selection"]["geometry_sha256"] != geometry_sha256
        ):
            raise ValueError(f"frozen layout mismatch: {name}")

    feasibility_evidence: dict[str, Any] = {}
    common_environment = None
    for layout_id in (149, 407):
        path = feasibility_paths[layout_id]
        expected = FEASIBILITY[layout_id]
        artifact_sha = file_sha256(path)
        if artifact_sha != expected["sha256"]:
            raise ValueError(f"layout-{layout_id} feasibility hash mismatch")
        payload = json.loads(path.read_text())
        provenance = payload.get("provenance", {})
        recomputed_gate = evaluate_gates(payload.get("refine4_pad16", {}))
        if (
            not payload.get("feasibility_pass")
            or payload.get("resource_gate") != recomputed_gate
            or not recomputed_gate["pass"]
            or payload.get("scientific_acceptance_evaluated") is not False
            or int(payload.get("selection", {}).get("layout_id", -1)) != layout_id
            or payload.get("selection", {}).get("geometry_sha256")
            != expected["geometry_sha256"]
            or not provenance.get("source_stable")
            or provenance.get("git_dirty_paths")
            or provenance.get("final_git_dirty_paths")
            or provenance.get("final_untracked_code")
        ):
            raise ValueError(f"layout-{layout_id} feasibility did not pass")
        previous_hashes = provenance.get("file_sha256", {})
        for name, current_hash in current_computational_hashes.items():
            if previous_hashes.get(name) != current_hash:
                raise ValueError(f"computational source changed since feasibility: {name}")
        observed_environment = {
            "python": provenance.get("python"),
            "package_versions": provenance.get("package_versions"),
            "thread_environment": provenance.get("thread_environment"),
        }
        comparable_current_environment = {
            "python": environment["python"],
            "package_versions": environment["package_versions"],
            "thread_environment": {
                name: environment["thread_environment"][name]
                for name in FEASIBILITY_THREAD_NAMES
            },
        }
        if observed_environment != comparable_current_environment:
            raise ValueError("runtime environment differs from feasibility probes")
        if common_environment is not None and observed_environment != common_environment:
            raise ValueError("feasibility probes used mixed environments")
        common_environment = observed_environment
        feasibility_evidence[str(layout_id)] = {
            "path": str(path),
            "sha256": artifact_sha,
            "slurm_job_id": provenance.get("slurm_job_id"),
        }
        if provenance.get("slurm_job_id") != expected["slurm_job_id"]:
            raise ValueError(f"layout-{layout_id} feasibility job mismatch")
    stage_b_binding = json.loads(feasibility_paths[407].read_text()).get(
        "provenance", {}
    ).get("stage_a_layout_149", {})
    if stage_b_binding.get("sha256") != FEASIBILITY[149]["sha256"]:
        raise ValueError("stage-B artifact is not bound to canonical stage A")
    return {
        "prior_final": {
            "path": str(prior_final_path),
            "sha256": PRIOR_FINAL_SHA256,
            "source_array_job_id": PRIOR_ARRAY_JOB_ID,
            "task_artifacts_sha256": task_hashes,
        },
        "refine4_feasibility": feasibility_evidence,
    }


def checkpoint_setting(
    path: Path, payload: dict[str, Any], setting: dict[str, Any]
) -> None:
    setting["resource_gate"] = evaluate_gates(setting)
    payload["settings"].append(setting)
    atomic_write(path, payload)
    if not setting_result_valid(setting) or not setting["resource_gate"]["pass"]:
        raise RuntimeError("FEM setting failed its numerical/resource gate")


def setting_result_valid(setting: dict[str, Any]) -> bool:
    """Require the exact solver contract and matching 256-bit system fingerprints."""
    input_hash = setting.get("input_system_sha256")
    system_hash = setting.get("system_sha256")
    valid_hash = lambda value: (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
    return bool(
        setting.get("success")
        and setting.get("linear_solver") == "pyamg_smoothed_aggregation_cg"
        and int(setting.get("maxiter", -1)) == 500
        and float(setting.get("rtol", float("inf"))) == 1e-10
        and int(setting.get("solver_info", -1)) == 0
        and not setting.get("telemetry_parse_errors")
        and valid_hash(input_hash)
        and valid_hash(system_hash)
        and input_hash == system_hash
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--prior-convergence-final", type=Path)
    parser.add_argument("--feasibility-149", type=Path)
    parser.add_argument("--feasibility-407", type=Path)
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({
            "schema": SCHEMA,
            "status": "validation-ok",
            "n_tasks": 9,
            "settings": SETTINGS,
            "layouts": LAYOUTS,
            "median_tolerance_pct": 2.0,
            "max_tolerance_pct": 5.0,
        }))
        return
    if not os.environ.get("SLURM_ARRAY_JOB_ID") or not os.environ.get("SLURM_ARRAY_TASK_ID"):
        raise SystemExit("Submit refine-3/refine-4 convergence as a SLURM array")
    required = (
        args.corpus,
        args.prior_convergence_final,
        args.feasibility_149,
        args.feasibility_407,
    )
    if any(path is None for path in required):
        raise SystemExit("corpus and all pinned evidence paths are required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if task_id not in range(9):
        raise SystemExit("canonical refine-3/refine-4 protocol has tasks 0..8")

    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty or untracked_code:
        raise SystemExit("Refusing scientific convergence run from dirty source")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    batch_script = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not batch_script.is_file():
        raise SystemExit("exact executed SLURM batch script is unavailable")

    sources = [ROOT / name for name in SOURCE_NAMES]
    initial_source_hashes = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sources
    }
    tracked_batch_sha = initial_source_hashes[
        "code/jobs/submit_corpus_v4_refine34_convergence.sh"
    ]
    if file_sha256(batch_script) != tracked_batch_sha:
        raise SystemExit("executed SLURM script differs from tracked protocol")
    environment = runtime_environment()
    evidence = validate_prior_and_feasibility(
        args.prior_convergence_final,
        {149: args.feasibility_149, 407: args.feasibility_407},
        {
            name: initial_source_hashes[name]
            for name in FEASIBILITY_COMPARABLE_SOURCES
        },
        environment,
    )

    samples, corpus_summary = load_final_corpus(args.corpus)
    if corpus_summary["artifacts_sha256"] != EXPECTED_CORPUS_SHA256:
        raise ValueError("source corpus hash mismatch")
    layout_id, geometry_sha256 = LAYOUTS[task_id]
    sample = next(sample for sample in samples if int(sample["layout_id"]) == layout_id)
    if sample["geometry_sha256"] != geometry_sha256:
        raise ValueError("selected geometry differs from frozen protocol")

    output = ROOT / "results/corpus_v4/refine34_convergence/jobs" / (
        f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "git_head": head,
            "git_dirty_paths": dirty,
            "file_sha256": initial_source_hashes,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            **environment,
            "executed_batch_script": {
                "path": str(batch_script),
                "sha256": file_sha256(batch_script),
            },
            "setting_timeout_s": args.timeout_s,
            **evidence,
        },
        "selection": {
            "rule": "exact nine-layout selection frozen by convergence job 6833715",
            "selection_position": task_id,
            "layout_id": layout_id,
            "geometry_sha256": geometry_sha256,
            "n_traces": len(sample["layout"]["traces"]),
        },
        "settings": [],
        "task_pass": False,
    }
    atomic_write(path, payload)
    for refine, pad_mm in SETTINGS:
        setting = solve_bounded(sample["layout"], refine, pad_mm, args.timeout_s)
        print(
            f"layout={layout_id:04d} refine={refine} pad={pad_mm:g} "
            f"success={setting['success']} last_stage={setting['last_stage']} "
            f"wall={setting['wall_ms'] / 1000.0:.1f}s",
            flush=True,
        )
        checkpoint_setting(path, payload, setting)

    final_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    final_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    final_untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    final_source_hashes = {
        source.relative_to(ROOT).as_posix(): file_sha256(source) for source in sources
    }
    source_stable = bool(
        final_head == head
        and final_dirty == dirty
        and not final_untracked_code
        and final_source_hashes == initial_source_hashes
        and file_sha256(batch_script) == tracked_batch_sha
    )
    payload["provenance"].update({
        "final_git_head": final_head,
        "final_git_dirty_paths": final_dirty,
        "final_untracked_code": final_untracked_code,
        "final_file_sha256": final_source_hashes,
        "source_stable": source_stable,
    })
    payload["task_pass"] = source_stable and all(
        setting["resource_gate"]["pass"] for setting in payload["settings"]
    )
    atomic_write(path, payload)
    if not payload["task_pass"]:
        raise RuntimeError("refine-3/refine-4 task provenance gate failed")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
