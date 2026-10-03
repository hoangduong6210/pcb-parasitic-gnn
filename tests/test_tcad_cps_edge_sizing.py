"""Tiny independent finite-segment and fake-native sizing checks only."""
import copy
from fractions import Fraction
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"code/solvers"),str(ROOT/"code/experiments/proofs"),str(ROOT/"code/core")]
import tcad_cps_edge_sizing as e
from scientific_artifact import sha256_json

BOXES = [[1.,2.,1.,2.,1.,2.], [1.,2.,1.,2.,3.,4.]]
DOMAIN = [0.,3.,0.,3.,0.,5.]
POLICY = {"near_size_mm": .1,"far_size_mm":1.}
CFG = {"edge_plateau_half_width_mm": .05,"segment_count_max":512,"expression_bytes_max":131072,
    "mesh_options":{"Mesh.Algorithm":5,"Mesh.AlgorithmSwitchOnFailure":0,"Mesh.MeshSizeFactor":1},
    "probe_points_max":8192,"probe_rtol":1e-12,"probe_atol_mm":1e-12}
MESH = {"transition_thickness_mm":.5}


def request(): return e.sizing_policy(copy.deepcopy(BOXES),dict(POLICY),copy.deepcopy(CFG),MESH)


def evaluate(text,point):
    # Evaluate only our generated trusted grammar; the production oracle uses
    # independent exact projection and never evaluates this expression string.
    return eval(text.replace("^","**"),{"__builtins__":{},"Max":max,"Sqrt":math.sqrt,"x":point[0],"y":point[1]})


def fake_fields():
    fields,options,views,plugin = {},{},{},{}
    state = {"background":None,"next_view":0,"probe_calls":[],"distance_error":0.,"size_error":0.}
    def add(kind):
        tag = len(fields)+1; fields[tag] = {"kind":kind}; return tag
    def background(tag): state["background"] = tag
    api = SimpleNamespace(list=lambda:list(fields),add=add,
        setNumber=lambda t,k,v:fields[t].__setitem__(k,v),getNumber=lambda t,k:fields[t][k],
        setNumbers=lambda t,k,v:fields[t].__setitem__(k,v),getNumbers=lambda t,k:fields[t][k],
        setString=lambda t,k,v:fields[t].__setitem__(k,v),getString=lambda t,k:fields[t][k],
        getType=lambda t:fields[t]["kind"],setAsBackgroundMesh=background)
    def view_add(name):
        state["next_view"] += 1
        tag = state["next_view"]; views[tag] = {}; return tag
    def add_data(tag,kind,count,flat): views[tag].update(kind=kind,count=count,flat=list(flat))
    def field_value(tag,point):
        f = fields[tag]
        if f["kind"] == "MathEval": return evaluate(f["F"],point)
        if f["kind"] == "Min": return min(field_value(i,point) for i in f["FieldsList"])
        return e.size_at_distance(field_value(f["InField"],point),f)
    def run(name):
        assert name == "MeshSizeFieldView" and plugin["Component"] == 0
        view = list(views)[plugin["View"]]; tag = plugin["MeshSizeField"]
        flat = views[view]["flat"]
        for i in range(views[view]["count"]):
            flat[4*i+3] = field_value(tag,flat[4*i:4*i+3]) + state["size_error" if fields[tag]["kind"] == "Threshold" else "distance_error"]
        state["probe_calls"].append(tag)
        return view
    native = SimpleNamespace(model=SimpleNamespace(mesh=SimpleNamespace(field=api)),
        option=SimpleNamespace(setNumber=lambda k,v:options.__setitem__(k,v),getNumber=lambda k:options[k]),
        view=SimpleNamespace(getTags=lambda:list(views),add=view_add,addListData=add_data,
            getIndex=lambda t:list(views).index(t),getListData=lambda t:([views[t]["kind"]],[views[t]["count"]],[views[t]["flat"]]),remove=lambda t:views.pop(t)),
        plugin=SimpleNamespace(setNumber=lambda name,k,v:plugin.__setitem__(k,v),run=run))
    return native,state,fields,views


