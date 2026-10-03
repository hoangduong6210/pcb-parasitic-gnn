"""Tiny synthetic columns only; no native initialization or real-layout replay."""
import copy
from collections import Counter
from fractions import Fraction
import itertools

import numpy as np
import pytest

from test_tcad_cps_column_planning import plan, POLICY, SETTINGS, CAPS
from test_tcad_cps_column_mesh import packet_fixture, report_fixture, BOXES, DOMAIN, CFG, OPTIONS
from test_tcad_cps_dielectric_mesh_audit import fixture as boundary_fixture, CFG as MESH_CFG
from tcad_cps_column_contract import prism_indices
import tcad_cps_column_planning as planning
import tcad_cps_column_volume_geometry as geometry
import tcad_cps_column_volume_audit as audit

LIMITS = {**CAPS,"mesh_triangles_max":1000}


def rectangle_topology(after):
    """Independent exact rectangle corners/edges for the synthetic CAD faces."""
    after = copy.deepcopy(after)
    points,edges = {},{}
    for face in after["2"]:
        b = face["bbox_mm"]
        corners = list(itertools.product(*[sorted(set(b[k:k+2])) for k in (0,2,4)]))
        face["boundary"] = []
        for a,c in itertools.combinations(corners,2):
            if sum(x != y for x,y in zip(a,c)) != 1: continue
            pair = tuple(sorted((a,c)))
            for p in pair:
                if p not in points: points[p] = {"tag":len(points)+1,"bbox_mm":[v for x in p for v in (x,x)]}
            if pair not in edges:
                edges[pair] = {"tag":len(edges)+1,"bbox_mm":[v for x,y in zip(a,c) for v in (min(x,y),max(x,y))],
                    "boundary":[points[p]["tag"] for p in pair]}
            face["boundary"].append(edges[pair]["tag"])
    after["0"],after["1"] = list(points.values()),list(edges.values())
    return after


def prepare(*, packet=None, planned=None, after=None, groups=None, cfg=None, limits=None, preserve=None):
    p = packet_fixture() if packet is None else packet
    r = plan(p) if planned is None else planned
    _, expected, labels = boundary_fixture()
    columns = geometry.Columns(p,report_fixture(),r,limits or LIMITS)
    review = audit.VolumeAudit(columns,rectangle_topology(after if after is not None else expected),
        groups if groups is not None else labels,BOXES,DOMAIN,["pri","sec"],cfg or MESH_CFG,
        limits or LIMITS,preserve_boundary=preserve)
    return columns,review


def complete(columns,review):
    rows = []
    for layer in range(len(columns.counts)):
        t,det = columns.slab(layer)
        rows.append(t.copy())
        review.visit(layer,t)
    result = review.finish()
    return np.concatenate(rows),result


def independent_facets(t):
    """Whole-mesh Python enumeration, separate from the streamed NumPy join."""
    counts = Counter(tuple(sorted(face)) for tet in t.tolist() for face in itertools.combinations(tet,3))
    assert all(v in (1,2) for v in counts.values())
    return {face for face,count in counts.items() if count == 1},sum(v == 2 for v in counts.values())


def test_complete_stream_equals_independent_whole_mesh_and_analytic_cavities():
    boundaries = []
    def preserve(faces,tags,owners): boundaries.append((faces.copy(),tags.copy(),owners.copy()))
    columns,review = prepare(preserve=preserve)
    t,result = complete(columns,review)
    exterior,internal = independent_facets(t)
    saved = np.concatenate([b[0] for b in boundaries])
    assert {tuple(sorted(row)) for row in saved.tolist()} == exterior
    assert result["boundary_triangles"] == len(saved) == len(exterior) == 180
    assert result["interior_facets"] == internal == 426
    assert result["mesh_nodes"] == 96 and result["mesh_tetrahedra"] == 258
    assert result["tetrahedral_components"] == 1
    assert result["independent_volume_mm3"] == 43.
    assert result["canonical_volume_mm3"] == {"numerator":"43","denominator":"1"}
    assert result["canonical_volume_error_mm3"] == {"numerator":"0","denominator":"1"}
    assert sum(result["cad_surface_mm2"].values()) == 90.
    assert result["minimum_independent_det_jac_mm3"] == 1.
    assert result["maximum_determinant_relative_difference"] == 0.
    assert result["boundary_groups"] == {
        "primary":{"nodes":8,"triangles":12},"secondary":{"nodes":8,"triangles":12},
        "outer":{"nodes":80,"triangles":156}}
    assert result["boundary_contract_passed"] and result["volume_mesh_generated"]
    assert not result["coordinates_snapped"] and not result["native_quality_claimed"]
    assert all(result[k] is False for k in audit.CLOSED)
    tags,xyz = review.node_arrays()
    assert np.array_equal(tags,np.arange(1,97)) and np.array_equal(xyz,columns.coordinates(tags))
    for faces,_,owners in boundaries:
        assert all(set(face) < set(t[owner-1]) for face,owner in zip(faces,owners))


