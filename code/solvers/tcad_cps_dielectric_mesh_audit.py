"""Dielectric tetrahedron/boundary audit helpers, without a native entry point.

Real arrays may only be collected/replayed by a separately guarded SLURM worker.
Small hand-constructed arrays and fake-native readers are used in unit tests.
No Gmsh initialization, mesh generation, field assembly or solving occurs here.
"""
from __future__ import annotations
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from tcad_cps_dielectric_cad_metadata import review_report

SCHEMA = "pcb-gnn.dielectric-boundary-mesh.v1"
ARRAY_DTYPES = {
    "node_tags": "<i8", "coordinates_mm": "<f8",
    "tetrahedron_tags": "<i8", "tetrahedron_nodes": "<i8", "tetrahedron_volumes": "<i8",
    "triangle_tags": "<i8", "triangle_nodes": "<i8", "triangle_faces": "<i8",
    "min_sicn": "<f8", "min_det_jac_mm3": "<f8",
}
GROUPS = ("primary", "secondary", "outer", "internal_dielectric")


def integers(value, width=None):
    import numpy as np
    a = np.asarray(value)
    if (not np.issubdtype(a.dtype, np.integer) or a.ndim != (1 if width is None else 2)
            or not len(a) or (width is not None and a.shape[1] != width)
            or a.min() <= 0 or a.max() > np.iinfo(np.int64).max):
        raise ValueError("nonempty positive int64-compatible tags/connectivity required")
    return a.astype(np.int64, copy=False)


def reals(value, shape):
    import numpy as np
    a = np.asarray(value)
    if (a.dtype.kind not in "fiu" or a.shape != shape or not np.isfinite(a).all()):
        raise ValueError("finite real array of the declared shape required")
    return a.astype(np.float64, copy=False)


def unique_tags(a):
    import numpy as np
    if len(np.unique(a)) != len(a):
        raise ValueError("duplicate native element/node tag")


def row_order(a):
    import numpy as np
    return np.lexsort(tuple(a[:, i] for i in reversed(range(a.shape[1]))))


def canonical_packet(packet, limits):
    """Normalize only record ordering; never flip, repair or drop an element."""
    import numpy as np
    if set(packet) != set(ARRAY_DTYPES):
        raise ValueError("mesh packet fields differ from schema")
    out = {}
    for prefix, width, cap in (("node", None, "mesh_nodes_max"),
                               ("tetrahedron", 4, "mesh_tetrahedra_max"),
                               ("triangle", 3, "mesh_triangles_max")):
        ids = integers(packet[prefix + "_tags"])
        if type(limits[cap]) is not int or not 0 < len(ids) <= limits[cap]:
            raise ValueError("mesh entity count outside cap")
        unique_tags(ids)
        order = np.argsort(ids, kind="stable")
        out[prefix + "_tags"] = ids[order]
        if width is None:
            out["coordinates_mm"] = reals(packet["coordinates_mm"], (len(ids), 3))[order]
        else:
            nodes = integers(packet[prefix + "_nodes"], width)
            entities = integers(packet[prefix + ("_volumes" if width == 4 else "_faces")])
            if len(nodes) != len(ids) or len(entities) != len(ids):
                raise ValueError("mesh element/connectivity/entity lengths differ")
            ordered = np.sort(nodes, axis=1)
            if np.any(ordered[:, 1:] == ordered[:, :-1]):
                raise ValueError("element repeats a vertex")
            ordered = ordered[row_order(ordered)]
            if np.any(np.all(ordered[1:] == ordered[:-1], axis=1)):
                raise ValueError("duplicate element connectivity")
            out[prefix + "_nodes"] = nodes[order]
            out[prefix + ("_volumes" if width == 4 else "_faces")] = entities[order]
        if width == 4:
            for name in ("min_sicn", "min_det_jac_mm3"):
                out[name] = reals(packet[name], (len(ids),))[order]
    if np.intersect1d(out["tetrahedron_tags"], out["triangle_tags"]).size:
        raise ValueError("native element tag reused across dimensions")
    return out


def packet_sha256(packet):
    """Exact canonical arrays, with labelled little-endian dtype/shape headers."""
    import numpy as np
    digest = hashlib.sha256((SCHEMA + "\0").encode())
    for name, dtype in ARRAY_DTYPES.items():
        a = np.ascontiguousarray(packet[name], dtype=dtype)
        header = json.dumps({"name": name, "dtype": a.dtype.str, "shape": list(a.shape)},
                            sort_keys=True, separators=(",", ":"))
        digest.update(header.encode() + b"\0")
        digest.update(memoryview(a).cast("B"))
    return digest.hexdigest()