def test_owner_coverage_and_finite_segment_distance_not_filled_box():
    r = request()
    assert len(r["segments"]) == 8
    assert [(s["owner"],s["side"]) for s in r["segments"]] == [(i,k) for i in range(2) for k in range(4)]
    assert r["expressions"][:4] == r["expressions"][4:]
    # At the center of the filled footprint, distance to the perimeter is .5.
    assert min(e.distance_squared([1.5,1.5],s) for s in r["segments"]) == Fraction(1,4)
    assert e.size_at_distance(.5,r["threshold"]) > POLICY["near_size_mm"]
    # Beyond an endpoint the finite-segment distance is Euclidean, not a line.
    s = r["segments"][0]
    assert e.distance_squared([4.,6.],s) == 25
    assert evaluate(r["expressions"][0],[4.,6.]) == 5


def test_expression_matches_independent_exact_projection_on_tiny_grid():
    r = request()
    for s,text in zip(r["segments"],r["expressions"]):
        for x in (-3.,.5,1.,1.5,2.,2.5,7.):
            for y in (-4.,.5,1.,1.5,2.,3.,8.):
                assert evaluate(text,[x,y]) == pytest.approx(math.sqrt(float(e.distance_squared([x,y],s))),rel=1e-15,abs=1e-15)


def test_one_ulp_coordinates_survive_literals_and_owner_projections():
    boxes = copy.deepcopy(BOXES)
    boxes[1][0] = math.nextafter(1.,2.)
    r = e.sizing_policy(boxes,POLICY,CFG,MESH)
    assert r["expressions"][0] != r["expressions"][4]
    assert evaluate(r["expressions"][4],[1.,1.5]) == boxes[1][0]-1 > 0
    assert e.literal(-1e-12) == "(-9.9999999999999998e-13)"


def test_threshold_plateau_transition_and_far_value():
    t = request()["threshold"]
    assert e.size_at_distance(0.,t) == e.size_at_distance(t["DistMin"],t) == .1
    assert e.size_at_distance(t["DistMax"],t) == e.size_at_distance(10.,t) == 1.
    assert e.size_at_distance((t["DistMin"]+t["DistMax"])/2,t) == pytest.approx(.55)


def test_native_effective_fields_and_independent_probe_scalar_review():
    native,state,fields,views = fake_fields()
    sizing = e.apply_sizing(native,request())
    assert len(fields) == 10 and state["background"] == sizing["background_tag"]
    report = e.probe(native,BOXES,DOMAIN,sizing,CFG)
    assert e.validate_probe(report,sizing,CFG)
    assert state["probe_calls"] == [sizing["minimum_tag"],sizing["background_tag"]] and not views
    assert any(r["expected_distance_mm"] == 0 for r in report["points"])
    assert any(r["expected_size_mm"] == 1. for r in report["points"])
    assert any(.1 < r["expected_size_mm"] < 1. for r in report["points"])
    assert not report["mesh_generated"] and not report["probe_is_mesh_accuracy_test"]


@pytest.mark.parametrize("damage",["distance_error","size_error"])
def test_bad_native_probe_values_preserved_then_rejected(damage):
    native,state,_,views = fake_fields()
    sizing = e.apply_sizing(native,request())
    state[damage] = .01
    report = e.probe(native,BOXES,DOMAIN,sizing,CFG)
    assert report["points"] and not views
    with pytest.raises(ValueError,match="oracle"): e.validate_probe(report,sizing,CFG)


@pytest.mark.parametrize("damage",["extra_field","option","expression","threshold","kind","minimum"])
def test_native_readback_and_fresh_session_fail_closed(damage):
    native,_,fields,_ = fake_fields()
    api = native.model.mesh.field
    if damage == "extra_field": api.add("surprise")
    if damage == "option": native.option.getNumber = lambda k:-999
    if damage == "expression": api.getString = lambda *a:"wrong"
    if damage == "threshold": api.getNumber = lambda *a:-999
    if damage == "kind": api.getType = lambda *a:"wrong"
    if damage == "minimum": api.getNumbers = lambda *a:[]
    with pytest.raises(ValueError): e.apply_sizing(native,request())


