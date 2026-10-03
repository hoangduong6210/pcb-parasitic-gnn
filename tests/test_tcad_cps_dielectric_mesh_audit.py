"""Tiny explicit lattice fixtures/fake API only; no native CAD or meshing."""
import copy
import itertools
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "code/solvers"))
import tcad_cps_dielectric_mesh_audit as m

CFG = {"coordinate_atol_mm": 1e-6, "measure_rtol": 1e-8,
       "measure_atol_native": 1e-9, "sicn_max": 1.000000000001, "jacobian_rtol": 1e-8}
LIMITS = {"mesh_nodes_max": 1000, "mesh_tetrahedra_max": 1000, "mesh_triangles_max": 1000}


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def fixture(split=False):
    """43 unit cubes, six explicit Freudenthal tets each, two interior holes.

    Analytic volume = 43; outer area = 78; each hole area = 6. These are
    hand-constructed test arrays, not a geometry/mesher/physics observation.
    """
    holes = {(1, 1, 1): "primary", (1, 1, 3): "secondary"}
    nodes = list(itertools.product(range(4), range(4), range(6)))
    node_index = {p: i for i, p in enumerate(nodes)}
    tetrahedra, volumes, square_faces = [], [], {}
    cube_counts = {}

    def region(cell):
        if cell in holes:
            return None
        return 19 if split and cell[2] >= 3 else 17

    for cell in itertools.product(range(3), range(3), range(5)):
        if cell in holes:
            continue
        vol = region(cell)
        cube_counts[vol] = cube_counts.get(vol, 0) + 1
        for perm in itertools.permutations(range(3)):
            corner = list(cell)
            vertices = [node_index[tuple(corner)]]
            for axis in perm:
                corner[axis] += 1
                vertices.append(node_index[tuple(corner)])
            inversions = sum(perm[i] > perm[j] for i in range(3) for j in range(i+1, 3))
            if inversions % 2:
                vertices[1], vertices[2] = vertices[2], vertices[1]
            tetrahedra.append(vertices)
            volumes.append(vol)
        # Expected CAD square labels derive independently from adjacent cells,
        # not from the audit's tetrahedral-facet matching algorithm.
        for axis in range(3):
            for side in (0, 1):
                neighbor = list(cell)
                neighbor[axis] += -1 if side == 0 else 1
                neighbor = tuple(neighbor)
                outside = any(not 0 <= neighbor[i] < (3, 3, 5)[i] for i in range(3))
                other = None if outside else region(neighbor)
                if not outside and neighbor not in holes and other == vol:
                    continue
                bounds = [v for x in cell for v in (x, x+1)]
                bounds[2*axis] = bounds[2*axis+1] = cell[axis] + side
                key = tuple(bounds)
                label = "outer" if outside else holes.get(neighbor, "internal_dielectric")
                if key not in square_faces:
                    square_faces[key] = {"tag": len(square_faces)+1, "bbox_mm": bounds,
                        "measure_native": 1., "upward": sorted([vol] if other is None else [vol, other]),
                        "group": label}
    t = np.asarray(tetrahedra, dtype=np.int64)
    # Enumerate known external square triangulations from fixed tetrahedra.
    facets = {}
    for tet in tetrahedra:
        for face in itertools.combinations(tet, 3):
            key = tuple(sorted(face))
            facets[key] = facets.get(key, 0) + 1
    tris, surface_ids = [], []
    xyz = np.asarray(nodes, dtype=np.float64)
    for face, count in facets.items():
        points = xyz[list(face)]
        bounds = tuple(v for low, high in zip(points.min(axis=0), points.max(axis=0)) for v in (low, high))
        if bounds in square_faces:
            tris.append(face)
            surface_ids.append(square_faces[bounds]["tag"])
        elif count != 2:
            raise AssertionError("fixture has an unexpected exposed facet")
    # Deliberately sparse native tags: algorithms must not allocate max(tag).
    node_tags = 10**11 + 7*np.arange(1, len(nodes)+1, dtype=np.int64)
    packet = {"node_tags": node_tags, "coordinates_mm": xyz,
        "tetrahedron_tags": 10**12+np.arange(1, len(t)+1, dtype=np.int64),
        "tetrahedron_nodes": node_tags[t], "tetrahedron_volumes": np.asarray(volumes, dtype=np.int64),
        "triangle_tags": 10**13+np.arange(1, len(tris)+1, dtype=np.int64),
        "triangle_nodes": node_tags[np.asarray(tris)], "triangle_faces": np.asarray(surface_ids, dtype=np.int64),
        "min_sicn": np.full(len(t), .5), "min_det_jac_mm3": np.ones(len(t))}
    groups = {name: [r["tag"] for r in square_faces.values() if r["group"] == name] for name in m.GROUPS}
    after = {"2": [{k: v for k, v in r.items() if k != "group"} for r in square_faces.values()],
             "3": [{"tag": tag, "measure_native": float(count), "bbox_mm": [0, 3, 0, 3, 0, 5]}
                   for tag, count in sorted(cube_counts.items())]}
    return packet, after, groups