def test_construction_matches_frozen_scalar_prism_rule_for_each_source_triangle():
    columns,_ = prepare()
    for layer in range(len(columns.counts)):
        observed,_ = columns.slab(layer)
        expected = [tuple(v+1 for v in row) for i,triangle in enumerate(columns.triangles)
            if layer in columns.retained[columns.masks[i]]
            for row in prism_indices(columns.xy.tolist(),triangle.tolist(),layer)]
        assert np.array_equal(observed,np.asarray(expected))


def test_input_record_order_sparse_tags_and_raw_orientation_are_preserved():
    original = packet_fixture()
    p = copy.deepcopy(original)
    old = p["node_tags"].copy()
    p["node_tags"] = 10**11+old*7
    p["triangle_nodes"] = 10**11+p["triangle_nodes"]*7
    p["line_nodes"] = 10**11+p["line_nodes"]*7
    p["triangle_nodes"][:,[1,2]] = p["triangle_nodes"][:,[2,1]]
    for prefix,names in (("node",["tags"]),("triangle",["tags","nodes","surfaces"]),("line",["tags","nodes","curves"])):
        for name in names: p[prefix+"_"+name] = p[prefix+"_"+name][::-1]
    for name in ("coordinates_mm","node_dimension","node_entity"): p[name] = p[name][::-1]
    before = copy.deepcopy(p)
    a,r = prepare(packet=p)
    t,result = complete(a,r)
    b,s = prepare()
    expected,report = complete(b,s)
    assert np.array_equal(t,expected) and result == report
    assert all(np.array_equal(p[k],before[k]) for k in p)


@pytest.mark.parametrize("damage",["missing","extra","flipped","unknown","repeated","wrong_plane","float"])
def test_changed_actual_connectivity_fails_closed_without_repair(damage):
    columns,review = prepare()
    t,_ = columns.slab(0)
    if damage == "missing": t = t[:-1]
    if damage == "extra": t = np.concatenate((t,t[:1]))
    if damage == "flipped": t[0,[1,2]] = t[0,[2,1]]
    if damage == "unknown": t[0,0] = columns.full_nodes+1
    if damage == "repeated": t[0,0] = t[0,1]
    if damage == "wrong_plane": t[0,0] += columns.n
    if damage == "float": t = t.astype(float)
    with pytest.raises(ValueError,match="connectivity"): review.visit(0,t)
    with pytest.raises(ValueError,match="failed"): review.visit(0,columns.slab(0)[0])
    with pytest.raises(ValueError): review.finish()
    with pytest.raises(ValueError): review.node_arrays()


@pytest.mark.parametrize("damage",["coordinate","negative","zero","nan","wrong_scale"])
def test_actual_coordinate_determinants_do_not_trust_the_generator(monkeypatch,damage):
    columns,review = prepare()
    t,expected = columns.slab(0)
    real_coordinates = columns.coordinates
    def coordinates(ids):
        xyz = real_coordinates(ids)
        if xyz.ndim == 3 and xyz.shape[1] == 4:
            if damage == "coordinate": xyz[0,0,0] += .1
            if damage == "negative": xyz[0,[1,2]] = xyz[0,[2,1]]
            if damage == "zero": xyz[0,1] = xyz[0,0]
            if damage == "nan": xyz[0,0,0] = np.nan
            if damage == "wrong_scale": xyz *= 2.
        return xyz
    monkeypatch.setattr(columns,"coordinates",coordinates)
    with pytest.raises(ValueError,match="determinant"): review.visit(0,t)


