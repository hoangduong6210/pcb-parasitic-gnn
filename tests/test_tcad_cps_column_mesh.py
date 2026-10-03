"""Tiny 16-node planar grid/fake native reader; no actual CAD or mesh generation."""
import copy
from fractions import Fraction as F
import itertools
from types import SimpleNamespace

import numpy as np
import pytest

from test_tcad_cps_column_cad import cad,CFG,OPTIONS,BOXES,DOMAIN,report_fixture,fake_reader
import tcad_cps_column_mesh as mesh

LIMITS = {"planar_nodes_max":100,"planar_triangles_max":100,"planar_lines_max":100}


def packet_fixture():
    xyz = np.array([(float(x),float(y),0.) for y in range(4) for x in range(4)])
    snapshot = report_fixture()["after"]
    dimensions,entities = [],[]
    for point in xyz:
        match = next((r["tag"] for r in snapshot["0"] if np.array_equal(point,r["point_mm"])),None)
        if match:
            dimensions.append(0); entities.append(match)
        else:
            for row in snapshot["1"]:
                b = row["bbox_mm"]
                if b[0] <= point[0] <= b[1] and b[2] <= point[1] <= b[3]:
                    dimensions.append(1); entities.append(row["tag"]); break
            else:
                dimensions.append(2); entities.append(2 if 1 < point[0] < 2 and 1 < point[1] < 2 else 1)
    triangles,faces = [],[]
    for y,x in itertools.product(range(3),repeat=2):
        a,b,c,d = 1+4*y+x,2+4*y+x,6+4*y+x,5+4*y+x
        triangles.extend([[a,b,c],[a,c,d]])
        faces.extend([2 if (x,y) == (1,1) else 1]*2)
    lines,curves = [],[]
    for row in snapshot["1"]:
        b = row["bbox_mm"]
        selected = [i+1 for i,p in enumerate(xyz) if b[0] <= p[0] <= b[1] and b[2] <= p[1] <= b[3]]
        selected.sort(key=lambda i:tuple(xyz[i-1]))
        for a,b in zip(selected,selected[1:]):
            lines.append([a,b]); curves.append(row["tag"])
    return {"node_tags":np.arange(1,17,dtype=np.int64),"coordinates_mm":xyz,
        "node_dimension":np.array(dimensions,dtype=np.int64),"node_entity":np.array(entities,dtype=np.int64),
        "triangle_tags":np.arange(1000,1018,dtype=np.int64),"triangle_nodes":np.array(triangles,dtype=np.int64),
        "triangle_surfaces":np.array(faces,dtype=np.int64),"line_tags":np.arange(100,100+len(lines),dtype=np.int64),
        "line_nodes":np.array(lines,dtype=np.int64),"line_curves":np.array(curves,dtype=np.int64)}


def audit(packet=None):
    return mesh.audit_packet(packet if packet is not None else packet_fixture(),report_fixture(),BOXES,DOMAIN,CFG,OPTIONS,LIMITS)


def fake_native(packet=None):
    p = packet if packet is not None else packet_fixture()
    native = fake_reader(report_fixture()["after"])
    def get_nodes(dim,tag,**kwargs):
        mask = np.ones(len(p["node_tags"]),dtype=bool) if dim == -1 else ((p["node_dimension"] == dim)&(p["node_entity"] == tag))
        return p["node_tags"][mask],p["coordinates_mm"][mask].reshape(-1),[]
    def get_elements(dim,tag):
        prefix,owner,kind = ("line","curves",1) if dim == 1 else ("triangle","surfaces",2)
        mask = np.ones(len(p[prefix+"_tags"]),dtype=bool) if tag == -1 else p[prefix+"_"+owner] == tag
        return np.array([kind],dtype=np.int32),[p[prefix+"_tags"][mask]],[p[prefix+"_nodes"][mask].reshape(-1)]
    native.model.mesh = SimpleNamespace(getNodes=get_nodes,getElements=get_elements)
    return native


