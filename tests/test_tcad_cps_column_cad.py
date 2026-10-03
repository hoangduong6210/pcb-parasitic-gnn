"""Hand-built planar ring/square metadata and fake readers; no native CAD."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "code/solvers"))
import tcad_cps_column_cad as cad

CFG = json.loads((ROOT / "protocols/tcad_cps_dielectric_cad_v1.json").read_text())["geometry_checks"]
OPTIONS = {"Geometry.Tolerance":1e-8,"Geometry.OCCParallel":0}
BOXES = [[1.,2.,1.,2.,1.,2.],[1.,2.,1.,2.,3.,4.]]
DOMAIN = [0.,3.,0.,3.,0.,5.]
OUTER = [(0.,0.),(3.,0.),(3.,3.),(0.,3.)]
INNER = [(1.,1.),(2.,1.),(2.,2.),(1.,2.)]


def snapshot_fixture(surfaces,merge=True):
    rows = {d:{} for d in range(3)}
    points,edges = {},{}
    def entity(dim,tag,xy,area,boundary):
        rows[dim][tag] = {"tag":tag,"kind":("Point","Line","Plane")[dim],
            "bbox_mm":[min(p[0] for p in xy),max(p[0] for p in xy),min(p[1] for p in xy),max(p[1] for p in xy),0.,0.],
            "boundary":sorted(boundary),"upward":[],"measure_native":area,
            "point_mm":[*xy[0],0.] if dim == 0 else None}
    def point(xy):
        if xy not in points:
            points[xy] = len(rows[0])+1
            entity(0,points[xy],[xy],None,[])
        return points[xy]
    for tag,(cycles,area) in enumerate(surfaces,1):
        if not merge: points,edges = {},{}
        boundary = []
        for cycle in cycles:
            for a,b in zip(cycle,cycle[1:]+cycle[:1]):
                key = tuple(sorted((point(a),point(b))))
                if key not in edges:
                    edges[key] = len(rows[1])+1
                    entity(1,edges[key],[a,b],abs(a[0]-b[0])+abs(a[1]-b[1]),list(key))
                boundary.append(edges[key])
        entity(2,tag,[p for cycle in cycles for p in cycle],area,boundary)
    for dim in (1,2):
        for tag,row in rows[dim].items():
            for child in row["boundary"]: rows[dim-1][child]["upward"].append(tag)
    return {**{str(d):list(rows[d].values()) for d in range(3)},"3":[]}


def report_fixture():
    return {"schema":cad.SCHEMA,"canonical_boxes_mm":copy.deepcopy(BOXES),"domain_box_mm":list(DOMAIN),
        "input_surface_tags":[1,2,3],"fragment_output_surfaces":[1,2],"fragment_map":[[1,2],[2],[2]],
        "before":snapshot_fixture([([OUTER],9.),([INNER],1.),([INNER],1.)],merge=False),
        "after":snapshot_fixture([([OUTER,INNER],8.),([INNER],1.)]),"options":dict(OPTIONS)}


def review(report=None):
    return cad.review_report(report or report_fixture(),BOXES,DOMAIN,CFG,OPTIONS)


def fake_reader(value):
    rows = {int(d):{r["tag"]:r for r in records} for d,records in value.items()}
    def bbox(dim,tag):
        b = rows[dim][tag]["bbox_mm"]
        return [b[i] for i in (0,2,4,1,3,5)]
    model = SimpleNamespace(getEntities=lambda dim:[(dim,t) for t in rows[dim]],
        getBoundingBox=bbox,getType=lambda d,t:rows[d][t]["kind"],
        getBoundary=lambda entities,**kw:[(d-1,k) for d,t in entities for k in rows[d][t]["boundary"]],
        getAdjacencies=lambda d,t:(rows[d][t]["upward"],rows[d][t]["boundary"]),
        getValue=lambda d,t,u:rows[d][t]["point_mm"],occ=SimpleNamespace(getMass=lambda d,t:rows[d][t]["measure_native"]))
    return SimpleNamespace(model=model)


def test_complete_duplicate_projection_metadata_and_closed_flags():
    value = report_fixture()
    assert cad.snapshot(fake_reader(value["before"]),CFG) == value["before"]
    assert cad.snapshot(fake_reader(value["after"]),CFG) == value["after"]
    summary = review(value)
    assert summary["ownership"] == {"1":[],"2":[0,1]}
    assert summary["entity_counts"] == {"0":8,"1":8,"2":2}
    assert summary["planar_cad_contract_passed"] is True
    assert summary["planar_mesh_validated"] is False
    assert all(summary[k] is False for k in cad.CLOSED)
    assert review(json.loads(json.dumps(value))) == summary


@pytest.mark.parametrize("mutation", ["option","bool_option","geometry","inputs","input_order","input_bbox","input_area","input_corner",
    "map_missing","map_coverage","map_owner","outputs","native_area","unknown_point","incidence","orphan","open_loop",
    "kind","nonplanar","volume","extra","nan","short","diagonal","outer_length","duplicate_tag","unknown_field"])
def test_corrupted_provenance_geometry_and_topology_fail(mutation):
    r = report_fixture()
    if mutation == "option": r["options"]["Geometry.Tolerance"] = 1.
    if mutation == "bool_option": r["options"]["Geometry.OCCParallel"] = False
    if mutation == "geometry": r["canonical_boxes_mm"][0][0] = .5
    if mutation == "inputs": r["input_surface_tags"][1] = 1
    if mutation == "input_order": r["input_surface_tags"] = [2,1,3]
    if mutation == "input_bbox": r["before"]["2"][0]["bbox_mm"][1] = 4.
    if mutation == "input_area": r["before"]["2"][0]["measure_native"] = 8.
    if mutation == "input_corner": r["before"]["0"][0]["point_mm"][0] = .1
    if mutation == "map_missing": r["fragment_map"].pop()
    if mutation == "map_coverage": r["fragment_map"][0] = [1]
    if mutation == "map_owner": r["fragment_map"][1] = [1]
    if mutation == "outputs": r["fragment_output_surfaces"] = [1]
    if mutation == "native_area": r["after"]["2"][0]["measure_native"] = 7.
    if mutation == "unknown_point": r["after"]["1"][0]["boundary"][0] = 999
    if mutation == "incidence": r["after"]["0"][0]["upward"].pop()
    if mutation == "orphan": r["after"]["1"][0]["upward"] = []
    if mutation == "open_loop": r["after"]["2"][0]["boundary"].pop()
    if mutation == "kind": r["after"]["1"][0]["kind"] = "BSpline"
    if mutation == "nonplanar": r["after"]["0"][0]["point_mm"][2] = 1e-15
    if mutation == "volume": r["after"]["3"] = [{"tag":1}]
    if mutation == "extra": r["reference_qualified"] = True
    if mutation == "nan": r["after"]["2"][0]["measure_native"] = float("nan")
    if mutation == "short": r["after"]["0"][1]["point_mm"] = [1e-8,0.,0.]
    if mutation == "diagonal": r["after"]["0"][1]["point_mm"] = [3.,.1,0.]
    if mutation == "outer_length": r["after"]["1"][0]["measure_native"] = 2.
    if mutation == "duplicate_tag": r["after"]["2"].append(copy.deepcopy(r["after"]["2"][0]))
    if mutation == "unknown_field": r["after"]["0"][0]["repaired"] = True
    with pytest.raises(ValueError): review(r)


def test_independent_native_readers_must_agree():
    fake = fake_reader(report_fixture()["after"])
    fake.model.getAdjacencies = lambda *a:([1],[])
    with pytest.raises(ValueError,match="incidence"): cad.snapshot(fake,CFG)


def test_capture_rejects_native_volumes_and_entity_cap():
    value = report_fixture()["after"]
    value["3"] = [{"tag":9}]
    with pytest.raises(ValueError,match="volume"): cad.snapshot(fake_reader(value),CFG)
    with pytest.raises(ValueError,match="cap"): cad.snapshot(fake_reader(report_fixture()["after"]),{**CFG,"entity_count_max_per_dimension":1})
