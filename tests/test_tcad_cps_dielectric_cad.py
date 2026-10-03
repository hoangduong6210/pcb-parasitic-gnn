"""Synthetic box-boundary metadata and fake native API only; no CAD/mesh run."""
import ast
import copy
import itertools
import json
import math
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code/experiments/proofs"), str(REPO / "code/solvers")]
import tcad_cps_dielectric_cad as c
import tcad_cps_dielectric_cad_builder as builder
import tcad_cps_dielectric_cad_metadata as meta
import tcad_cps_dielectric_cad_worker as worker
import run_tcad_cps_dielectric_cad as runner
from scientific_artifact import atomic_write_json, sha256_file, sha256_json
from test_tcad_cps_reference import scheduler_fixture

P = c.protocol()
CFG = P[c.PHASE]["geometry_checks"]


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def report(mode="toy", split=False):
    """Construct a tiny combinatorial fixture, never native CAD or tetrahedra."""
    _, layout, arm = c.mode_input(mode, P)
    boxes, domain = meta.domain_inputs(layout, arm["pad_mm"], CFG)
    index = {d: {} for d in range(4)}
    point_ids, edge_ids, face_ids = {}, {}, {}

    def entity(dim, tag, box, mass, boundary):
        index[dim][tag] = {"tag": tag, "bbox_mm": list(box), "measure_native": mass,
            "boundary": sorted(boundary), "upward": [], "kind": ["Point", "Line", "Plane", "Volume"][dim]}

    def point(coordinates):
        key = tuple(coordinates)
        if key not in point_ids:
            tag = point_ids[key] = len(point_ids)+1
            entity(0, tag, [v for x in key for v in (x, x)], None, [])
        return point_ids[key]

    def face(box):
        key = tuple(box)
        if key not in face_ids:
            tag = face_ids[key] = len(face_ids)+1
            corners = list(itertools.product(*[sorted(set(box[k:k+2])) for k in (0, 2, 4)]))
            assert len(corners) == 4
            edges = []
            for a, b in itertools.combinations(corners, 2):
                if sum(x != y for x, y in zip(a, b)) == 1:
                    edge = tuple(sorted((a, b)))
                    if edge not in edge_ids:
                        e = edge_ids[edge] = len(edge_ids)+1
                        bounds = [v for x, y in zip(a, b) for v in (min(x, y), max(x, y))]
                        entity(1, e, bounds, math.sqrt(sum((x-y)**2 for x, y in zip(a, b))), [point(a), point(b)])
                    edges.append(edge_ids[edge])
            area = math.prod(box[k+1]-box[k] for k in (0, 2, 4) if box[k+1] != box[k])
            entity(2, tag, box, area, edges)
        return face_ids[key]

    def box_faces(box):
        faces = []
        for side in range(6):
            b = list(box)
            k = 2*(side//2)
            b[k] = b[k+1] = box[side]
            faces.append(face(b))
        return faces

    outer = box_faces(domain)
    provenance = [[]]
    next_tag = 2
    for i, box in enumerate(boxes):
        parts = [box]
        if split and i == 0:
            pairs = [[(box[k], (box[k]+box[k+1])/2), ((box[k]+box[k+1])/2, box[k+1])] for k in (0, 2, 4)]
            parts = [[v for pair in chunk for v in pair] for chunk in itertools.product(*pairs)]
        descendants = []
        for part in parts:
            descendants.append(next_tag)
            entity(3, next_tag, part, meta.volume(part), box_faces(part))
            next_tag += 1
        provenance.append(descendants)
    owners = {f: [] for f in index[2]}
    for tag, r in index[3].items():
        for f in r["boundary"]:
            owners[f].append(tag)
    dielectric = next_tag
    interfaces = [f for f, own in owners.items() if len(own) == 1]
    entity(3, dielectric, domain, meta.volume(domain)-math.fsum(meta.volume(b) for b in boxes), outer+interfaces)
    for d in (3, 2, 1):
        for tag, r in index[d].items():
            for child in r["boundary"]:
                index[d-1][child]["upward"].append(tag)
    for rows in index.values():
        for r in rows.values():
            r["upward"].sort()
    provenance[0] = sorted(index[3])
    before = {str(d): [index[d][t] for t in sorted(index[d])] for d in range(4)}
    reach = meta.reachable(index, [dielectric])
    after = copy.deepcopy({str(d): [index[d][t] for t in sorted(reach[d])] for d in range(4)})
    for d in range(4):
        for r in after[str(d)]:
            r["upward"] = [] if d == 3 else sorted(set(r["upward"]) & reach[d+1])
    return {"schema": "pcb-gnn.dielectric-cad-report.v1", "geometry_sha256": meta.geometry_sha256(layout),
        "canonical_boxes_mm": boxes, "domain_box_mm": domain, "input_volume_tags": list(range(1, len(boxes)+2)),
        "fragment_output_volumes": sorted(index[3]), "fragment_map": provenance,
        "before": before, "after": after, "removed_entities": {str(d): sorted(set(index[d])-reach[d]) for d in range(4)},
        "options": copy.deepcopy(P[c.PHASE]["cad_options"])}


def review(value, mode="toy"):
    _, layout, arm = c.mode_input(mode, P)
    return meta.review_report(value, layout, arm["pad_mm"], CFG, P[c.PHASE]["cad_options"])


def result(mode="toy", split=False):
    value = report(mode, split)
    layout_id, _, arm = c.mode_input(mode, P)
    return {"source_commit": "fixture", "mode": mode, "layout_id": layout_id, "arm": arm,
        "cad_report": value, "cad_report_sha256": sha256_json(value), "cad_summary": review(value, mode),
        "cad_contract_passed": True, "stages": list(c.STAGES), "mesh_generated": False, "mesh_feasible": False,
        "field_solver_executed": False, "reference_qualified": False, "training_may_start": False,
        "claim_eligible": False, "elapsed_s": 1., "peak_rss_gib": .1,
        "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(P)}


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
@pytest.mark.parametrize("split", [False, True])
def test_complete_metadata_replay(mode, split):
    value = result(mode, split)
    assert c.assess_result(value, mode, P)
    assert value["cad_summary"]["retained_volumes"] == 1
    if split:
        assert all(value["cad_report"]["removed_entities"][str(d)] for d in range(4))
    assert review(json.loads(json.dumps(value["cad_report"])), mode) == value["cad_summary"]


@pytest.mark.parametrize("case", ["geometry", "option", "input_identity", "map_count", "map_swap",
    "map_overlap", "fragment_output", "volume", "bounds", "outer_area", "incidence", "kind", "nan",
    "duplicate", "unknown_child", "point_mass", "missing_dimension", "removed", "after_volume",
    "after_geometry", "after_upward", "after_missing_face", "orphan_before", "extra", "bool_option"])
def test_corrupt_metadata_rejected(case):
    value = report(split=True)
    before = value["before"]
    if case == "geometry": value["geometry_sha256"] = "wrong"
    elif case == "option": value["options"]["Geometry.OCCParallel"] = 1
    elif case == "input_identity": value["input_volume_tags"][1] = value["input_volume_tags"][0]
    elif case == "map_count": value["fragment_map"].pop()
    elif case == "map_swap": value["fragment_map"][1:] = reversed(value["fragment_map"][1:])
    elif case == "map_overlap": value["fragment_map"][2] = value["fragment_map"][1]
    elif case == "fragment_output": value["fragment_output_volumes"].pop()
    elif case == "volume": before["3"][0]["measure_native"] *= .9
    elif case == "bounds": before["3"][0]["bbox_mm"][0] -= .01
    elif case == "outer_area": before["2"][0]["measure_native"] *= .9
    elif case == "incidence": before["2"][0]["upward"] = []
    elif case == "kind": before["2"][0]["kind"] = "BSpline surface"
    elif case == "nan": before["0"][0]["bbox_mm"][0] = float("nan")
    elif case == "duplicate": before["1"].append(before["1"][0])
    elif case == "unknown_child": before["2"][0]["boundary"] = [999]
    elif case == "point_mass": before["0"][0]["measure_native"] = 1
    elif case == "missing_dimension": before.pop("0")
    elif case == "removed": value["removed_entities"]["2"] = []
    elif case == "after_volume": value["after"]["3"].append(before["3"][0])
    elif case == "after_geometry": value["after"]["2"][0]["bbox_mm"][0] += 1e-9
    elif case == "after_upward": value["after"]["2"][0]["upward"] = []
    elif case == "after_missing_face": value["after"]["2"].pop()
    elif case == "orphan_before":
        point = copy.deepcopy(before["0"][-1])
        point.update(tag=999, upward=[])
        before["0"].append(point)
    elif case == "extra": value["cps_pf"] = 1.
    else: value["options"]["Geometry.OCCParallel"] = False
    with pytest.raises((ValueError, KeyError)):
        review(value)


def test_new_cad_protocol_is_not_a_mesh_or_field_retry():
    previous = c.parent.protocol()
    for key in ("physics", "runtime", "smoke", "recovery"):
        assert P[key] == previous[key]
    assert P[c.PHASE]["modes"] == ["toy", "local1", "repeat1"]
    assert P["resources"][c.PHASE]["mem_gib"] == 8
    assert all(limits == {"worker_timeout_s": 180, "rss_gib_max": 6} for limits in P["worker_limits"].values())
    assert P[c.PHASE]["worker_budget_s"] == 540


@pytest.mark.parametrize("kind", ["edge", "vertex"])
def test_cross_net_lower_dimensional_short_rejected(monkeypatch, kind):
    value = report()
    _, layout, arm = c.mode_input("toy", P)
    index, plan = meta.classify_before(value["before"], layout, arm["pad_mm"], value["fragment_map"], CFG)
    pri_face, sec_face = plan["faces"]["primary"][0], plan["faces"]["secondary"][0]
    pri_edge = index[2][pri_face]["boundary"][0]
    if kind == "edge":
        index[2][sec_face]["boundary"].append(pri_edge)
    else:
        sec_edge = index[2][sec_face]["boundary"][0]
        index[1][sec_edge]["boundary"].append(index[1][pri_edge]["boundary"][0])
    # Isolate the additional net-contact check after structural snapshot checks.
    monkeypatch.setattr(meta, "snapshot_index", lambda *a: index)
    with pytest.raises(ValueError, match="shared edge or vertex"):
        meta.classify_before(value["before"], layout, arm["pad_mm"], value["fragment_map"], CFG)


def test_child_geometry_must_fit_its_parent():
    value = report()
    value["before"]["0"][0]["bbox_mm"] = [1000., 1000., 1000., 1000., 1000., 1000.]
    with pytest.raises(ValueError, match="child CAD bounds"):
        review(value)


@pytest.mark.parametrize("field,value", [("mesh_generated", True), ("claim_eligible", 0),
    ("cad_contract_passed", 1), ("cad_report_sha256", "bad"), ("elapsed_s", 181),
    ("peak_rss_gib", 7), ("stages", []), ("cps_pf", 1.)])
def test_result_gate_rejects_bad_semantics(field, value):
    r = result()
    r[field] = value
    assert not c.assess_result(r, "toy", P)


def test_repeat_binds_full_geometry_and_keeps_downstream_closed():
    record = {"failure": None, "modes": {m: {"passed": True, "result": result(m)} for m in P[c.PHASE]["modes"]}}
    assert c.assessment(record, P)["diagnostic_passed"]
    record["modes"]["repeat1"]["result"] = result("repeat1", split=True)
    state = c.assessment(record, P)
    assert state["complete"] and not state["repeatability_passed"]
    for key in ("mesh_generated", "mesh_feasible", "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible"):
        assert state[key] is False


class FakeNative:
    def __init__(self, value):
        self.value = value
        self.options, self.inputs, self.removals = {}, {}, []
        self.active = False
        self.fragmented = False
        self.index = meta.snapshot_index(copy.deepcopy(value["before"]), CFG)
        self.model = SimpleNamespace(add=Mock(), occ=SimpleNamespace(addBox=self.add_box,
            synchronize=Mock(), getMass=self.mass, fragment=self.fragment, remove=self.remove),
            getEntities=self.entities, getBoundary=self.boundary, getAdjacencies=self.adjacencies,
            getBoundingBox=self.bounds, getType=lambda d, t: self.index[d][t]["kind"])
        self.option = SimpleNamespace(setNumber=lambda k, v: self.options.update({k: v}), getNumber=self.options.get)
        self.initialize = Mock(side_effect=self.start)
        self.finalize = Mock(side_effect=lambda: setattr(self, "active", False))
        self.isInitialized = lambda: self.active

    def start(self, *args, **kwargs):
        self.active = True

    def add_box(self, x, y, z, dx, dy, dz):
        tag = len(self.inputs)+1
        self.inputs[tag] = [x, x+dx, y, y+dy, z, z+dz]
        return tag

    def mass(self, dim, tag):
        return self.index[dim][tag]["measure_native"] if self.fragmented else meta.volume(self.inputs[tag])

    def bounds(self, dim, tag):
        b = self.index[dim][tag]["bbox_mm"] if self.fragmented else self.inputs[tag]
        return [b[i] for i in (0, 2, 4, 1, 3, 5)]

    def fragment(self, objects, tools, **kwargs):
        assert objects == [(3, 1)] and tools == [(3, t) for t in range(2, len(self.inputs)+1)]
        assert kwargs == dict(tag=-1, removeObject=True, removeTool=True)
        self.fragmented = True
        return ([(3, t) for t in self.value["fragment_output_volumes"]],
                [[(3, t) for t in row] for row in self.value["fragment_map"]])

    def entities(self, dim):
        return [(dim, t) for t in sorted(self.index[dim])]

    def boundary(self, pairs, **kwargs):
        assert kwargs == dict(combined=False, oriented=False, recursive=False)
        dim, tag = pairs[0]
        return [(dim-1, child) for child in self.index[dim][tag]["boundary"]]

    def adjacencies(self, dim, tag):
        row = self.index[dim][tag]
        return row["upward"], row["boundary"]

    def remove(self, pairs, recursive):
        assert recursive is False
        self.removals.append(pairs)
        for dim, tag in pairs:
            row = self.index[dim].pop(tag)
            assert not row["upward"]
            if dim:
                for child in row["boundary"]:
                    self.index[dim-1][child]["upward"].remove(tag)


def fake_guards(monkeypatch):
    for module in (builder, c):
        monkeypatch.setattr(module, "check_allocation", lambda *a: {"JobId": "123"})
        monkeypatch.setattr(module, "check_source", lambda **kw: {})
        monkeypatch.setattr(module, "check_runtime", lambda *a: runner.expected_runtime(P))


@pytest.mark.parametrize("split", [False, True])
def test_guarded_builder_with_fake_native(monkeypatch, split):
    value = report(split=split)
    fake = FakeNative(value)
    fake_guards(monkeypatch)
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    stages = []
    actual = builder.build_cad("toy", lambda stage, payload: stages.append(stage))
    assert actual == value
    assert stages == c.STAGES
    assert fake.active is False
    fake.initialize.assert_called_once_with([], readConfigFiles=False, run=False)
    assert [pairs[0][0] for pairs in fake.removals] == ([3, 2, 1, 0] if split else [3])


def test_native_failure_finalizes_without_erasing_unproven_entities(monkeypatch):
    fake = FakeNative(report())
    fake.model.occ.fragment = Mock(side_effect=ValueError("synthetic fragment failure"))
    fake_guards(monkeypatch)
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    with pytest.raises(ValueError, match="fragment failure"):
        builder.build_cad("toy", lambda *a: None)
    fake.finalize.assert_called_once()
    assert not fake.removals


@pytest.mark.parametrize("case", ["option", "input_mass", "input_bounds", "mapping", "lost_interface", "orphan_parent", "changed_geometry", "active_session"])
def test_native_boundary_and_removal_fail_closed(monkeypatch, case):
    fake = FakeNative(report(split=True))
    fake_guards(monkeypatch)
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    if case == "option":
        fake.option.getNumber = lambda _: -99
    elif case == "input_mass":
        fake.model.occ.getMass = lambda *a: -1.
    elif case == "input_bounds":
        fake.model.getBoundingBox = lambda *a: [0.]*6
    elif case == "mapping":
        fake.value["fragment_map"][1:] = reversed(fake.value["fragment_map"][1:])
    elif case == "active_session":
        fake.active = True
    else:
        original = fake.model.occ.remove
        def broken(pairs, recursive):
            original(pairs, recursive)
            if pairs[0][0] == 3:
                retained = next(t for t, r in fake.index[2].items() if r["upward"])
                if case == "lost_interface":
                    fake.index[2].pop(retained)
                elif case == "orphan_parent":
                    orphan = next(t for t, r in fake.index[2].items() if not r["upward"])
                    fake.index[2][orphan]["upward"] = [999]
                else:
                    fake.index[2][retained]["measure_native"] *= 2
        fake.model.occ.remove = broken
    with pytest.raises(ValueError):
        builder.build_cad("toy", lambda *a: None)
    if case == "active_session":
        fake.initialize.assert_not_called()
        fake.finalize.assert_not_called()
    else:
        fake.finalize.assert_called_once()


def test_parent_stops_on_first_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "fixture"})
    monkeypatch.setattr(c, "check_source", lambda: {})
    monkeypatch.setattr(runner, "validate_attempt", lambda *a: None)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    bounded = Mock(return_value={"passed": False, "failure": "synthetic failure"})
    monkeypatch.setattr(runner, "bounded_mode", bounded)
    assert not runner.run(P, {"JobId": "123"}, runner.expected_runtime(P))
    assert bounded.call_count == 1


