"""Tiny explicit synthetic geometry only; no real-layout/native computation."""
import ast
from collections import Counter
import copy
from fractions import Fraction as F
import itertools
import math
from pathlib import Path
import sys
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/solvers"))
import tcad_cps_column_contract as c
from tcad_cps_jacobian_exact import homogeneous

BOXES = [[1.,3.,1.,3.,1.,2.], [2.,4.,2.,4.,3.,4.]]
DOMAIN = [0.,5.,0.,5.,0.,5.]
POLICY = {"near_size_mm": 1., "far_size_mm": 2., "face_band_half_width_mm": .1}
Z = [0.,1.,2.,3.,4.,5.]
GROUPS = [{"owners": [], "triangles": 16}, {"owners": [0], "triangles": 6},
          {"owners": [0,1], "triangles": 2}, {"owners": [1], "triangles": 6}]
LIMITS = {"mesh_nodes_max": 1000, "mesh_tetrahedra_max": 1000}


def capacity(**changes):
    data = dict(boxes=copy.deepcopy(BOXES), domain=list(DOMAIN), z_points=list(Z),
                groups=copy.deepcopy(GROUPS), planar_nodes=24, limits=dict(LIMITS))
    data.update(changes)
    return c.column_capacity(**data)


def test_independent_ownership_areas_not_union_or_one_owner():
    p = c.footprint_partition(BOXES,DOMAIN)
    assert {tuple(g["owners"]): c.unpack(g["area_mm2"]) for g in p["groups"]} == {():18, (0,):3, (0,1):1, (1,):3}
    assert c.unpack(p["domain_area_mm2"]) == 25
    assert p["reference_rectangles"] == 25
    assert p["coordinates_snapped"] is False


def test_duplicate_projection_is_a_shared_mask_not_duplicate_metal_volume():
    boxes = copy.deepcopy(BOXES)
    boxes[1][:4] = boxes[0][:4]
    p = c.footprint_partition(boxes,DOMAIN)
    assert {tuple(g["owners"]): c.unpack(g["area_mm2"]) for g in p["groups"]} == {():21, (0,1):4}
    report = capacity(boxes=boxes, groups=[{"owners":[], "triangles":8},{"owners":[0,1],"triangles":2}])
    assert c.unpack(report["exact_dielectric_volume_mm3"]) == 117
    assert report["prisms"] == 8*5+2*3


def test_triple_projection_ownership_recovers_each_independent_conductor_area():
    boxes = copy.deepcopy(BOXES)+[[1.5,3.5,1.5,3.5,5.,6.]]
    domain = [0.,5.,0.,5.,0.,7.]
    partition = c.footprint_partition(boxes,domain)
    assert [0,1,2] in [g["owners"] for g in partition["groups"]]
    for i,box in enumerate(boxes):
        area = sum(c.unpack(g["area_mm2"]) for g in partition["groups"] if i in g["owners"])
        assert area == (F(box[1])-F(box[0]))*(F(box[3])-F(box[2]))
    groups = [{"owners":g["owners"],"triangles":2} for g in partition["groups"]]
    result = c.column_capacity(boxes,domain,[0.,1.,2.,3.,4.,5.,6.,7.],groups,30,LIMITS)
    assert c.unpack(result["exact_dielectric_volume_mm3"]) == 163


def test_one_ulp_footprint_strip_is_preserved_exactly():
    boxes = copy.deepcopy(BOXES)
    boxes[1][:4] = boxes[0][:4]
    boxes[1][0] = math.nextafter(boxes[0][0],math.inf)
    p = c.footprint_partition(boxes,DOMAIN)
    expected = (F(boxes[1][0])-F(boxes[0][0]))*2
    assert {tuple(g["owners"]):c.unpack(g["area_mm2"]) for g in p["groups"]}[(0,)] == expected > 0
    assert 1. in p["reference_planes_xy_mm"][0] and boxes[1][0] in p["reference_planes_xy_mm"][0]


def test_hand_counted_column_volume_capacity_and_closed_gates():
    report = capacity()
    assert report["prisms"] == 16*5+6*4+2*3+6*4 == 134
    assert report["tetrahedra"] == 402 and report["column_node_upper_bound"] == 144
    assert c.unpack(report["exact_dielectric_volume_mm3"]) == 117
    assert report["groups"][2]["retained_z_intervals"] == [0,2,4]
    assert report["capacity_feasible"] is True
    assert report["planar_mesh_validated"] is False and report["conditioning_validated"] is False
    assert all(report[k] is False for k in c.CLOSED)


@pytest.mark.parametrize("name", list(LIMITS))
def test_failed_capacity_is_reported_without_changing_geometry(name):
    report = capacity(limits={**LIMITS,name:1})
    assert report["capacity_feasible"] is False and report["tetrahedra"] == 402


