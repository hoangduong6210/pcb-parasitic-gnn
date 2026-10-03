#!/usr/bin/env python3
"""Archive terminal receipts byte-for-byte; geometry/metadata only, no solver."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))
from geometry_contract import trace_box
from scientific_artifact import atomic_write_json, sha256_file
from tcad_cps_reference import read_json
from run_tcad_cps_reference import accounting, result_from_log

BASE = Path("results/tcad/cps_reference_v1")
MANIFEST = BASE / "archive/pilot_7641200/manifest.json"
DIAGNOSTIC = BASE / "archive/pilot_7641200/geometry_cost.json"
SOURCE_COMMIT = "d00426684f93155cc20924630facc63a94e72d32"
LOCK_SHA = "31f1aeb3dad2384f0f982b105722406f914f2a1b027230c074b5860b077fc510"


def metadata_review(root: Path) -> dict:
    panel = read_json(root / BASE / "plan/panel.json")
    records = []
    for task, layout_id in enumerate(panel["pilot_layout_ids"]):
        directory = root / BASE / f"pilot/job_7641200/task_{task}"
        receipt = read_json(directory / "attempt.json")
        if receipt["source_commit"] != SOURCE_COMMIT or receipt["lock_sha256"] != LOCK_SHA or receipt["layout_id"] != layout_id:
            raise ValueError("original task identity mismatch")
        arms = []
        for name, arm in receipt["arms"].items():
            if read_json(directory / f"{name}.json") != arm:
                raise ValueError("original arm receipt mismatch")
            if set(arm["files_sha256"]) != {f"{name}.stdout", f"{name}.stderr"}:
                raise ValueError("unexpected raw-log closure")
            for filename, digest in arm["files_sha256"].items():
                if sha256_file(directory / filename) != digest:
                    raise ValueError("original raw-log hash mismatch")
            if arm["passed"] and result_from_log(directory / f"{name}.stdout") != arm["result"]:
                raise ValueError("saved result differs from original raw log")
            stages = [json.loads(line[6:]) for line in (directory / f"{name}.stdout").read_text().splitlines() if line.startswith("STAGE=")]
            mesh = next((s for s in stages if s["stage"] == "mesh_generated"), {})
            arms.append({"name": name, "passed": arm["passed"], "elapsed_s": arm["elapsed_s"],
                         "mesh_generation_elapsed_s": mesh.get("elapsed_s"), "mesh_nodes": mesh.get("n_nodes"),
                         "peak_rss_gib": arm["observed_peak_rss_gib"], "failure": arm["failure"]})
        geometry = next(r for r in panel["rows"] if r["layout_id"] == layout_id)
        boxes = [trace_box(geometry["layout"], t) for t in geometry["layout"]["traces"]]
        pair_gaps = []
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if min(a[1], b[1]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[2], b[2]):
                    gap = max(a[4], b[4]) - min(a[5], b[5])
                    if gap > 0:
                        pair_gaps.append(gap)
        volumes = {}
        for expansion in (0.11, 0.055):
            volumes[str(expansion)] = sum((b[1]-b[0]+2*expansion)*(b[3]-b[2]+2*expansion)*(b[5]-b[4]+2*expansion) for b in boxes)
        records.append({"layout_id": layout_id, "geometry_sha256": geometry["geometry_sha256"],
                        "n_conductors": len(boxes), "minimum_projected_interlayer_gap_mm": min(pair_gaps),
                        "sum_expanded_box_volume_mm3": volumes,
                        "volume_proxy_warning": "sum counts overlaps repeatedly; excludes transition layer; not a node-count prediction",
                        "attempt_sha256": sha256_file(directory / "attempt.json"), "arms": arms})
    return {"schema": "pcb-gnn.tcad-cps-v1-geometry-cost.v1", "rows": records,
            "target_values_used_for_support_choice": False,
            "scope": "geometry and operational cost review; no sensitivity aggregation or numerical replay"}


def check_archive() -> dict:
    manifest = read_json(ROOT / MANIFEST)
    for path, digest in manifest["files_sha256"].items():
        if sha256_file(ROOT / path) != digest:
            raise ValueError(f"archive hash mismatch: {path}")
    if read_json(ROOT / DIAGNOSTIC) != metadata_review(ROOT):
        raise ValueError("geometry/cost receipt does not reconstruct")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        manifest = check_archive()
    else:
        source = args.source_root.resolve(strict=True)
        if ROOT not in source.parents or source == ROOT:
            raise ValueError("source must be a separate worktree inside the authorized workspace")
        if (ROOT / MANIFEST).exists():
            raise ValueError("archive already exists")
        review = metadata_review(source)
        _, rows = accounting("7641200")
        _, final = accounting("7641201")
        expected = {"7641200_0": ("COMPLETED", "0:0"), "7641200_1": ("COMPLETED", "0:0"),
                    "7641200_2": ("FAILED", "2:0"), "7641201": ("FAILED", "2:0")}
        observed = rows + final
        if len(observed) != 4 or {r["JobID"] for r in observed} != set(expected):
            raise ValueError("missing or duplicate terminal accounting")
        if any((r["State"], r["ExitCode"]) != expected[r["JobID"]] or r["Restarts"] != "0" for r in observed):
            raise ValueError("unexpected terminal state")
        files = []
        for directory in (BASE / "pilot/job_7641200", BASE / "finalize/job_7641201"):
            paths = list((source / directory).rglob("*"))
            if any(p.is_symlink() for p in paths) or (ROOT / directory).exists():
                raise ValueError("refusing symlinks or archive overwrite")
            shutil.copytree(source / directory, ROOT / directory)
            files.extend(p.relative_to(source) for p in paths if p.is_file())
        logs = [f"tcad_cps_pilot_7641200_{task}.{suffix}" for task in range(3) for suffix in ("out", "err")]
        logs += [f"tcad_cps_final_7641201.{suffix}" for suffix in ("out", "err")]
        log_root = ROOT / MANIFEST.parent / "logs"
        log_root.mkdir(parents=True, exist_ok=False)
        for name in logs:
            original = source / "logs" / name
            if original.is_symlink():
                raise ValueError("symlinked scheduler log")
            shutil.copyfile(original, log_root / name)
            files.append((log_root / name).relative_to(ROOT))
            if sha256_file(original) != sha256_file(log_root / name):
                raise ValueError("scheduler log copy changed bytes")
        for path in files:
            original = source / path
            if original.exists() and sha256_file(original) != sha256_file(ROOT / path):
                raise ValueError("archive copy changed bytes")
        atomic_write_json(ROOT / DIAGNOSTIC, review)
        files.append(DIAGNOSTIC)
        manifest = {"schema": "pcb-gnn.tcad-cps-pilot-archive.v1", "source_commit": SOURCE_COMMIT,
                    "original_lock_sha256": LOCK_SHA, "accounting": observed,
                    "scientific_status": "rejected incomplete pilot; not repaired by archival",
                    "files_sha256": {str(p): sha256_file(ROOT / p) for p in sorted(files)}}
        atomic_write_json(ROOT / MANIFEST, manifest)
        check_archive()
    print(json.dumps({"files": len(manifest["files_sha256"]), "archive_sha256": sha256_file(ROOT / MANIFEST)}))


if __name__ == "__main__":
    main()