def audit(packet, after, groups, cfg=None, limits=None):
    return m._audit_packet(packet, after, groups, cfg or CFG, limits or LIMITS)


@pytest.mark.parametrize("split", [False, True])
def test_exact_analytic_lattice_boundary(split):
    packet, after, groups = fixture(split)
    canonical, result = audit(packet, after, groups)
    assert result["mesh_nodes"] == 96
    assert result["mesh_tetrahedra"] == 258
    # The split plane has area 9 minus the second terminal's unit-square end.
    assert result["mesh_triangles"] == (196 if split else 180)
    assert result["exterior_facets"] == 180
    assert result["interior_facets"] == 426
    assert result["cross_volume_facets"] == (16 if split else 0)
    assert result["tetrahedral_components"] == 1
    assert sum(result["cad_volume_mm3"].values()) == 43
    assert sum(result["cad_surface_mm2"].values()) == (98 if split else 90)
    assert result["boundary_groups"]["primary"]["triangles"] == 12
    assert result["boundary_groups"]["secondary"]["triangles"] == 12
    assert result["boundary_groups"]["primary"]["nodes"] == 8
    assert result["boundary_contract_passed"] is True
    for key in ("field_solver_executed", "numerical_accuracy_qualified", "reference_qualified", "training_may_start", "claim_eligible"):
        assert result[key] is False
    for key in packet:
        assert np.array_equal(canonical[key], packet[key])


def test_canonicalizes_record_order_not_vertex_order():
    packet, after, groups = fixture()
    canonical, result = audit(packet, after, groups)
    for prefix, extras in (("node", ["coordinates_mm"]), ("tetrahedron", ["tetrahedron_nodes", "tetrahedron_volumes", "min_sicn", "min_det_jac_mm3"]),
                           ("triangle", ["triangle_nodes", "triangle_faces"])):
        for name in [prefix + "_tags", *extras]:
            packet[name] = packet[name][::-1]
    assert audit(packet, after, groups)[1] == result
    packet["triangle_nodes"] = packet["triangle_nodes"][:, ::-1]
    changed = audit(packet, after, groups)[1]
    assert changed["packet_sha256"] != result["packet_sha256"]
    assert changed["boundary_contract_passed"] is True


@pytest.mark.parametrize("name", list(m.ARRAY_DTYPES))
def test_missing_array_rejected(name):
    packet, after, groups = fixture()
    del packet[name]
    with pytest.raises(ValueError, match="fields"):
        audit(packet, after, groups)


@pytest.mark.parametrize("name", ["node_tags", "tetrahedron_tags", "triangle_tags", "tetrahedron_nodes", "triangle_nodes", "tetrahedron_volumes", "triangle_faces"])
@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_tag_value_types_rejected(name, value):
    packet, after, groups = fixture()
    packet[name] = packet[name].astype(object if value is True else float if value == 1.5 else np.int64)
    packet[name].flat[0] = value
    with pytest.raises(ValueError):
        audit(packet, after, groups)


@pytest.mark.parametrize("name", ["node_tags", "tetrahedron_tags", "triangle_tags"])
def test_duplicate_tags_rejected(name):
    packet, after, groups = fixture()
    packet[name][1] = packet[name][0]
    with pytest.raises(ValueError, match="duplicate"):
        audit(packet, after, groups)


@pytest.mark.parametrize("name", ["tetrahedron_nodes", "triangle_nodes"])
def test_duplicate_connectivity_rejected(name):
    packet, after, groups = fixture()
    packet[name][1] = packet[name][0][::-1]
    with pytest.raises(ValueError, match="duplicate element connectivity"):
        audit(packet, after, groups)


@pytest.mark.parametrize("name", ["tetrahedron_nodes", "triangle_nodes"])
@pytest.mark.parametrize("unknown", [1, 10**15])
def test_unknown_nodes_rejected(name, unknown):
    packet, after, groups = fixture()
    packet[name][0, 0] = unknown
    with pytest.raises(ValueError, match="unknown node"):
        audit(packet, after, groups)