def test_more_z_points_change_counts_not_dielectric_volume():
    a,b = capacity(),capacity(z_points=[0.,.5,1.,2.,2.5,3.,4.,5.])
    assert b["tetrahedra"] > a["tetrahedra"]
    assert b["exact_dielectric_volume_mm3"] == a["exact_dielectric_volume_mm3"]


def test_input_permutation_relabels_owner_sets_but_preserves_measure():
    a,b = c.footprint_partition(BOXES,DOMAIN),c.footprint_partition(list(reversed(BOXES)),DOMAIN)
    remapped = {tuple(sorted(1-i for i in g["owners"])): g["area_mm2"] for g in b["groups"]}
    assert remapped == {tuple(g["owners"]):g["area_mm2"] for g in a["groups"]}


@pytest.mark.parametrize("defect", ["overlap", "outside", "nan", "bool", "rounded_int", "zero", "cap", "empty"])
def test_invalid_canonical_geometry_is_rejected(defect):
    boxes,domain,cap = copy.deepcopy(BOXES),list(DOMAIN),128
    if defect == "overlap": boxes[1][4:6] = [1.,2.]
    if defect == "outside": boxes[0][0] = domain[0]
    if defect == "nan": boxes[0][0] = float("nan")
    if defect == "bool": boxes[0][0] = True
    if defect == "rounded_int": domain[1] = 2**53+1
    if defect == "zero": boxes[0][1] = boxes[0][0]
    if defect == "cap": cap = 1
    if defect == "empty": boxes = []
    with pytest.raises(ValueError): c.footprint_partition(boxes,domain,cap)


@pytest.mark.parametrize("defect", ["missing_mask", "duplicate_mask", "unknown_owner", "partial_mask", "unsorted", "float_count", "zero_count", "bool_nodes", "missing_z", "reversed_z", "domain_z", "zero_limit", "extra_field"])
def test_column_metadata_cannot_silently_lose_ownership_or_geometry(defect):
    groups,z,nodes,limits = copy.deepcopy(GROUPS),list(Z),24,dict(LIMITS)
    if defect == "missing_mask": groups.pop()
    if defect == "duplicate_mask": groups.append(copy.deepcopy(groups[0]))
    if defect == "unknown_owner": groups[1]["owners"] = [2]
    if defect == "partial_mask": groups[2]["owners"] = [0]
    if defect == "unsorted": groups[2]["owners"] = [1,0]
    if defect == "float_count": groups[0]["triangles"] = 16.
    if defect == "zero_count": groups[0]["triangles"] = 0
    if defect == "bool_nodes": nodes = True
    if defect == "missing_z": z.remove(2.)
    if defect == "reversed_z": z[0],z[1] = z[1],z[0]
    if defect == "domain_z": z[0] = -.1
    if defect == "zero_limit": limits["mesh_nodes_max"] = 0
    if defect == "extra_field": groups[0]["accepted"] = True
    with pytest.raises(ValueError): capacity(groups=groups,z_points=z,planar_nodes=nodes,limits=limits)


def test_z_axis_preserves_faces_and_is_independent_of_xy_close_planes():
    a = c.vertical_plan(BOXES,DOMAIN,POLICY)
    boxes = copy.deepcopy(BOXES)
    boxes[1][0] = math.nextafter(boxes[0][0], math.inf)
    assert c.vertical_plan(boxes,DOMAIN,POLICY) == a
    assert a["base_planes_mm"] == a["canonical_planes_mm"] == Z
    assert set(Z) <= set(a["points_mm"])


@pytest.mark.parametrize("options", [{"point_cap":2},{"depth_cap":0},{"point_cap":4097}])
def test_vertical_caps_fail_closed(options):
    with pytest.raises(ValueError): c.vertical_plan(BOXES,DOMAIN,POLICY,**options)


def facets(tets):
    return Counter(tuple(sorted(f)) for t in tets for f in itertools.combinations(t,3))


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
@pytest.mark.parametrize("height", [.125,1.,4.])
def test_prism_orientation_volume_and_permutation_stability(order,height):
    points = [(0.,0.),(2.,0.),(.5,1.)]
    tets = c.prism_indices(points,order,0)
    assert tets == c.prism_indices(points,[0,1,2],0)
    xyz = [[F(x),F(y),F(z)] for z in (0.,height) for x,y in points]
    signed = [homogeneous([xyz[i] for i in t]) for t in tets]
    assert all(v == F(2)*F(height) for v in signed)
    assert sum(signed)/6 == F(height)
    counts = facets(tets)
    assert list(counts.values()).count(2) == 2
    assert list(counts.values()).count(1) == 8


