"""Guard/protocol tests and a small explicit box lattice with a fake native API."""
import ast
import copy
import itertools
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_dielectric_mesh as c
import tcad_cps_dielectric_mesh_builder as builder
import tcad_cps_dielectric_mesh_worker as worker
import run_tcad_cps_dielectric_mesh as runner
from tcad_cps_dielectric_mesh_bundle import load_bundle
from scientific_artifact import sha256_json, atomic_write_json
from test_tcad_cps_dielectric_cad import report, FakeNative as FakeCAD
from test_tcad_cps_dielectric_mesh_audit import FakeNative as FakeMesh

P = c.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def box_packet(cad):
    """A tiny explicit Cartesian test lattice fitting the canonical CAD toy.

    Six fixed simplex patterns per retained cell; no native mesher/solver.
    Signed conditions are fake values; determinants/areas/volumes are checked
    against independent canonical CAD metadata by the production audit.
    """
    boxes = [cad["domain_box_mm"], *cad["canonical_boxes_mm"]]
    axes = [sorted({b[k] for b in boxes for k in (2*axis, 2*axis+1)}) for axis in range(3)]
    positions = list(itertools.product(*axes))
    index = {p: i for i, p in enumerate(positions)}
    tets = []
    for cell in itertools.product(*(range(len(a)-1) for a in axes)):
        mid = [(axes[i][cell[i]]+axes[i][cell[i]+1])/2 for i in range(3)]
        if any(all(b[2*i] < mid[i] < b[2*i+1] for i in range(3)) for b in boxes[1:]):
            continue
        for perm in itertools.permutations(range(3)):
            vertex = list(cell)
            tet = [index[tuple(axes[i][vertex[i]] for i in range(3))]]
            for axis in perm:
                vertex[axis] += 1
                tet.append(index[tuple(axes[i][vertex[i]] for i in range(3))])
            if sum(perm[i] > perm[j] for i in range(3) for j in range(i+1, 3)) % 2:
                tet[1], tet[2] = tet[2], tet[1]
            tets.append(tet)
    used = sorted({v for t in tets for v in t})
    t = np.searchsorted(used, np.asarray(tets))
    xyz = np.asarray(positions, dtype=float)[used]
    facets = {}
    for tet in t:
        for face in itertools.combinations(tet.tolist(), 3):
            key = tuple(sorted(face))
            facets[key] = facets.get(key, 0)+1
    tris, tags = [], []
    for face, count in facets.items():
        if count != 1:
            continue
        points = xyz[list(face)]
        matches = [r["tag"] for r in cad["after"]["2"] if
            np.all(points >= np.array(r["bbox_mm"][::2])-1e-12) and np.all(points <= np.array(r["bbox_mm"][1::2])+1e-12)]
        assert len(matches) == 1
        tris.append(face)
        tags.append(matches[0])
    determinant = np.einsum("ij,ij->i", xyz[t[:, 1]]-xyz[t[:, 0]], np.cross(xyz[t[:, 2]]-xyz[t[:, 0]], xyz[t[:, 3]]-xyz[t[:, 0]]))
    node_tags = np.arange(1, len(xyz)+1, dtype=np.int64)
    return {"node_tags": node_tags, "coordinates_mm": xyz,
        "tetrahedron_tags": np.arange(10001, 10001+len(t), dtype=np.int64), "tetrahedron_nodes": node_tags[t],
        "tetrahedron_volumes": np.full(len(t), cad["after"]["3"][0]["tag"], dtype=np.int64),
        "triangle_tags": np.arange(20001, 20001+len(tris), dtype=np.int64),
        "triangle_nodes": node_tags[np.asarray(tris)], "triangle_faces": np.array(tags, dtype=np.int64),
        "min_sicn": np.full(len(t), .5), "min_det_jac_mm3": determinant}