def _indices(nodes, connectivity):
    import numpy as np
    indices = np.searchsorted(nodes, connectivity)
    if np.any(indices == len(nodes)) or np.any(nodes[indices] != connectivity):
        raise ValueError("element references an unknown node tag")
    return indices


def _close(actual, expected, cfg):
    return math.isclose(actual, expected, rel_tol=cfg["measure_rtol"],
                        abs_tol=cfg["measure_atol_native"])


def _facet_incidence(t):
    import numpy as np
    # Four outward faces for a positive, first-order (0,1,2,3) tetrahedron.
    faces = np.concatenate([t[:, idx] for idx in ([1, 2, 3], [0, 3, 2], [0, 1, 3], [0, 2, 1])])
    parity = sum((faces[:, i] > faces[:, j]).astype(np.int8) for i, j in ((0, 1), (0, 2), (1, 2))) % 2
    faces.sort(axis=1)
    order = row_order(faces)
    faces, parity = faces[order], parity[order]
    owner = order % len(t)
    starts = np.r_[0, np.flatnonzero(np.any(faces[1:] != faces[:-1], axis=1))+1]
    counts = np.diff(np.r_[starts, len(faces)])
    if np.any(counts > 2):
        raise ValueError("nonmanifold tetrahedral facet")
    paired = starts[counts == 2]
    if np.any(parity[paired] == parity[paired+1]):
        raise ValueError("internal facet induced orientations do not cancel")
    return faces, owner, starts, counts, paired


