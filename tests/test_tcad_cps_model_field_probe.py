"""Tiny stateful fake-native tests; no actual CAD/native initialization."""
import copy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/solvers"),str(ROOT / "code/core"),str(ROOT / "code/experiments/proofs")]
import tcad_cps_model_field_probe as a
import tcad_cps_edge_sizing as e
from test_tcad_cps_edge_sizing import fake_fields,request,evaluate as formula


def fake_native(*, original="main"):
    native,_,fields,_ = fake_fields()
    models,views,plugin = {},{},{}
    state = {"current":"","view_counter":-1,"initialized":False,"failure":None,"error":0.,"plugin_calls":[]}
    def add(name):
        assert name not in models
        models[name] = {"entities":[],"tags":[],"xyz":[],"elements":[],"rectangles":[]}
        state["current"] = name
    if original is not None: add(original)
    def initialize(*args,**kwargs):
        state["initialized"] = True
        add("")
    def finalize(): state["initialized"] = False
    native.initialize = Mock(side_effect=initialize)
    native.finalize = Mock(side_effect=finalize)
    native.isInitialized = lambda:state["initialized"]
    native.option.getString = lambda key:"synthetic fake model data, not actual native proof"
    def current(): return models[state["current"]]
    def set_current(name):
        assert name in models
        state["current"] = name
    def remove():
        assert state["current"] == a.TEMP_MODEL
        if state["failure"] != "cleanup": del models[state["current"]]
        state["current"] = list(models)[0]
    def discrete(dim,tag): current()["entities"].append([dim,tag]); return tag
    def nodes(dim,tag,tags,xyz):
        if state["failure"] == "insert": raise ValueError("synthetic insert failure")
        current().update(tags=list(tags),xyz=list(xyz))
    def elements(tag,kind,tags,nodes):
        assert tag == 1 and kind == 15 and tags == nodes
        current()["elements"] = list(tags)
    def get_elements():
        row = current()
        return ([15],[list(row["elements"])],[list(row["elements"])]) if row["elements"] else ([],[],[])
    def rectangle(*coords):
        row = current(); tag = len(row["rectangles"])+1
        row["rectangles"].append(list(coords)); row["entities"].append([2,tag]); return tag
    native.model.add,native.model.remove = add,remove
    native.model.getCurrent,native.model.setCurrent = lambda:state["current"],set_current
    native.model.list = lambda:list(models)
    native.model.getEntities = lambda *args:copy.deepcopy(current()["entities"])
    native.model.addDiscreteEntity = discrete
    native.model.occ = SimpleNamespace(addRectangle=rectangle,synchronize=Mock())
    mesh = native.model.mesh
    mesh.addNodes,mesh.addElementsByType = nodes,elements
    mesh.getNodes = lambda:(list(current()["tags"]),list(current()["xyz"]),[])
    mesh.getElements = get_elements
    mesh.generate = Mock(side_effect=AssertionError("mesh.generate is forbidden"))
    def add_view(name):
        state["view_counter"] += 1
        tag = state["view_counter"]; views[tag] = {}; return tag
    def add_data(tag,step,model,kind,tags,data,**kwargs):
        assert step == 0 and kind == "NodeData" and models[model]["elements"] == tags
        views[tag] = {"model":model,"kind":kind,"tags":list(tags),"data":copy.deepcopy(data),"time":0.,"components":1}
    def get_data(tag,step):
        r = views[tag]
        return r["kind"],list(r["tags"]),copy.deepcopy(r["data"]),r["time"],r["components"]
    def field_value(tag,point):
        f = fields[tag]
        if f["kind"] == "MathEval": return formula(f["F"],point)
        if f["kind"] == "Min": return min(field_value(k,point) for k in f["FieldsList"])
        return e.size_at_distance(field_value(f["InField"],point),f)
    def run(name):
        assert name == "MeshSizeFieldView" and state["current"] != a.TEMP_MODEL
        state["plugin_calls"].append(state["current"])
        if state["failure"] == "plugin": raise ValueError("synthetic plugin failure")
        tag = list(views)[plugin["View"]]; row = views[tag]; model = models[row["model"]]
        if not model["entities"] or not model["elements"]:
            raise ValueError("Cannot get entity from this view")
        for i in range(len(row["tags"])):
            row["data"][i] = [field_value(plugin["MeshSizeField"],model["xyz"][3*i:3*i+3])+state["error"]]
        damage = state["failure"]
        if damage == "nonfinite": row["data"][0][0] = math.nan
        if damage == "kind": row["kind"] = "ElementData"
        if damage == "tags": row["tags"][0] += 100
        if damage == "components": row["components"] = 3
        if damage == "time": row["time"] = 1.
        if damage == "shape": row["data"][0] = []
        if damage == "coordinate": model["xyz"][0] += 1.
        if damage == "extra_view": views[tag+100] = {}
        if damage == "original": current()["tags"].append(999)
        if damage == "returned": return tag+1
        return tag
    native.view = SimpleNamespace(add=add_view,getTags=lambda:list(views),remove=lambda tag:views.pop(tag),
        addModelData=add_data,getModelData=get_data,getIndex=lambda tag:list(views).index(tag))
    native.plugin = SimpleNamespace(setNumber=lambda name,key,value:plugin.__setitem__(key,value),run=run)
    state.update(models=models,views=views,fields=fields)
    native.fixture_state = state
    return native,state