def setup_native(monkeypatch, tmp_path):
    cad = report()
    p = copy.deepcopy(P)
    p[c.PHASE]["cad_report_sha256"]["toy"] = sha256_json(cad)
    monkeypatch.setattr(c, "protocol", lambda: p)
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    for name in ("check_source", "check_runtime", "check_allocation"):
        monkeypatch.setattr(c, name, lambda *a, **kw: {})
    monkeypatch.setattr(c, "check_allocation", lambda *a: {"JobId": "123"})
    monkeypatch.setattr(c, "check_runtime", lambda *a: runner.expected_runtime(p))
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "fixture"})
    directory = c.attempt_directory("123", create=True)
    native = FakeCAD(cad)
    final = box_packet(cad)
    raw = copy.deepcopy(final)
    raw["coordinates_mm"][0, 0] += .001
    raw["min_sicn"][0] = -1e-16
    mesh = FakeMesh(raw, cad["after"])
    mesh.generate = Mock()
    mesh.optimize = Mock(side_effect=lambda **kw: setattr(mesh, "packet", copy.deepcopy(final)))
    native.model.mesh = mesh
    native.option.getString = lambda key: "hxt occ"
    monkeypatch.setitem(sys.modules, "gmsh", native)
    monkeypatch.setattr(builder, "apply_mesh_policy", lambda *a: c.expected_policy("toy", p))
    return p, directory, native, final


def test_protocol_preserves_all_existing_mesh_limits():
    prior = c.parent.parent.protocol()
    for mode, limits in prior["worker_limits"].items():
        assert all(P["worker_limits"][mode][k] == v for k, v in limits.items())
    assert P["resources"][c.PHASE] == prior["resources"]["hxt_postopt"]
    for field in ("mesh", "runtime", "physics", "recovery", "smoke"):
        assert P[field] == prior[field]
    assert P[c.PHASE]["optimizer"] == prior["hxt_postopt"]["optimizer"]


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
def test_protocol_anchors_are_the_actual_archived_native_reports(mode):
    receipt = c.read_json(ROOT / c.parent.BASE / "job_7651941" / f"{mode}.json")
    assert receipt["passed"] is True
    assert sha256_json(receipt["result"]["cad_report"]) == P[c.PHASE]["cad_report_sha256"][mode]


def test_cad_construction_statements_match_immutable_builder():
    import tcad_cps_dielectric_cad_builder as original
    def statements(path, function):
        tree = ast.parse(Path(path).read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
        body = next(n for n in node.body if isinstance(n, ast.Try)).body
        end = next(i for i, n in enumerate(body) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                   and n.value.args and isinstance(n.value.args[0], ast.Constant) and n.value.args[0].value == "cad_after_verified")
        class Normalize(ast.NodeTransformer):
            def visit_Name(self, node):
                return ast.Constant(value="dielectric_cad") if node.id == "PHASE" else node
        return [ast.dump(Normalize().visit(n)) for n in body[:end+1]]
    assert statements(original.__file__, "build_cad") == statements(builder.__file__, "build_mesh")


def test_full_fake_native_builder_preserves_raw_and_refetches_final(monkeypatch, tmp_path):
    p, directory, native, expected = setup_native(monkeypatch, tmp_path)
    stages = []
    result = builder.build_mesh("toy", lambda s, v: stages.append(s), directory / "toy.payload")
    assert stages == c.STAGES and not native.active
    native.model.mesh.generate.assert_called_once_with(3)
    native.model.mesh.optimize.assert_called_once_with(**p[c.PHASE]["optimizer"])
    raw = load_bundle(directory / "toy.payload/raw", p[c.PHASE]["payload"])
    final = load_bundle(directory / "toy.payload/final", p[c.PHASE]["payload"])
    assert raw["min_sicn"][0] < 0
    assert not np.array_equal(raw["coordinates_mm"], final["coordinates_mm"])
    assert all(np.array_equal(final[k], expected[k]) for k in expected)
    result.update(mode="toy", layout_id=c.mode_input("toy", p)[0], arm=c.mode_input("toy", p)[2],
                  stages=stages, elapsed_s=1., peak_rss_gib=.1, **{k: False for k in c.CLOSED})
    assert c.assess_result(result, "toy", p)


def test_worker_fake_native_full_receipt(monkeypatch, tmp_path, capsys):
    p, directory, native, _ = setup_native(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    worker.main()
    output = capsys.readouterr().out
    result = json.loads(next(line[7:] for line in output.splitlines() if line.startswith("RESULT=")))
    runner.validate_result(result, "toy", p, "123", directory)


@pytest.mark.parametrize("failure", ["cad_hash", "optimizer", "audit", "cad_mutation"])
def test_native_failure_stops_and_finalizes_preserving_partial_evidence(monkeypatch, tmp_path, failure):
    p, directory, native, _ = setup_native(monkeypatch, tmp_path)
    if failure == "cad_hash": p[c.PHASE]["cad_report_sha256"]["toy"] = "0"*64
    elif failure == "optimizer": native.model.mesh.optimize.side_effect = ValueError("optimizer fault")
    elif failure == "audit": monkeypatch.setattr(builder, "audit_cad_mesh", Mock(side_effect=ValueError("audit fault")))
    else:
        original = native.model.mesh.optimize.side_effect
        def changed(**kw):
            original(**kw)
            native.index[0][min(native.index[0])]["bbox_mm"][0] -= 1e-9
        native.model.mesh.optimize.side_effect = changed
    with pytest.raises(ValueError):
        builder.build_mesh("toy", lambda *a: None, directory / "toy.payload")
    assert not native.active
    if failure == "cad_hash": native.model.mesh.generate.assert_not_called()
    else: assert (directory / "toy.payload/raw/manifest.json").is_file()
    if failure in ("audit", "cad_mutation"):
        assert (directory / "toy.payload/final/manifest.json").is_file()


def test_login_guard_covers_all_new_native_entry_points(monkeypatch, tmp_path):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    native = Mock()
    monkeypatch.setitem(sys.modules, "gmsh", native)
    for entry in (runner.main, worker.main, lambda: builder.build_mesh("toy", lambda *a: None, tmp_path)):
        with pytest.raises(ValueError, match="login-node"):
            entry()
    native.initialize.assert_not_called()


@pytest.mark.parametrize("cap", ["time", "rss"])
def test_parent_watchdog_stops_worker_and_scrubs_credentials(monkeypatch, tmp_path, cap):
    process = Mock(pid=123, returncode=-9)
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 601, 602] if cap == "time" else [0, 1, 2])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 7 if cap == "rss" else 0)
    monkeypatch.setenv("GH_TOKEN", "synthetic-secret")
    receipt = runner.bounded_mode(tmp_path, "toy", P)
    assert not receipt["passed"] and receipt["failure"]
    assert "GH_TOKEN" not in runner.subprocess.Popen.call_args.kwargs["env"]
    kill.assert_called_once_with(123, runner.signal.SIGKILL)