def test_complete_hand_constructed_packet_and_native_capture():
    packet = packet_fixture()
    captured = mesh.read_native(fake_native(packet),report_fixture()["after"],LIMITS)
    assert all(np.array_equal(packet[k],captured[k]) for k in packet)
    r = audit(captured)
    assert r["planar_nodes"] == 16 and r["planar_triangles"] == 18 and r["planar_lines"] == 16
    assert r["groups"] == [{"owners":[],"triangles":16},{"owners":[0,1],"triangles":2}]
    assert r["raw_clockwise_triangles"] == 0 and r["planar_mesh_validated"] is True
    assert r["minimum_exact_triangle_area_mm2"] == {"numerator":"1","denominator":"2"}
    assert all(cad.unpack(v) == 0 for v in r["ownership_leakage_upper_bound_mm2"])
    assert r["native_quality_claimed"] is False and all(r[k] is False for k in mesh.CLOSED)


def test_clockwise_raw_triangles_are_preserved_while_derived_view_is_oriented():
    p = packet_fixture()
    p["triangle_nodes"][0,[1,2]] = p["triangle_nodes"][0,[2,1]]
    before = {k:v.copy() for k,v in p.items()}
    digest = mesh.packet_sha256(p)
    r = audit(p)
    assert r["raw_clockwise_triangles"] == 1 and r["raw_connectivity_changed"] is False
    assert r["packet_sha256"] == digest
    assert all(np.array_equal(p[k],before[k]) for k in p)


def test_record_order_normalization_not_connectivity_or_coordinate_repair():
    p = packet_fixture()
    for names in (("node_tags","coordinates_mm","node_dimension","node_entity"),
                  ("triangle_tags","triangle_nodes","triangle_surfaces"),("line_tags","line_nodes","line_curves")):
        for name in names: p[name] = p[name][::-1]
    assert audit(p) == audit()


@pytest.mark.parametrize("mutation", ["duplicate_node_tag","duplicate_coordinate","node_class","point_class","unknown_node","nonplanar","nan",
    "orphan","zero_area","duplicate_triangle","triangle_face","line_curve","missing_line","extra_line","reused_element",
    "line_float","dim_bool","missing_field","count_cap","point_position"])
def test_bad_mesh_identity_geometry_incidence_and_coverage_rejected(mutation):
    p,limits = packet_fixture(),dict(LIMITS)
    if mutation == "duplicate_node_tag": p["node_tags"][1] = p["node_tags"][0]
    if mutation == "duplicate_coordinate": p["coordinates_mm"][-1] = p["coordinates_mm"][0]
    if mutation == "node_class": p["node_entity"][0] = 999
    if mutation == "point_class": p["node_dimension"][0] = 2
    if mutation == "unknown_node": p["triangle_nodes"][0][0] = 99
    if mutation == "nonplanar": p["coordinates_mm"][0][2] = 1e-15
    if mutation == "nan": p["coordinates_mm"][0][0] = float("nan")
    if mutation == "orphan":
        for name,value in (("node_tags",[17]),("coordinates_mm",[[1.5,1.5,0.]]),("node_dimension",[2]),("node_entity",[2])):
            p[name] = np.concatenate((p[name],np.array(value,dtype=p[name].dtype)))
    if mutation == "zero_area": p["triangle_nodes"][0] = [1,2,3]
    if mutation == "duplicate_triangle": p["triangle_nodes"][1] = p["triangle_nodes"][0]
    if mutation == "triangle_face": p["triangle_surfaces"][0] = 2
    if mutation == "line_curve": p["line_curves"][0] = 2
    if mutation == "missing_line":
        for name in ("line_tags","line_nodes","line_curves"): p[name] = p[name][1:]
    if mutation == "extra_line": p["line_nodes"][0] = [1,16]
    if mutation == "reused_element": p["line_tags"][0] = p["triangle_tags"][0]
    if mutation == "line_float": p["line_nodes"] = p["line_nodes"].astype(float)
    if mutation == "dim_bool": p["node_dimension"] = p["node_dimension"].astype(bool)
    if mutation == "missing_field": p.pop("line_tags")
    if mutation == "count_cap": limits["planar_triangles_max"] = 17
    if mutation == "point_position": p["coordinates_mm"][0][0] = 1e-4
    with pytest.raises(ValueError): mesh.audit_packet(p,report_fixture(),BOXES,DOMAIN,CFG,OPTIONS,limits)


