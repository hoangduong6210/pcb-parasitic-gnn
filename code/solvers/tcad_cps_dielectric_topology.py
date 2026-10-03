"""Metadata-only interface classification for a proposed dielectric-only domain.

No CAD, meshing, field solving or numerical imports. The caller must independently
obtain complete native entity lists, fragment provenance and both directions of
incidence. In particular, outer_faces must come from geometric outer-box checks,
not from selecting all faces with one owner. This helper cannot verify geometry.
"""
from __future__ import annotations


def _tags(values, name, *, nonempty=True):
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name}: a list/tuple of positive integer tags is required")
    if any(type(tag) is not int or tag <= 0 for tag in values):
        raise ValueError(f"{name}: invalid native tag")
    tags = set(values)
    if len(tags) != len(values) or (nonempty and not tags):
        raise ValueError(f"{name}: duplicate or missing tags")
    return tags


def _incidence(mapping, keys, targets, name):
    if not isinstance(mapping, dict) or any(type(k) is not int for k in mapping):
        raise ValueError(f"{name}: integer-keyed incidence mapping required")
    if set(mapping) != keys:
        raise ValueError(f"{name}: exact entity coverage required")
    parsed = {k: _tags(v, name) for k, v in mapping.items()}
    if any(not v <= targets for v in parsed.values()):
        raise ValueError(f"{name}: unknown adjacent entity")
    return parsed


def classify_interfaces(*, all_volumes, all_faces, outer_descendants,
                        primary_descendants, secondary_descendants,
                        volume_faces, face_volumes, outer_faces):
    """Validate abstract fragmented-volume topology, not physical correctness.

    Descendant sets are already aggregated by input identity, not inferred from
    centroid position or output ordering. Inputs use unsigned native integer
    tags. Return sorted classifications and the expected retained incidence;
    a future guarded CAD adapter must check that incidence again after removal.
    """
    volumes = _tags(all_volumes, "all_volumes")
    faces = _tags(all_faces, "all_faces")
    air = _tags(outer_descendants, "outer_descendants")
    pri = _tags(primary_descendants, "primary_descendants")
    sec = _tags(secondary_descendants, "secondary_descendants")
    outer = _tags(outer_faces, "outer_faces")
    if air != volumes or not (pri | sec) <= volumes:
        raise ValueError("fragment provenance must cover exactly the enclosing domain")
    if pri & sec:
        raise ValueError("primary/secondary volume overlap")
    dielectric = air - pri - sec
    if not dielectric:
        raise ValueError("missing dielectric volume")
    if not outer <= faces:
        raise ValueError("unknown outer face")
    vf = _incidence(volume_faces, volumes, faces, "volume_faces")
    fv = _incidence(face_volumes, faces, volumes, "face_volumes")
    inverse = {face: set() for face in faces}
    for volume, boundary in vf.items():
        for face in boundary:
            inverse[face].add(volume)
    if inverse != fv:
        raise ValueError("boundary and adjacency incidence disagree")
    if any(len(owners) > 2 for owners in fv.values()):
        raise ValueError("nonmanifold face has more than two volume owners")

    labels = {v: "dielectric" if v in dielectric else "primary" if v in pri
              else "secondary" for v in volumes}
    groups = {k: [] for k in ("primary", "secondary", "outer",
                              "internal_dielectric", "internal_metal")}
    for face, owners in sorted(fv.items()):
        kinds = {labels[v] for v in owners}
        if face in outer:
            if len(owners) != 1 or kinds != {"dielectric"}:
                raise ValueError("outer face must have exactly one dielectric owner")
            group = "outer"
        elif len(owners) == 1:
            raise ValueError("unclassified exterior face or exposed conductor")
        elif kinds == {"primary", "secondary"}:
            raise ValueError("primary/secondary shared face")
        elif kinds == {"dielectric", "primary"}:
            group = "primary"
        elif kinds == {"dielectric", "secondary"}:
            group = "secondary"
        elif kinds == {"dielectric"}:
            group = "internal_dielectric"
        else:
            group = "internal_metal"
        groups[group].append(face)
    if not groups["primary"] or not groups["secondary"]:
        raise ValueError("both terminal interfaces must be nonempty")

    # Each disconnected dielectric component needs a Dirichlet boundary;
    # an outer-Neumann-only component would leave a constant nullspace.
    adjacency = {v: set() for v in dielectric}
    anchored = set()
    for face in groups["internal_dielectric"]:
        left, right = sorted(fv[face])
        adjacency[left].add(right)
        adjacency[right].add(left)
    for face in groups["primary"] + groups["secondary"]:
        anchored.update(fv[face] & dielectric)
    remaining = set(dielectric)
    while remaining:
        pending = [min(remaining)]
        component = set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(adjacency[current] - component)
        remaining.difference_update(component)
        if not component & anchored:
            raise ValueError("dielectric component has no terminal boundary")

    retained = {f: sorted(v & dielectric) for f, v in sorted(fv.items()) if v & dielectric}
    return {
        "schema": "pcb-gnn.dielectric-topology-plan.v1",
        "scope": "abstract face-volume metadata only; geometry and removal unverified",
        "volumes": {"dielectric": sorted(dielectric), "primary": sorted(pri), "secondary": sorted(sec)},
        "faces": groups,
        "expected_retained_face_volumes": retained,
        "expected_retained_volume_faces": {v: sorted(vf[v]) for v in sorted(dielectric)},
        "geometry_verified": False,
        "removal_verified": False,
        "mesh_feasible": False,
        "field_solver_executed": False,
        "reference_qualified": False,
        "training_may_start": False,
        "claim_eligible": False,
    }