def test_parent_stops_after_first_failed_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "identity", lambda: {})
    monkeypatch.setattr(c, "check_source", lambda: {})
    monkeypatch.setattr(runner, "validate_attempt", lambda *a: None)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    bounded = Mock(return_value={"passed": False, "failure": "synthetic"})
    monkeypatch.setattr(runner, "bounded_mode", bounded)
    assert not runner.run(P, {"JobId": "123"}, runner.expected_runtime(P))
    assert bounded.call_count == 1


def test_source_lock_when_frozen():
    if not (ROOT / c.LOCK).exists():
        pytest.skip("new source lock is not frozen yet")
    assert c.check_source(execution=False) == c.frozen_lock()


@pytest.mark.parametrize("case", ["claim", "mesh_accuracy", "negative_quality", "cad_bool", "wrong_mode",
    "stages", "optimizer", "optimizer_calls", "time", "rss", "cad_hash", "packet_hash", "audit_hash",
    "bundle_cap", "tet_cap", "component", "group", "facets", "raw_count", "raw_nan", "cps"])
def test_result_gate_rejects_semantic_mutations(monkeypatch, tmp_path, case):
    p, directory, native, _ = setup_native(monkeypatch, tmp_path)
    value = builder.build_mesh("toy", lambda *a: None, directory / "toy.payload")
    value.update(mode="toy", layout_id=c.mode_input("toy", p)[0], arm=c.mode_input("toy", p)[2],
        stages=list(c.STAGES), elapsed_s=1., peak_rss_gib=.1, **{k: False for k in c.CLOSED})
    assert c.assess_result(value, "toy", p)
    if case == "claim": value["claim_eligible"] = True
    elif case == "mesh_accuracy": value["mesh_audit"]["numerical_accuracy_qualified"] = True
    elif case == "negative_quality": value["mesh_audit"]["minimum_sicn"] = -1e-16
    elif case == "cad_bool": value["cad_summary"]["cad_contract_passed"] = 1
    elif case == "wrong_mode": value["mode"] = "local1"
    elif case == "stages": value["stages"].pop()
    elif case == "optimizer": value["optimizer"] = {**value["optimizer"], "niter": 2}
    elif case == "optimizer_calls": value["optimizer_calls"] = True
    elif case == "time": value["elapsed_s"] = 601
    elif case == "rss": value["peak_rss_gib"] = 7
    elif case == "cad_hash": value["cad_report_sha256"] = "0"*64
    elif case == "packet_hash": value["bundles"]["final"]["packet_sha256"] = "0"*64
    elif case == "audit_hash": value["mesh_audit_sha256"] = "0"*64
    elif case == "bundle_cap": value["bundles"]["final"]["payload_bytes"] = 3*1024**3
    elif case == "tet_cap": value["mesh_audit"]["mesh_tetrahedra"] = 1500001
    elif case == "component": value["mesh_audit"]["tetrahedral_components"] = 2
    elif case == "group": value["mesh_audit"]["boundary_groups"]["primary"]["faces"] = []
    elif case == "facets": value["mesh_audit"]["exterior_facets"] += 1
    elif case == "raw_count": value["quality_before"]["tetrahedra"] = 0
    elif case == "raw_nan": value["quality_before"]["metrics"]["min_sicn"]["minimum"] = float("nan")
    else: value["cps_pf"] = 1.
    if case != "audit_hash":
        value["mesh_audit_sha256"] = sha256_json(value["mesh_audit"])
    assert not c.assess_result(value, "toy", p)