def test_summary_boolean_is_not_numeric_admission():
    value = result()
    value["cad_summary"]["cad_contract_passed"] = 1
    assert not c.assess_result(value, "toy", P)


def test_worker_fake_native_integration(monkeypatch, capsys):
    fake_guards(monkeypatch)
    monkeypatch.setitem(sys.modules, "gmsh", FakeNative(report()))
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "fixture"})
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    worker.main()
    lines = capsys.readouterr().out.splitlines()
    observed = json.loads(next(line[7:] for line in lines if line.startswith("RESULT=")))
    assert c.assess_result(observed, "toy", P)


def test_login_guards_precede_native_calls(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    for entry in (runner.main, worker.main, lambda: builder.build_cad("toy", lambda *a: None)):
        with pytest.raises(ValueError, match="login-node"):
            entry()
    tree = ast.parse((REPO / "code/solvers/tcad_cps_dielectric_cad_builder.py").read_text())
    body = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_cad")
    native = next(n.lineno for n in body.body if isinstance(n, ast.Import))
    calls = [n.lineno for n in ast.walk(body) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id in ("check_source", "check_runtime", "check_allocation")]
    assert len(calls) == 3 and max(calls) < native
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("mesh", "generate", "solve", "assemble", "cg") for n in ast.walk(tree))