def test_slab_facets_reject_nonmanifold_and_same_induced_orientation():
    t = np.array([[1,2,3,4]],dtype=np.int64)
    with pytest.raises(ValueError,match="nonmanifold"): audit.slab_facets(np.repeat(t,3,axis=0))
    with pytest.raises(ValueError,match="orientations"): audit.slab_facets(np.repeat(t,2,axis=0))


@pytest.mark.parametrize("damage",["same_side","same_orientation","third_owner"])
def test_exact_cross_slab_seam_gate(damage):
    components = audit.Components(); components.add(3)
    before = (np.array([[1,2,3]]),np.array([0]),np.array([1]))
    after = (np.array([[1,3,2]]),np.array([1]),np.array([2]))
    if damage == "same_orientation": after = (before[0].copy(),after[1],after[2])
    if damage == "same_side": before = (np.array([[1,2,3],[1,3,2]]),np.array([0,1]),np.array([1,2])); after = (np.empty((0,3),int),np.empty(0,int),np.empty(0,int))
    if damage == "third_owner": after = (np.array([[1,3,2],[1,2,3]]),np.array([1,2]),np.array([2,3]))
    with pytest.raises(ValueError): audit.join_seam(before,after,components)


def test_components_preserve_terminal_anchoring_and_owner_conflicts():
    graph = audit.Components(); graph.add(4)
    graph.mark(0,17,True); graph.mark(1,17,False); graph.join(0,1)
    graph.mark(2,19,True); graph.mark(3,19,False)
    with pytest.raises(ValueError,match="no terminal"): graph.finish([17,19])
    graph.join(2,3)
    assert graph.finish([17,19]) == 2
    with pytest.raises(ValueError,match="CAD owner"): graph.join(0,2)


@pytest.mark.parametrize("damage",["missing_face","wrong_group","wrong_plane","area","normal","volume","boundary_cap"])
def test_full_surface_geometry_area_normal_and_cap_gates(damage):
    _,after,groups = boundary_fixture()
    cfg,limits = dict(MESH_CFG),dict(LIMITS)
    if damage == "missing_face": groups["outer"].pop()
    if damage == "wrong_group": groups["primary"],groups["secondary"] = groups["secondary"],groups["primary"]
    if damage == "wrong_plane": after["2"][0]["bbox_mm"][0] += .1
    if damage == "area": after["2"][0]["measure_native"] += .1
    if damage == "volume": after["3"][0]["measure_native"] += .1
    if damage == "boundary_cap": limits["mesh_triangles_max"] = 1
    with pytest.raises(ValueError):
        columns,review = prepare(after=after,groups=groups,cfg=cfg,limits=limits)
        if damage == "normal": review.surfaces[0]["normal_sign"] *= -1
        complete(columns,review)


@pytest.mark.parametrize("damage",["packet","plan_false","count","interval","plane","node_cap","tet_cap"])
def test_unbound_column_input_is_rejected(damage):
    p,r,limits = packet_fixture(),plan(),dict(LIMITS)
    if damage == "packet": p["coordinates_mm"][0,0] += .01
    if damage == "plan_false": r["planning_feasible"] = False
    if damage == "count": r["capacity"]["tetrahedra"] += 3
    if damage == "interval": r["capacity"]["groups"][0]["retained_z_intervals"].pop()
    if damage == "plane": r["vertical_axis"]["points_mm"][1] = .9
    if damage == "node_cap": limits["mesh_nodes_max"] = 95
    if damage == "tet_cap": limits["mesh_tetrahedra_max"] = 257
    with pytest.raises(ValueError): geometry.Columns(p,report_fixture(),r,limits)


@pytest.mark.parametrize("stage",["skip","repeat","early_finish","repeat_finish"])
def test_attempt_cannot_skip_or_repeat_volume_stages(stage):
    columns,review = prepare()
    with pytest.raises(ValueError):
        if stage == "skip": review.visit(1,columns.slab(1)[0])
        if stage == "repeat":
            review.visit(0,columns.slab(0)[0]); review.visit(0,columns.slab(0)[0])
        if stage == "early_finish": review.finish()
        if stage == "repeat_finish": complete(columns,review); review.finish()