def test_exact_repeat_binds_both_raw_and_final_packets(monkeypatch, tmp_path):
    p, directory, native, _ = setup_native(monkeypatch, tmp_path)
    value = builder.build_mesh("toy", lambda *a: None, directory / "toy.payload")
    value.update(stages=list(c.STAGES), elapsed_s=1., peak_rss_gib=.1, **{k: False for k in c.CLOSED})
    monkeypatch.setattr(c, "mode_input", lambda mode, p: c.parent.mode_input("toy", p))
    monkeypatch.setattr(c, "expected_policy", lambda mode, p: c.parent.parent.expected_policy("toy", p))
    record = {"failure": None, "modes": {}}
    for mode in p[c.PHASE]["modes"]:
        p[c.PHASE]["cad_report_sha256"][mode] = value["cad_report_sha256"]
        result = {**copy.deepcopy(value), "mode": mode, "layout_id": c.mode_input(mode, p)[0], "arm": c.mode_input(mode, p)[2]}
        record["modes"][mode] = {"passed": True, "result": result}
    assert c.assessment(record, p)["diagnostic_passed"]
    record["modes"]["repeat1"]["result"]["bundles"]["raw"]["packet_sha256"] = "0"*64
    flags = c.assessment(record, p)
    assert flags["complete"] and not flags["repeatability_passed"]
    assert all(flags[k] is False for k in (*c.CLOSED, "mesh_feasible", "automatic_expansion"))


def test_partial_payload_is_hashed_and_receipt_validated_without_numeric_replay(monkeypatch, tmp_path):
    p, directory, native, _ = setup_native(monkeypatch, tmp_path)
    payload = directory / "toy.payload/raw"
    payload.mkdir(parents=True)
    (payload / "partial.bin").write_bytes(b"partial synthetic native output")
    for suffix in ("stdout", "stderr"):
        (directory / f"toy.{suffix}").write_text("failed synthetic worker")
    arm = {"mode": "toy", "passed": False, "returncode": -9, "failure": "worker wall-time cap exceeded",
           "elapsed_s": 601., "observed_peak_rss_gib": .1, "files_sha256": runner.mode_files(directory, "toy")}
    atomic_write_json(directory / "toy.json", arm)
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p),
              "modes": {"toy": arm}, "failure": None}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    assert runner.validate_attempt(directory, p) == record
    (payload / "partial.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash closure"):
        runner.validate_attempt(directory, p)


def test_guards_precede_all_numerical_imports_in_builder():
    tree = ast.parse(Path(builder.__file__).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_mesh")
    imported = min(n.lineno for n in function.body if isinstance(n, ast.Import))
    guards = [n.lineno for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ("check_source", "check_allocation", "check_runtime")]
    assert len(guards) == 3 and max(guards) < imported


def test_wrapper_is_single_bounded_allocation():
    shell = (ROOT / c.WRAPPER).read_text()
    for required in ("--mem=160G", "--time=00:55:00", "--cpus-per-task=1", "--no-requeue", "PCB_TCAD_BATCH_PHASE=dielectric_mesh"):
        assert required in shell
    assert "--array" not in shell