def test_allocation_and_wrapper():
    scheduler, env = scheduler_fixture("smoke")
    matches = c.parent.parent.parent.support.original.allocation_matches
    assert matches(scheduler, env, "a0126", c.PHASE, P)
    assert not matches(scheduler, env, "ascend-login01", c.PHASE, P)
    assert not matches({**scheduler, "Requeue": "1"}, env, "a0126", c.PHASE, P)
    shell = (REPO / c.WRAPPER).read_text()
    for text in ("--mem=8G", "--time=00:15:00", "--no-requeue", "PCB_TCAD_BATCH_PHASE=dielectric_cad"):
        assert text in shell


@pytest.mark.parametrize("cap", ["time", "rss"])
def test_parent_watchdog_preserves_failed_logs(monkeypatch, tmp_path, cap):
    process = Mock(pid=123, returncode=-9)
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 181, 182] if cap == "time" else [0, 1, 2])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 7 if cap == "rss" else 0)
    monkeypatch.setenv("GH_TOKEN", "synthetic-secret")
    receipt = runner.bounded_mode(tmp_path, "toy", P)
    assert receipt["passed"] is False and receipt["failure"]
    assert set(receipt["files_sha256"]) == {"toy.stdout", "toy.stderr"}
    assert "GH_TOKEN" not in runner.subprocess.Popen.call_args.kwargs["env"]
    kill.assert_called_once_with(123, runner.signal.SIGKILL)