def finer_planar_fixture():
    """A 25-node hand grid adds strict metal-interior column nodes."""
    values = [0.,1.,1.5,2.,3.]
    xyz = np.array([(x,y,0.) for y in values for x in values])
    snapshot = report_fixture()["after"]
    dimensions,entities = [],[]
    for point in xyz:
        match = next((r["tag"] for r in snapshot["0"] if np.array_equal(point,r["point_mm"])),None)
        if match: dimensions.append(0); entities.append(match); continue
        match = next((r["tag"] for r in snapshot["1"] if r["bbox_mm"][0] <= point[0] <= r["bbox_mm"][1]
                      and r["bbox_mm"][2] <= point[1] <= r["bbox_mm"][3]),None)
        dimensions.append(1 if match else 2)
        entities.append(match if match else (2 if 1 < point[0] < 2 and 1 < point[1] < 2 else 1))
    triangles,faces = [],[]
    for y,x in itertools.product(range(4),repeat=2):
        a,b,c,d = 1+5*y+x,2+5*y+x,7+5*y+x,6+5*y+x
        triangles.extend([[a,b,c],[a,c,d]])
        faces.extend([2 if x in (1,2) and y in (1,2) else 1]*2)
    lines,curves = [],[]
    for row in snapshot["1"]:
        b = row["bbox_mm"]
        selected = [i+1 for i,p in enumerate(xyz) if b[0] <= p[0] <= b[1] and b[2] <= p[1] <= b[3]]
        selected.sort(key=lambda i:tuple(xyz[i-1]))
        for a,b in zip(selected,selected[1:]): lines.append([a,b]); curves.append(row["tag"])
    return {"node_tags":np.arange(1,26,dtype=np.int64),"coordinates_mm":xyz,
        "node_dimension":np.array(dimensions),"node_entity":np.array(entities),
        "triangle_tags":np.arange(1000,1032),"triangle_nodes":np.array(triangles),"triangle_surfaces":np.array(faces),
        "line_tags":np.arange(100,100+len(lines)),"line_nodes":np.array(lines),"line_curves":np.array(curves)}


def test_defined_node_projection_excludes_only_unused_metal_interior_nodes():
    p = finer_planar_fixture()
    r = planning.plan_packet(p,report_fixture(),BOXES,DOMAIN,CFG,OPTIONS,
        {**POLICY,"near_size_mm":.5},SETTINGS,LIMITS)
    # The finer planar grid crosses the unit square subdivisions of this CAD
    # fixture exactly; every expected face remains independently checkable.
    columns,review = prepare(packet=p,planned=r)
    t,result = complete(columns,review)
    tags,xyz = review.node_arrays()
    assert np.array_equal(tags,np.unique(t))
    removed = sorted(set(range(1,columns.full_nodes+1))-set(tags.tolist()))
    assert len(removed) == 2
    assert np.array_equal(columns.coordinates(np.array(removed)),np.array([[1.5,1.5,1.5],[1.5,1.5,3.5]]))
    assert result["independent_volume_mm3"] == 43.
    assert result["mesh_nodes"] == columns.full_nodes-2


def test_native_style_padded_bounds_do_not_change_mesh_coordinates_or_area_gates():
    _,after,groups = boundary_fixture()
    after = rectangle_topology(after)
    for records in after.values():
        for row in records:
            row["bbox_mm"] = [v+(-1e-7 if k % 2 == 0 else 1e-7) for k,v in enumerate(row["bbox_mm"])]
    columns,_ = prepare()
    review = audit.VolumeAudit(columns,after,groups,BOXES,DOMAIN,["pri","sec"],MESH_CFG,LIMITS)
    observed,result = complete(columns,review)
    reference,other = prepare(); expected,baseline = complete(reference,other)
    assert result == baseline and np.array_equal(observed,expected)
    assert np.array_equal(review.node_arrays()[1],other.node_arrays()[1])