@pytest.mark.parametrize("permutation", list(itertools.permutations(range(4))))
def test_adjacent_prisms_have_identical_shared_face_triangulation(permutation):
    original = [(0.,0.),(1.,0.),(0.,1.),(1.,1.)]
    points = [original[i] for i in permutation]
    index = {old:new for new,old in enumerate(permutation)}
    a,b = ([index[i] for i in t] for t in ([0,1,2],[1,3,2]))
    pa,pb = c.prism_indices(points,a,0),c.prism_indices(points,b,0)
    shared = {index[1],index[2],index[1]+4,index[2]+4}
    fa = {f for f,n in facets(pa).items() if n == 1 and set(f) <= shared}
    fb = {f for f,n in facets(pb).items() if n == 1 and set(f) <= shared}
    assert fa == fb and len(fa) == 2
    for layer in (0,1):
        xyz = [[F(x),F(y),F(z)] for z in range(3) for x,y in points]
        assert all(homogeneous([xyz[i] for i in t]) > 0 for triangle in (a,b)
                   for t in c.prism_indices(points,triangle,layer))


@pytest.mark.parametrize("points", [[(0.,0.),(2.,0.),(.5,1.)],[(0.,0.),(.001,0.),(.0001,3.)],[(5.,7.),(5.,8.),(6.,7.)]])
@pytest.mark.parametrize("permutation", list(itertools.permutations(range(3))))
def test_condition_certificate_against_direct_exact_maps_at_interior_heights(points,permutation):
    points = [points[i] for i in permutation]
    report = c.prism_condition_bound(points,.125,4.)
    xy,_ = c.triangle_coordinates(points)
    for h in (F(1,8),F(1,4),F(1,2),F(1),F(2),F(4)):
        vertices = [p+[z] for z in (F(0),h) for p in xy]
        for pattern,bound in zip(c.PRISM_PATTERN,report["tetrahedra"]):
            v = [vertices[k] for k in pattern]
            j = [[v[k][i]-v[0][i] for k in (1,2,3)] for i in range(3)]
            inv = c.inverse(j)
            assert [[sum(j[i][k]*inv[k][m] for k in range(3)) for m in range(3)] for i in range(3)] == [[1,0,0],[0,1,0],[0,0,1]]
            norm = sum(x*x for row in j for x in row)*sum(x*x for row in inv for x in row)
            assert norm <= c.unpack(bound["condition_upper_bound_squared"])
            assert abs(homogeneous(v)) >= c.unpack(report["minimum_positive_determinant_mm3"])
    assert report["native_quality_claimed"] is False
    assert all(report[k] is False for k in c.CLOSED)


def test_exact_stored_z_difference_is_never_rounded_before_certificate():
    height = F(1.)-F(.1)
    assert height != F(float(height))
    report = c.prism_condition_bound([(0.,0.),(1.,0.),(0.,1.)],height,height)
    assert c.unpack(report["minimum_height_mm"]) == c.unpack(report["maximum_height_mm"]) == height
    assert c.unpack(report["minimum_positive_determinant_mm3"]) == height


def test_horizontal_interface_is_conforming_between_unequal_layers():
    points = [(0.,0.),(2.,0.),(0.,1.)]
    low,high = (facets(c.prism_indices(points,[2,0,1],layer)) for layer in (0,1))
    assert {f for f,n in low.items() if n == 1 and set(f) <= {3,4,5}} == {(3,4,5)}
    assert {f for f,n in high.items() if n == 1 and set(f) <= {3,4,5}} == {(3,4,5)}


def test_thin_or_bad_triangle_is_not_accepted_merely_for_positive_volume():
    p = [(0.,0.),(1.,0.),(.5,1e-12)]
    report = c.prism_condition_bound(p,.1,2.)
    assert c.unpack(report["minimum_positive_determinant_mm3"]) > 0
    assert report["conditioning_passed"] is False


@pytest.mark.parametrize("height", [0.,-1.,float("nan"),True,2**53+1])
def test_bad_height_rejected(height):
    with pytest.raises(ValueError): c.prism_condition_bound([(0.,0.),(1.,0.),(0.,1.)],height,4.)


def test_degenerate_triangle_rejected():
    with pytest.raises(ValueError): c.prism_condition_bound([(0.,0.),(1.,1.),(2.,2.)],1.,2.)


def test_module_does_not_create_native_or_real_input_execution_path():
    tree = ast.parse(Path(c.__file__).read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    imports.update(alias.name for n in ast.walk(tree) if isinstance(n,ast.Import) for alias in n.names)
    assert imports <= {"fractions","math","tcad_cps_layer_grid_axes","tcad_cps_layer_grid_dyadic_axes"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert not {"open","eval","exec","__import__"} & calls


def test_command_line_refuses_unintegrated_real_input_execution():
    result = subprocess.run([sys.executable,c.__file__,"--mode","toy"],capture_output=True,text=True,timeout=10)
    assert result.returncode != 0 and "guarded SLURM protocol" in result.stderr