def setup_attempt(monkeypatch, tmp_path, outcome="pass"):
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "fixture"})
    directory = c.attempt_directory("123", create=True)
    record = {"source_commit": "fixture", "scheduler": {"JobId": "123"},
              "runtime": runner.expected_runtime(P), "failure": None, "modes": {}}
    modes = P[c.PHASE]["modes"][:2] if outcome == "timeout" else P[c.PHASE]["modes"]
    for mode in modes:
        failed = outcome == "timeout" and mode == "local1"
        value = result(mode, split=outcome == "negative" and mode == "repeat1")
        (directory / f"{mode}.stdout").write_text("incomplete native log\n" if failed else "RESULT=" + json.dumps(value) + "\n")
        (directory / f"{mode}.stderr").write_text("")
        arm = {"mode": mode, "passed": not failed, "failure": "worker wall-time cap exceeded" if failed else None,
               "returncode": -9 if failed else 0, "elapsed_s": 181. if failed else 1., "observed_peak_rss_gib": .1,
               "files_sha256": {f"{mode}.{s}": sha256_file(directory / f"{mode}.{s}") for s in ("stdout", "stderr")}}
        if not failed:
            arm["result"] = value
        record["modes"][mode] = arm
        atomic_write_json(directory / f"{mode}.json", arm)
    record.update(c.assessment(record, P))
    atomic_write_json(directory / "attempt.json", record)
    return directory, record