@pytest.mark.parametrize("damage",["source","hash","count","expected","native","rational","scope","tolerance","point","duplicate"])
def test_probe_metadata_mutations_rejected(damage):
    native,_,_,_ = fake_fields()
    sizing = e.apply_sizing(native,request())
    report = e.probe(native,BOXES,DOMAIN,sizing,CFG)
    if damage == "source": report["sizing_sha256"] = "0"*64
    if damage == "hash": report["point_set_sha256"] = "0"*64
    if damage == "count": report["point_count"] += 1
    if damage == "expected": report["points"][0]["expected_distance_mm"] += .1
    if damage == "native": report["points"][0]["native_size_mm"] = math.nan
    if damage == "rational": report["points"][0]["exact_minimum_distance_squared_mm2"]["numerator"] = "-1"
    if damage == "scope": report["probe_is_mesh_accuracy_test"] = True
    if damage == "tolerance": report["rtol"] = 1.
    if damage == "point": report["points"][0]["point_mm"][2] = 1.
    if damage == "duplicate": report["points"][1]["point_mm"] = list(report["points"][0]["point_mm"])
    if damage in ("point","duplicate"): report["point_set_sha256"] = sha256_json([r["point_mm"] for r in report["points"]])
    with pytest.raises(ValueError): e.validate_probe(report,sizing,CFG)


@pytest.mark.parametrize("damage",["box","nonfinite","plateau","transition","segment_cap","expression_cap","probe_cap"])
def test_invalid_or_unbounded_definition_fails(damage):
    boxes,cfg,mesh = copy.deepcopy(BOXES),copy.deepcopy(CFG),dict(MESH)
    if damage == "box": boxes[0][1] = boxes[0][0]
    if damage == "nonfinite": boxes[0][0] = math.nan
    if damage == "plateau": cfg["edge_plateau_half_width_mm"] = 0
    if damage == "transition": mesh["transition_thickness_mm"] = 0
    if damage == "segment_cap": cfg["segment_count_max"] = 1
    if damage == "expression_cap": cfg["expression_bytes_max"] = 1
    if damage == "probe_cap": cfg["probe_points_max"] = 1
    with pytest.raises(ValueError):
        r = e.sizing_policy(boxes,POLICY,cfg,mesh)
        e.probe_points(boxes,DOMAIN,r,cfg)


@pytest.mark.parametrize("damage",["requested","expression","threshold","collision","boolean","zero","extra"])
def test_effective_sizing_metadata_fails_closed(damage):
    native,_,_,_ = fake_fields()
    expected = request()
    sizing = e.apply_sizing(native,expected)
    assert e.validate_sizing(sizing,expected)
    sizing = copy.deepcopy(sizing)
    if damage == "requested": sizing["requested"]["threshold"]["DistMax"] += 1
    if damage == "expression": sizing["distance_fields"][0]["expression"] = "x"
    if damage == "threshold": sizing["threshold_settings"]["InField"] += 1
    if damage == "collision": sizing["background_tag"] = sizing["minimum_tag"]
    if damage == "boolean": sizing["background_tag"] = True
    if damage == "zero": sizing["background_tag"] = 0
    if damage == "extra": sizing["unexpected"] = True
    with pytest.raises(ValueError): e.validate_sizing(sizing,expected)


@pytest.mark.parametrize("damage",["returned_view","extra_view","kind","count","arrays","length","coordinate","nonfinite"])
def test_malformed_native_probe_fails_and_removes_its_view(damage):
    native,_,_,views = fake_fields()
    sizing = e.apply_sizing(native,request())
    run = native.plugin.run
    def broken(name):
        tag = run(name)
        if damage == "returned_view": return tag+1
        if damage == "extra_view": views[tag+1] = {}
        if damage == "kind": views[tag]["kind"] = "VP"
        if damage == "count": views[tag]["count"] += 1
        if damage == "length": views[tag]["flat"].pop()
        if damage == "coordinate": views[tag]["flat"][0] += 1
        if damage == "nonfinite": views[tag]["flat"][3] = math.nan
        return tag
    native.plugin.run = broken
    if damage == "arrays": native.view.getListData = lambda t:(["SP"],[1],[])
    with pytest.raises(ValueError): e.evaluate_native(native,sizing["minimum_tag"],[[0.,0.,0.]])
    assert 1 not in views


def test_probe_rejects_preexisting_view_without_overwriting_it():
    native,_,_,views = fake_fields()
    sizing = e.apply_sizing(native,request())
    views[99] = {"preserved":True}
    with pytest.raises(ValueError,match="existing views"):
        e.evaluate_native(native,sizing["minimum_tag"],[[0.,0.,0.]])
    assert views == {99:{"preserved":True}}