def _audit_packet(packet, after, groups, cfg, limits):
    """Array audit against already-replayed CAD; private for synthetic fixtures.

    Tetrahedra keep Gmsh's local vertex order. Facet matching is unoriented,
    while the two induced orientations of every internal facet must cancel.
    This is not an exhaustive geometric intersection or field-accuracy proof.
    """
    import numpy as np
    a = canonical_packet(packet, limits)
    volumes = {int(r["tag"]): r for r in after["3"]}
    surfaces = {int(r["tag"]): r for r in after["2"]}
    if set(groups) != set(GROUPS) or any(not isinstance(v, list) for v in groups.values()):
        raise ValueError("boundary group schema mismatch")
    labels = [f for name in GROUPS for f in groups[name]]
    if (any(type(f) is not int or f <= 0 for f in labels) or len(labels) != len(set(labels))
            or set(labels) != set(surfaces) or any(not groups[n] for n in GROUPS[:3])):
        raise ValueError("missing, repeated or unknown CAD boundary group")
    if (set(a["tetrahedron_volumes"].tolist()) != set(volumes)
            or set(a["triangle_faces"].tolist()) != set(surfaces)):
        raise ValueError("mesh does not cover exactly retained CAD volumes/faces")
    # The public adapter obtains this incidence from full CAD replay.
    for face, r in surfaces.items():
        up = r["upward"]
        expected = 2 if face in groups["internal_dielectric"] else 1
        if len(up) != expected or len(set(up)) != expected or not set(up) <= set(volumes):
            raise ValueError("CAD boundary group/owner mismatch")
    xyz = a["coordinates_mm"]
    t = _indices(a["node_tags"], a["tetrahedron_nodes"])
    tri = _indices(a["node_tags"], a["triangle_nodes"])
    if len(np.unique(t)) != len(xyz):
        raise ValueError("mesh contains orphan nodes")
    if (np.any(a["min_sicn"] <= 0) or np.any(a["min_sicn"] > cfg["sicn_max"])
            or np.any(a["min_det_jac_mm3"] <= 0)):
        raise ValueError("native signed quality/Jacobian gate failed")
    edge1, edge2, edge3 = (xyz[t[:, j]] - xyz[t[:, 0]] for j in (1, 2, 3))
    determinant = np.einsum("ij,ij->i", edge1, np.cross(edge2, edge3))
    if not np.isfinite(determinant).all() or np.any(determinant <= 0):
        raise ValueError("independent signed tetrahedron determinant gate failed")
    if not np.allclose(determinant, a["min_det_jac_mm3"], rtol=cfg["jacobian_rtol"], atol=0):
        raise ValueError("native and independently reconstructed Jacobians disagree")
    del edge1, edge2, edge3
    volume_measures = {}
    tolerance = cfg["coordinate_atol_mm"]
    for tag, record in volumes.items():
        selected = a["tetrahedron_volumes"] == tag
        measure = float(np.sum(determinant[selected], dtype=np.float64)/6)
        if not _close(measure, record["measure_native"], cfg):
            raise ValueError("tetrahedron volume sum differs from retained CAD volume")
        points = xyz[np.unique(t[selected])]
        box = record["bbox_mm"]
        if np.any(points < np.asarray(box[::2])-tolerance) or np.any(points > np.asarray(box[1::2])+tolerance):
            raise ValueError("tetrahedron vertices outside owning CAD volume bounds")
        volume_measures[str(tag)] = measure
    faces, owner, starts, counts, paired = _facet_incidence(t)
    cross_volume = a["tetrahedron_volumes"][owner[paired]] != a["tetrahedron_volumes"][owner[paired+1]]
    required = np.sort(np.r_[starts[counts == 1], paired[cross_volume]])
    tri_sorted = np.sort(tri, axis=1)
    tri_order = row_order(tri_sorted)
    if not np.array_equal(faces[required], tri_sorted[tri_order]):
        raise ValueError("native triangles do not exactly cover exterior/cross-volume tetrahedral facets")
    # Exact join above gives one/two tetrahedral owners for each native face.
    first = owner[required]
    second = np.full(len(required), -1, dtype=np.int64)
    internal = np.isin(required, paired, assume_unique=True)
    second[internal] = owner[required[internal]+1]
    face_labels = a["triangle_faces"][tri_order]
    area_measures = {}
    for tag, record in surfaces.items():
        mask = face_labels == tag
        actual_first = a["tetrahedron_volumes"][first[mask]]
        expected = sorted(record["upward"])
        if len(expected) == 1:
            if np.any(second[mask] != -1) or np.any(actual_first != expected[0]):
                raise ValueError("surface triangle has wrong dielectric owner")
        else:
            if np.any(second[mask] < 0):
                raise ValueError("internal CAD interface has an exterior triangle")
            pairs = np.sort(np.column_stack([actual_first, a["tetrahedron_volumes"][second[mask]]]), axis=1)
            if np.any(pairs != expected):
                raise ValueError("internal CAD interface has wrong volume pair")
        local = tri[tri_order[mask]]
        points = xyz[np.unique(local)]
        box = record["bbox_mm"]
        if np.any(points < np.asarray(box[::2])-tolerance) or np.any(points > np.asarray(box[1::2])+tolerance):
            raise ValueError("triangle vertices outside owning CAD surface bounds/plane")
        edges1, edges2 = xyz[local[:, 1]]-xyz[local[:, 0]], xyz[local[:, 2]]-xyz[local[:, 0]]
        areas = np.linalg.norm(np.cross(edges1, edges2), axis=1)/2
        measure = float(np.sum(areas, dtype=np.float64))
        if not np.isfinite(areas).all() or np.any(areas <= 0) or not _close(measure, record["measure_native"], cfg):
            raise ValueError("triangle area sum differs from retained CAD surface")
        area_measures[str(tag)] = measure
    group_nodes = {name: np.unique(tri[np.isin(a["triangle_faces"], tags)]) for name, tags in groups.items()}
    if any(np.intersect1d(group_nodes[left], group_nodes[right]).size for left, right in
           (("primary", "secondary"), ("primary", "outer"), ("secondary", "outer"))):
        raise ValueError("terminal nodes overlap another terminal or the outer boundary")
    # A disconnected tetrahedral component without a terminal would have a
    # Neumann nullspace even if its volume's CAD metadata looked connected.
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    graph = coo_matrix((np.ones(len(paired), dtype=np.int8),
                        (owner[paired], owner[paired+1])), shape=(len(t), len(t))).tocsr()
    n_components, component = connected_components(graph, directed=False)
    terminal = np.isin(face_labels, groups["primary"] + groups["secondary"])
    if len(np.unique(component[first[terminal]])) != n_components:
        raise ValueError("tetrahedral component has no terminal boundary")
    # Return small diagnostics, plus canonical buffers for a
    # future guarded worker to archive. Do not instantiate/reorient MeshTet.
    report = {"schema": SCHEMA, "packet_sha256": packet_sha256(a),
        "mesh_nodes": len(xyz), "mesh_tetrahedra": len(t), "mesh_triangles": len(tri),
        "exterior_facets": int(np.count_nonzero(counts == 1)),
        "interior_facets": int(len(paired)), "cross_volume_facets": int(np.count_nonzero(cross_volume)),
        "tetrahedral_components": int(n_components), "cad_volume_mm3": volume_measures,
        "cad_surface_mm2": area_measures, "minimum_sicn": float(a["min_sicn"].min()),
        "minimum_native_det_jac_mm3": float(a["min_det_jac_mm3"].min()),
        "minimum_independent_det_jac_mm3": float(determinant.min()),
        "boundary_groups": {name: {"faces": list(tags), "triangles": int(np.isin(a["triangle_faces"], tags).sum()),
            "nodes": int(len(group_nodes[name]))} for name, tags in groups.items()},
        "boundary_contract_passed": True, "field_solver_executed": False,
        "numerical_accuracy_qualified": False, "reference_qualified": False,
        "training_may_start": False, "claim_eligible": False}
    return a, report