@pytest.mark.parametrize("outcome", ["pass", "negative", "timeout"])
def test_receipt_and_terminal_review(monkeypatch, tmp_path, outcome):
    directory, record = setup_attempt(monkeypatch, tmp_path, outcome)
    assert runner.validate_attempt(directory, P) == record
    monkeypatch.setattr(runner, "accounting", lambda _: ("fixture", [{"JobID": "123", "Restarts": "0",
        "State": "FAILED" if outcome == "timeout" else "COMPLETED", "ExitCode": "2:0" if outcome == "timeout" else "0:0"}]))
    terminal = runner.terminal_review("123", P)
    assert terminal["diagnostic_passed"] == (outcome == "pass")
    assert terminal["complete"] == (outcome != "timeout")


@pytest.mark.parametrize("case", ["claim", "boolean", "coverage", "extra", "symlink", "cap", "log"])
def test_attempt_corruption_rejected(monkeypatch, tmp_path, case):
    directory, record = setup_attempt(monkeypatch, tmp_path)
    if case == "claim": record["mesh_feasible"] = True
    elif case == "boolean": record["claim_eligible"] = 0
    elif case == "coverage": record["modes"].pop("toy")
    elif case == "extra": (directory / "extra").write_text("")
    elif case == "symlink":
        (directory / "toy.stdout").rename(directory / "target")
        (directory / "toy.stdout").symlink_to(directory / "target")
    elif case == "cap":
        record["modes"]["toy"]["elapsed_s"] = 181.
        atomic_write_json(directory / "toy.json", record["modes"]["toy"])
    else: (directory / "toy.stdout").write_text("changed")
    atomic_write_json(directory / "attempt.json", record)
    with pytest.raises(ValueError):
        runner.validate_attempt(directory, P)


def test_source_closure_after_freeze():
    if not (REPO / c.LOCK).exists():
        pytest.skip("pre-freeze validation")
    lock = c.check_source(execution=False)
    assert set(c.SOURCES) <= set(lock["files_sha256"])
    assert str(c.ARCHIVE) in lock["files_sha256"]