@pytest.mark.parametrize("damage",["edge_count","point_count","direction","endpoint","owner","internal","ambiguous"])
def test_boundary_adapter_rejects_unsupported_or_corrupted_cad_without_omission(damage):
    _,after,groups = boundary_fixture()
    after = rectangle_topology(after)
    first = after["2"][0]
    if damage == "edge_count": first["boundary"].pop()
    if damage == "point_count": after["1"][0]["boundary"] = [1]
    if damage == "direction": after["1"][0]["bbox_mm"] = [0.,1.,0.,1.,0.,1.]
    if damage == "endpoint": after["0"][0]["bbox_mm"] = [99.]*6
    if damage == "owner": first["upward"] = [999]
    if damage == "internal": groups["internal_dielectric"] = [first["tag"]]
    if damage == "ambiguous":
        extra = copy.deepcopy(first); extra["tag"] = max(r["tag"] for r in after["2"])+1
        after["2"].append(extra); groups["outer"].append(extra["tag"])
    columns,_ = prepare()
    with pytest.raises(ValueError):
        review = audit.VolumeAudit(columns,after,groups,BOXES,DOMAIN,["pri","sec"],MESH_CFG,LIMITS)
        complete(columns,review)


def test_two_slab_components_can_join_later_without_losing_terminal_anchor():
    components = audit.Components()
    assert components.add(2) == 0
    components.mark(0,17,True); components.mark(1,17,False)
    assert components.add(1) == 2
    components.join(0,2); components.join(1,2)
    assert components.finish([17]) == 1


def test_nonrepresentable_exact_height_difference_uses_exact_column_oracle():
    boxes = copy.deepcopy(BOXES); boxes[0][4] = .1
    cad = report_fixture(); cad["canonical_boxes_mm"] = boxes
    packet = packet_fixture()
    planned = planning.plan_packet(packet,cad,boxes,DOMAIN,CFG,OPTIONS,
        {**POLICY,"near_size_mm":10.,"far_size_mm":10.},SETTINGS,LIMITS)
    after = {"2":[],"3":[{"tag":17,"measure_native":42.1,"bbox_mm":list(DOMAIN)}]}
    groups = {k:[] for k in ("primary","secondary","outer","internal_dielectric")}
    for box,group in zip([DOMAIN,*boxes],["outer","primary","secondary"]):
        for side in range(6):
            b = list(box); b[2*(side//2)] = b[2*(side//2)+1] = box[side]
            area = np.prod([box[k+1]-box[k] for k in (0,2,4) if k//2 != side//2])
            tag = len(after["2"])+1
            after["2"].append({"tag":tag,"bbox_mm":b,"measure_native":float(area),"upward":[17]})
            groups[group].append(tag)
    columns = geometry.Columns(packet,cad,planned,LIMITS)
    review = audit.VolumeAudit(columns,rectangle_topology(after),groups,boxes,DOMAIN,["pri","sec"],MESH_CFG,LIMITS)
    t,result = complete(columns,review)
    assert Fraction(2)-Fraction(.1) != Fraction(2-.1)
    assert result["canonical_volume_mm3"] == planned["capacity"]["exact_dielectric_volume_mm3"]
    assert result["maximum_determinant_relative_difference"] < MESH_CFG["jacobian_rtol"]
    assert result["boundary_contract_passed"] and len(t) == planned["capacity"]["tetrahedra"]


@pytest.mark.parametrize("damage",["missing_checks","duplicate_group","node_cap_type","tet_cap_type","plane_count"])
def test_declared_input_shapes_and_cap_types_are_not_coerced(damage):
    p,r,limits = packet_fixture(),plan(),dict(LIMITS)
    if damage == "missing_checks": r["planning_checks"].pop("jacobian_condition_bound")
    if damage == "duplicate_group": r["capacity"]["groups"].append(copy.deepcopy(r["capacity"]["groups"][0]))
    if damage == "node_cap_type": limits["mesh_nodes_max"] = 1000.
    if damage == "tet_cap_type": limits["mesh_tetrahedra_max"] = True
    if damage == "plane_count": r["vertical_axis"]["point_count"] += 1
    with pytest.raises(ValueError): geometry.Columns(p,report_fixture(),r,limits)