def audit_cad_mesh(packet, cad_report, layout, pad, cad_cfg, cad_options, cfg, limits):
    """Replay CAD before binding every retained volume and surface to the mesh."""
    summary = review_report(cad_report, layout, pad, cad_cfg, cad_options)
    groups = {name: summary[name + "_faces"] for name in GROUPS}
    return _audit_packet(packet, cad_report["after"], groups, cfg, limits)


def _native_block(native, dim, tag, count_max):
    """Reject unsupported, missing or mixed types instead of silently skipping."""
    kinds, element_tags, element_nodes = native.model.mesh.getElements(dim, tag)
    kind, width = (4, 4) if dim == 3 else (2, 3)
    kinds = integers(kinds)
    if len(kinds) != 1 or kinds[0] != kind or len(element_tags) != 1 or len(element_nodes) != 1:
        raise ValueError("native entity must have exactly one supported first-order element type")
    ids = integers(element_tags[0])
    if len(ids) > count_max:
        raise ValueError("native extraction count exceeds cap")
    flat = integers(element_nodes[0])
    if len(flat) != width*len(ids):
        raise ValueError("native connectivity size differs from element count")
    unique_tags(ids)
    return ids, flat.reshape(-1, width)


def extract_mesh_packet(native, cad_report, limits):
    """Read an existing native mesh; caller owns SLURM/runtime/source guards.

    No native import/session creation is present. Fake API objects exercise this
    helper on login. Real extraction is compute-only, including any replay.
    """
    import numpy as np
    for kind, dim, count, reference in (
            (4, 3, 4, [0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1.]),
            (2, 2, 3, [0., 0., 1., 0., 0., 1.])):
        _, dimension, order, n_nodes, coords, primary_nodes = native.model.mesh.getElementProperties(kind)
        if (dimension != dim or order != 1 or n_nodes != count or primary_nodes != count
                or not np.array_equal(coords, reference)):
            raise ValueError("native reference element differs from affine simplex contract")
    node_tags, coordinates, _ = native.model.mesh.getNodes(-1, -1, False, False)
    node_tags = integers(node_tags)
    if len(node_tags) > limits["mesh_nodes_max"]:
        raise ValueError("native node count exceeds cap")
    unique_tags(node_tags)
    coordinates = reals(coordinates, (3*len(node_tags),)).reshape(-1, 3)
    packet = {"node_tags": node_tags, "coordinates_mm": coordinates}
    for dim, prefix, entity_name, cap in ((3, "tetrahedron", "volumes", "mesh_tetrahedra_max"),
                                         (2, "triangle", "faces", "mesh_triangles_max")):
        entities = [r["tag"] for r in cad_report["after"][str(dim)]]
        actual = native.model.getEntities(dim)
        if any(len(pair) != 2 or pair[0] != dim or type(pair[1]) is not int for pair in actual):
            raise ValueError("unexpected native mesh entity dimension/type")
        if sorted(pair[1] for pair in actual) != sorted(entities):
            raise ValueError("native mesh CAD entities differ from retained report")
        ids, nodes, owners, count = [], [], [], 0
        for tag in entities:
            block_ids, block_nodes = _native_block(native, dim, tag, limits[cap]-count)
            count += len(block_ids)
            ids.append(block_ids)
            nodes.append(block_nodes)
            owners.append(np.full(len(block_ids), tag, dtype=np.int64))
        all_ids, all_nodes = np.concatenate(ids), np.concatenate(nodes)
        unique_tags(all_ids)
        global_ids, global_nodes = _native_block(native, dim, -1, limits[cap])
        order, global_order = np.argsort(all_ids), np.argsort(global_ids)
        if not np.array_equal(all_ids[order], global_ids[global_order]) or not np.array_equal(all_nodes[order], global_nodes[global_order]):
            raise ValueError("per-entity extraction differs from global native mesh")
        packet[prefix + "_tags"] = all_ids
        packet[prefix + "_nodes"] = all_nodes
        packet[prefix + "_" + entity_name] = np.concatenate(owners)
    packet["min_sicn"] = native.model.mesh.getElementQualities(packet["tetrahedron_tags"], "minSICN")
    packet["min_det_jac_mm3"] = native.model.mesh.getElementQualities(packet["tetrahedron_tags"], "minDetJac")
    return canonical_packet(packet, limits)