def test_centroid_alone_cannot_certify_triangle_ownership():
    p = packet_fixture()
    # The centroid (1,1) is outside the open inner square, but half a square
    # millimetre of this triangle overlaps its interior. Exact clipping catches it.
    p["triangle_nodes"][0] = [1,4,13]
    with pytest.raises(ValueError,match="leakage"): audit(p)


@pytest.mark.parametrize("triangle,box,area", [
    ([(0,0),(3,0),(0,3)],[1.,2.,1.,2.],F(1,2)),
    ([(0,0),(1,0),(0,1)],[2.,3.,2.,3.],F(0)),
    ([(0,0),(1,0),(0,1)],[-1.,2.,-1.,2.],F(1,2)),
    ([(0,0),(3,0),(0,1)],[1.,2.,0.,1.],F(1,2))])
@pytest.mark.parametrize("reverse", [False,True])
def test_exact_clipping_is_independent_of_vertex_orientation(triangle,box,area,reverse):
    points = [[F(x),F(y)] for x,y in triangle]
    assert mesh.clipped_area(points[::-1] if reverse else points,box) == area


@pytest.mark.parametrize("value", [F(0),F(1,3),F(1,7),F(1,2**100),F(19,11)])
def test_dyadic_leakage_accumulation_is_conservative(value):
    bound = mesh.leakage_upper_bound(value)
    assert value <= bound < value+F(1,2**80)
    assert bound.denominator & (bound.denominator-1) == 0


@pytest.mark.parametrize("links,boundary", [
    ({0:[(1,2),(2,3),(3,1)]},set()),({0:[(1,2),(2,3)]},{0})])
def test_valid_vertex_links(links,boundary):
    mesh.check_vertex_links(links,boundary)


@pytest.mark.parametrize("pairs,boundary", [
    ([(1,2),(2,3),(3,1),(4,5),(5,6),(6,4)],set()),
    ([(1,2),(2,3),(2,4)],{0}), ([(1,2),(2,3),(3,1)],{0}),
    ([(1,2),(2,3)],set()), ([(1,2),(1,2)],set()), ([(1,1)],{0})])
def test_pinched_or_nonmanifold_vertex_links_fail(pairs,boundary):
    with pytest.raises(ValueError): mesh.check_vertex_links({0:pairs},boundary)


@pytest.mark.parametrize("mutation", ["coordinate","node_coverage","element_coverage","wrong_type","float_type","duplicate_entity","cad_change"])
def test_independent_native_array_reads_must_agree(mutation):
    p = packet_fixture()
    native = fake_native(p)
    nodes,elements,entities = native.model.mesh.getNodes,native.model.mesh.getElements,native.model.getEntities
    def get_nodes(dim,tag,**kw):
        ids,xyz,u = nodes(dim,tag,**kw)
        if mutation == "coordinate" and dim == 0 and tag == 1:
            xyz = xyz.copy(); xyz[0] += .1
        if mutation == "node_coverage" and dim == 0 and tag == 1: ids,xyz = ids[:0],xyz[:0]
        return ids,xyz,u
    def get_elements(dim,tag):
        kind,ids,nodes = elements(dim,tag)
        if mutation == "element_coverage" and dim == 2 and tag == 2:
            ids,nodes = [ids[0][1:]],[nodes[0][3:]]
        if mutation == "wrong_type": kind = np.array([9],dtype=np.int32)
        if mutation == "float_type": kind = kind.astype(float)
        if mutation == "duplicate_entity" and dim == 2 and tag == 2: return elements(2,1)
        return kind,ids,nodes
    native.model.mesh.getNodes,native.model.mesh.getElements = get_nodes,get_elements
    if mutation == "cad_change": native.model.getEntities = lambda d:entities(d)+([(2,99)] if d == 2 else [])
    with pytest.raises(ValueError): mesh.read_native(native,report_fixture()["after"],LIMITS)