@pytest.mark.parametrize("name", ["coordinates_mm", "min_sicn", "min_det_jac_mm3"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_arrays_rejected(name, bad):
    packet, after, groups = fixture()
    packet[name].flat[0] = bad
    with pytest.raises(ValueError, match="finite real"):
        audit(packet, after, groups)


@pytest.mark.parametrize("name,value", [("min_sicn", 0), ("min_sicn", -1e-16), ("min_sicn", 1.01),
                                        ("min_det_jac_mm3", 0), ("min_det_jac_mm3", -1e-16)])
def test_no_quality_relaxation(name, value):
    packet, after, groups = fixture()
    packet[name][0] = value
    with pytest.raises(ValueError, match="quality/Jacobian"):
        audit(packet, after, groups)


def test_native_jacobian_cannot_hide_orientation_flip():
    packet, after, groups = fixture()
    packet["tetrahedron_nodes"][0, [1, 2]] = packet["tetrahedron_nodes"][0, [2, 1]]
    with pytest.raises(ValueError, match="independent signed"):
        audit(packet, after, groups)


def test_native_jacobian_must_match_coordinates():
    packet, after, groups = fixture()
    packet["min_det_jac_mm3"][0] = 1.01
    with pytest.raises(ValueError, match="Jacobians disagree"):
        audit(packet, after, groups)


@pytest.mark.parametrize("cap", list(LIMITS))
def test_caps_before_facet_work(cap, monkeypatch):
    packet, after, groups = fixture()
    limits = {**LIMITS, cap: 1}
    monkeypatch.setattr(m, "row_order", lambda *_: (_ for _ in ()).throw(AssertionError("too late")))
    # Tetrahedron/triangle cap follows earlier entity validation; do not require
    # preceding small connectivity blocks to bypass their own validation.
    if cap != "mesh_nodes_max":
        monkeypatch.undo()
    with pytest.raises(ValueError, match="cap"):
        audit(packet, after, groups, limits=limits)


@pytest.mark.parametrize("dimension", ["2", "3"])
def test_cad_measure_disagreement(dimension):
    packet, after, groups = fixture()
    after[dimension][0]["measure_native"] *= 1.1
    with pytest.raises(ValueError, match="sum differs"):
        audit(packet, after, groups)


def test_orphan_node_rejected():
    packet, after, groups = fixture()
    packet["node_tags"] = np.r_[packet["node_tags"], 10**14]
    packet["coordinates_mm"] = np.vstack([packet["coordinates_mm"], [1, 1, 1]])
    with pytest.raises(ValueError, match="orphan"):
        audit(packet, after, groups)


def test_missing_exterior_triangle_rejected():
    packet, after, groups = fixture()
    for name in ("triangle_tags", "triangle_nodes", "triangle_faces"):
        packet[name] = packet[name][1:]
    with pytest.raises(ValueError, match="exactly cover"):
        audit(packet, after, groups)


def test_internal_interface_cannot_be_neumann():
    packet, after, groups = fixture(split=True)
    groups["outer"] += groups["internal_dielectric"]
    groups["internal_dielectric"] = []
    with pytest.raises(ValueError, match="group/owner"):
        audit(packet, after, groups)


def test_wrong_face_owner_rejected():
    packet, after, groups = fixture(split=True)
    face = next(r for r in after["2"] if len(r["upward"]) == 1)
    face["upward"] = [19 if face["upward"] == [17] else 17]
    with pytest.raises(ValueError, match="wrong dielectric owner"):
        audit(packet, after, groups)


def test_surface_labels_must_match_coordinate_plane():
    packet, after, groups = fixture()
    # Same area and owner, but two disjoint outer unit squares swapped.
    left, right = groups["outer"][0], groups["outer"][-1]
    original = packet["triangle_faces"].copy()
    packet["triangle_faces"][original == left] = right
    packet["triangle_faces"][original == right] = left
    with pytest.raises(ValueError, match="surface bounds/plane"):
        audit(packet, after, groups)


def test_primary_secondary_node_short_rejected():
    packet, after, groups = fixture()
    moved = groups["primary"].pop()
    groups["secondary"].append(moved)
    with pytest.raises(ValueError, match="nodes overlap"):
        audit(packet, after, groups)


def test_public_wrapper_replays_cad_before_numeric_work(monkeypatch):
    called = []
    def fail(*args):
        called.append(args)
        raise ValueError("unverified CAD")
    monkeypatch.setattr(m, "review_report", fail)
    with pytest.raises(ValueError, match="unverified CAD"):
        m.audit_cad_mesh({}, {}, {}, 2., {}, {}, CFG, LIMITS)
    assert len(called) == 1


class FakeNative:
    def __init__(self, packet, after):
        self.packet, self.after = packet, after
        self.model = SimpleNamespace(mesh=self, getEntities=lambda dim: [(dim, r["tag"]) for r in after[str(dim)]])
        self.quality_calls = []

    def getElementProperties(self, kind):
        if kind == 4:
            return "Tetrahedron 4", 3, 1, 4, np.array([0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1.]), 4
        assert kind == 2
        return "Triangle 3", 2, 1, 3, np.array([0., 0., 1., 0., 0., 1.]), 3

    def getNodes(self, *args):
        assert args == (-1, -1, False, False)
        return self.packet["node_tags"], self.packet["coordinates_mm"].ravel(), []

    def getElements(self, dim, tag):
        prefix, entities, kind = ("tetrahedron", "volumes", 4) if dim == 3 else ("triangle", "faces", 2)
        mask = slice(None) if tag == -1 else self.packet[prefix + "_" + entities] == tag
        return [kind], [self.packet[prefix + "_tags"][mask]], [self.packet[prefix + "_nodes"][mask].ravel()]

    def getElementQualities(self, tags, metric):
        indices = np.searchsorted(self.packet["tetrahedron_tags"], tags)
        assert np.array_equal(tags, self.packet["tetrahedron_tags"][indices])
        self.quality_calls.append(metric)
        return self.packet[{"minSICN": "min_sicn", "minDetJac": "min_det_jac_mm3"}[metric]][indices]


@pytest.mark.parametrize("split", [False, True])
def test_fake_native_full_extraction(split):
    packet, after, groups = fixture(split)
    native = FakeNative(packet, after)
    extracted = m.extract_mesh_packet(native, {"after": after}, LIMITS)
    assert audit(extracted, after, groups)[1] == audit(packet, after, groups)[1]
    assert native.quality_calls == ["minSICN", "minDetJac"]


@pytest.mark.parametrize("kind", [1, 5, 11, 9])
def test_no_unsupported_element_skipping(kind):
    packet, after, groups = fixture()
    native = FakeNative(packet, after)
    original = native.getElements
    native.getElements = lambda dim, tag: ([kind], *original(dim, tag)[1:])
    with pytest.raises(ValueError, match="supported first-order"):
        m.extract_mesh_packet(native, {"after": after}, LIMITS)


@pytest.mark.parametrize("global_change", ["drop", "connectivity", "mixed"])
def test_global_native_mesh_cannot_hide_an_extra_type_or_missing_element(global_change):
    packet, after, groups = fixture()
    native = FakeNative(packet, after)
    original = native.getElements
    def changed(dim, tag):
        types, ids, nodes = original(dim, tag)
        if tag == -1:
            if global_change == "drop":
                return types, [ids[0][1:]], [nodes[0][4:]]
            if global_change == "connectivity":
                nodes = [nodes[0].copy()]
                nodes[0][0] = nodes[0][1]
            else:
                return types + [11], ids + [np.array([777])], nodes + [np.arange(1, 11)]
        return types, ids, nodes
    native.getElements = changed
    with pytest.raises(ValueError, match="global native|supported first-order"):
        m.extract_mesh_packet(native, {"after": after}, LIMITS)


def test_import_has_no_native_or_solver_entry_point():
    import ast
    tree = ast.parse(Path(m.__file__).read_text())
    imported = {name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
    assert "gmsh" not in imported and "skfem" not in imported
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr in ("initialize", "generate", "optimize", "solve") for n in ast.walk(tree))


def test_induced_facet_orientation_is_checked_independently():
    with pytest.raises(ValueError, match="orientations"):
        m._facet_incidence(np.array([[0, 1, 2, 3], [0, 1, 2, 4]]))
    faces, owners, starts, counts, paired = m._facet_incidence(np.array([[0, 1, 2, 3], [0, 2, 1, 4]]))
    assert len(paired) == 1
    assert sorted(counts.tolist()) == [1, 1, 1, 1, 1, 1, 2]


def test_nonmanifold_facet_rejected():
    with pytest.raises(ValueError, match="nonmanifold"):
        m._facet_incidence(np.array([[0, 1, 2, 3], [0, 2, 1, 4], [0, 1, 2, 5]]))


@pytest.mark.parametrize("column", [1, 2, 3, 4, 5])
def test_native_reference_element_contract(column):
    packet, after, groups = fixture()
    native = FakeNative(packet, after)
    original = native.getElementProperties
    def changed(kind):
        values = list(original(kind))
        values[column] = np.ones(12) if column == 4 else 7
        return tuple(values)
    native.getElementProperties = changed
    with pytest.raises(ValueError, match="reference element"):
        m.extract_mesh_packet(native, {"after": after}, LIMITS)


@pytest.mark.parametrize("scale", [1e-3, 3.])
def test_coordinate_measure_and_jacobian_units_stay_consistent(scale):
    packet, after, groups = fixture()
    packet["coordinates_mm"] *= scale
    packet["min_det_jac_mm3"] *= scale**3
    for dim in ("2", "3"):
        for record in after[dim]:
            record["bbox_mm"] = [v*scale for v in record["bbox_mm"]]
            record["measure_native"] *= scale**int(dim)
    result = audit(packet, after, groups)[1]
    assert sum(result["cad_volume_mm3"].values()) == pytest.approx(43*scale**3)
    assert sum(result["cad_surface_mm2"].values()) == pytest.approx(90*scale**2)


def test_neumann_only_mesh_component_rejected():
    packet, after, groups = fixture()
    # Add one disconnected, fully valid unit cube with no terminal label.
    # CAD-volume/face sums and incidence remain consistent, so only the mesh
    # component check can reject this fixture's unanchored component.
    xyz = packet["coordinates_mm"]
    old_tags = packet["node_tags"]
    cube_tets = packet["tetrahedron_nodes"][:6]
    used = np.unique(cube_tets)
    cube_xyz = xyz[np.searchsorted(old_tags, used)] + [5., 0., 0.]
    new_tags = 10**14 + np.arange(1, len(used)+1)
    new_tets = new_tags[np.searchsorted(used, cube_tets)]
    facet_counts = {}
    for tet in new_tets:
        for face in itertools.combinations(tet.tolist(), 3):
            key = tuple(sorted(face))
            facet_counts[key] = facet_counts.get(key, 0)+1
    new_tri, new_face_ids, surfaces = [], [], {}
    for face, count in facet_counts.items():
        if count != 1:
            continue
        pts = cube_xyz[np.searchsorted(new_tags, face)]
        box = tuple(v for lo, hi in zip(pts.min(axis=0), pts.max(axis=0)) for v in (lo, hi))
        if box not in surfaces:
            surfaces[box] = {"tag": 1000+len(surfaces), "bbox_mm": list(box), "measure_native": 1., "upward": [37]}
        new_tri.append(face)
        new_face_ids.append(surfaces[box]["tag"])
    extra = {"node_tags": new_tags, "coordinates_mm": cube_xyz,
        "tetrahedron_tags": 10**14+np.arange(1, 7), "tetrahedron_nodes": new_tets,
        "tetrahedron_volumes": np.full(6, 37), "min_sicn": np.full(6, .5), "min_det_jac_mm3": np.ones(6),
        "triangle_tags": 10**15+np.arange(1, 13), "triangle_nodes": np.array(new_tri), "triangle_faces": np.array(new_face_ids)}
    for name in packet:
        packet[name] = np.concatenate([packet[name], extra[name]], axis=0)
    after["3"].append({"tag": 37, "measure_native": 1., "bbox_mm": [5, 6, 0, 1, 0, 1]})
    after["2"].extend(surfaces.values())
    groups["outer"].extend(r["tag"] for r in surfaces.values())
    with pytest.raises(ValueError, match="component has no terminal"):
        audit(packet, after, groups)


@pytest.mark.parametrize("prefix", ["tetrahedron", "triangle"])
def test_repeated_vertex_rejected(prefix):
    packet, after, groups = fixture()
    packet[prefix + "_nodes"][0, 1] = packet[prefix + "_nodes"][0, 0]
    with pytest.raises(ValueError, match="repeats a vertex"):
        audit(packet, after, groups)


def test_element_ids_unique_across_dimensions():
    packet, after, groups = fixture()
    packet["triangle_tags"][0] = packet["tetrahedron_tags"][0]
    with pytest.raises(ValueError, match="reused across dimensions"):
        audit(packet, after, groups)


def test_packet_is_not_modified_by_audit():
    packet, after, groups = fixture()
    before = copy.deepcopy(packet)
    audit(packet, after, groups)
    for key in packet:
        assert np.array_equal(packet[key], before[key])