def probe_fixture():
    native,state = fake_native()
    sizing = e.apply_sizing(native,request())
    events = {}
    def preserve(name,row):
        assert name not in events
        events[name] = copy.deepcopy(row)
    return native,state,sizing,events,preserve


def test_isolated_model_uses_original_field_and_restores_every_owned_object():
    native,state,sizing,events,preserve = probe_fixture()
    before = copy.deepcopy(state["models"])
    values = a.evaluate(native,sizing["minimum_tag"],[[1.,1.,0.],[1.5,1.5,0.],[4.,6.,0.]],preserve)
    assert values == [0.,.5,math.sqrt(20.)]
    assert list(events) == list(a.EVENTS)
    assert state["models"] == before and state["current"] == "main" and not state["views"]
    assert state["plugin_calls"] == ["main"]
    assert events["view_after"]["view_tag"] == 0
    native.model.mesh.generate.assert_not_called()


@pytest.mark.parametrize("damage",["insert","plugin","nonfinite","kind","tags","components","time","shape","coordinate","returned"])
def test_failure_preserves_raw_data_and_restores_original_without_retry(damage):
    native,state,sizing,events,preserve = probe_fixture()
    state["failure"] = damage
    with pytest.raises(ValueError): a.evaluate(native,sizing["background_tag"],[[1.,1.,0.],[4.,6.,0.]],preserve)
    assert state["current"] == "main" and list(state["models"]) == ["main"] and not state["views"]
    assert events["cleanup"] == events["request"]["before"]
    if damage not in ("insert","plugin"): assert "view_after" in events
    if damage == "nonfinite": assert events["view_after"]["data"]["values"][0][0] == {"nonfinite":"nan"}
    assert len(state["plugin_calls"]) <= 1


@pytest.mark.parametrize("damage",["cleanup","extra_view"])
def test_cleanup_mismatch_is_not_hidden_or_fixed_by_deleting_unowned_state(damage):
    native,state,sizing,events,preserve = probe_fixture()
    state["failure"] = damage
    with pytest.raises(ValueError,match="restoration"):
        a.evaluate(native,sizing["minimum_tag"],[[0.,0.,0.]],preserve)
    assert state["current"] == "main" and events["cleanup"] != events["request"]["before"]
    if damage == "extra_view": assert 100 in state["views"]
    else: assert a.TEMP_MODEL in state["models"]


@pytest.mark.parametrize("damage",["entity","elements","coordinates","initial_data"])
def test_invalid_scaffold_or_initial_data_is_preserved_before_gate(damage):
    native,state,sizing,events,preserve = probe_fixture()
    if damage == "entity": native.model.addDiscreteEntity = lambda *args:1
    if damage == "elements": native.model.mesh.addElementsByType = lambda *args:None
    if damage == "coordinates": native.model.mesh.getNodes = lambda:([1],[99.,0.,0.],[])
    if damage == "initial_data": native.view.getModelData = lambda *args:("NodeData",[1],[[math.nan]],0.,1)
    with pytest.raises(ValueError): a.evaluate(native,sizing["minimum_tag"],[[0.,0.,0.]],preserve)
    assert "scaffold" in events and "cleanup" in events and not state["plugin_calls"]
    if damage == "initial_data": assert events["view_before"]["values"][0][0] == {"nonfinite":"nan"}
    assert state["current"] == "main" and not state["views"] and a.TEMP_MODEL not in state["models"]


@pytest.mark.parametrize("damage",["existing_model","existing_view","unknown_field","duplicate_points","nonfinite_point","zero_field"])
def test_invalid_start_never_mutates_session(damage):
    native,state,sizing,events,preserve = probe_fixture()
    tag,points = sizing["minimum_tag"],[[0.,0.,0.]]
    if damage == "existing_model": state["models"][a.TEMP_MODEL] = {"preserved":True}
    if damage == "existing_view": state["views"][123] = {"preserved":True}
    if damage == "unknown_field": tag = 999
    if damage == "duplicate_points": points *= 2
    if damage == "nonfinite_point": points[0][0] = math.nan
    if damage == "zero_field": tag = 0
    before = copy.deepcopy(state)
    with pytest.raises(ValueError): a.evaluate(native,tag,points,preserve)
    assert state == before and not events
