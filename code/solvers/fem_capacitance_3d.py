"""
fem_capacitance_3d.py — 3-D inter-winding capacitance C_ps via a scikit-fem
electrostatic FEM (BSD, Python-native; no subprocess, no BEM panel orientation).

Robust where the surface-BEM solvers (FastCap/FasterCap) were not: a VOLUME FEM
of the Laplace problem div(eps grad phi)=0 on a gmsh tet mesh of the air box with
the real pri/sec conductor boxes embedded (true 3-D registration + fringing, thin
gaps resolved by the conforming mesh). Dirichlet phi=1V on every primary node,
phi=0V on every secondary node; the inter-winding C_ps = 2W/V^2 with
W = 1/2 * integral(eps |grad phi|^2) over the dielectric.

Validated against the parallel-plate analytic eps0*eps_r*A/d.
"""
from __future__ import annotations
import numpy as np

from geometry_contract import trace_box, validate_layout

EPS0 = 8.854187817e-12   # F/m


def _build_mesh(layout, eps_r=4.2, pad_mm=8.0, refine=0):
    """gmsh OCC: air box + pri/sec conductor boxes (fragmented, tagged).
    Returns (skfem MeshTet, element_region array: 0=air,1=pri,2=sec)."""
    import gmsh
    from skfem import MeshTet
    import tempfile, os
    validate_layout(layout)
    trs = layout["traces"]
    boxes = [trace_box(layout, trace) for trace in trs]
    xs = [box[0] for box in boxes] + [box[1] for box in boxes]
    ys = [box[2] for box in boxes] + [box[3] for box in boxes]
    zs = [box[4] for box in boxes] + [box[5] for box in boxes]
    x0, x1 = min(xs) - pad_mm, max(xs) + pad_mm
    y0, y1 = min(ys) - pad_mm, max(ys) + pad_mm
    z0, z1 = min(zs) - pad_mm, max(zs) + pad_mm

    if gmsh.isInitialized():     # clean any stuck state from a prior failed solve
        gmsh.finalize()
    gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("cps")
    occ = gmsh.model.occ
    air = occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
    pri_boxes, sec_boxes = [], []
    for t, box in zip(trs, boxes):
        net = t.get("net")
        if net not in ("pri", "sec"):
            continue
        bx = occ.addBox(
            box[0], box[2], box[4],
            box[1] - box[0], box[3] - box[2], box[5] - box[4],
        )
        (pri_boxes if net == "pri" else sec_boxes).append(bx)
    occ.synchronize()
    # FUSE each winding into one conductor (resolves same-net same-layer overlaps,
    # which are connected copper, not invalid geometry, and makes a clean 2-conductor problem)
    def fuse(boxes):
        if not boxes:
            return []
        if len(boxes) == 1:
            return [(3, boxes[0])]
        res, _ = occ.fuse([(3, boxes[0])], [(3, b) for b in boxes[1:]])
        return res
    pri_f = fuse(pri_boxes); sec_f = fuse(sec_boxes)
    occ.synchronize()
    # fragment so the air mesh conforms to every conductor surface
    out, omap = occ.fragment([(3, air)], pri_f + sec_f)
    occ.synchronize()
    # identify which fragment volume is which conductor by centroid-in-box test
    vols = [v[1] for v in gmsh.model.getEntities(3)]
    def centroid(v):
        return np.array(gmsh.model.occ.getCenterOfMass(3, v))
    region_of_vol = {}
    for v in vols:
        c = centroid(v); tag = 0   # gmsh model units are mm here
        for t, box in zip(trs, boxes):
            if t.get("net") not in ("pri", "sec"):
                continue
            if (box[0] - 1e-3 <= c[0] <= box[1] + 1e-3 and
                box[2] - 1e-3 <= c[1] <= box[3] + 1e-3 and
                box[4] - 1e-3 <= c[2] <= box[5] + 1e-3):
                tag = 1 if t["net"] == "pri" else 2; break
        region_of_vol[v] = tag
    # mesh size: fine near the (thin) gaps
    gaps = sorted(set(round(z, 4) for z in zs))
    dz = min((gaps[i+1]-gaps[i]) for i in range(len(gaps)-1)) if len(gaps) > 1 else 0.2
    h = max(dz * 0.8, 0.05)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h)
    gmsh.option.setNumber("Mesh.MeshSizeMax", max(h * 12, 2.0))
    for _ in range(refine):
        gmsh.option.setNumber("Mesh.MeshSizeMax", gmsh.option.getNumber("Mesh.MeshSizeMax")*0.6)
    gmsh.model.mesh.generate(3)
    tmp = tempfile.mktemp(suffix=".msh"); gmsh.write(tmp)
    # map gmsh element tags to regions via volume membership
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    coords = np.array(node_coords).reshape(-1, 3).T * 1e-3  # mm -> m (SI energy)
    id2idx = {int(t): i for i, t in enumerate(node_tags)}
    elem_conn = []; elem_region = []
    for v in vols:
        etypes, etags, enodes = gmsh.model.mesh.getElements(3, v)
        for et, en in zip(etypes, enodes):
            if et != 4:   # 4-node tet
                continue
            conn = np.array(en, dtype=np.int64).reshape(-1, 4)
            for row in conn:
                elem_conn.append([id2idx[int(t)] for t in row])
                elem_region.append(region_of_vol[v])
    gmsh.finalize()
    t = np.array(elem_conn).T
    m = MeshTet(coords, t)
    return m, np.array(elem_region)


def fem_cps_3d_diagnostics(layout, eps_r=4.2, refine=0, pad_mm=8.0):
    """Return C_ps and mesh diagnostics for an explicit mesh/domain setting."""
    import skfem
    from skfem import Basis, ElementTetP1, BilinearForm
    from skfem.helpers import dot, grad
    if not any(t.get("net") == "pri" for t in layout["traces"]) or \
       not any(t.get("net") == "sec" for t in layout["traces"]):
        return None
    try:                          # gmsh fails to mesh intersecting (invalid) boxes
        m, elem_region = _build_mesh(
            layout, eps_r=eps_r, refine=refine, pad_mm=pad_mm
        )
    except Exception:
        try:
            import gmsh
            if gmsh.isInitialized():
                gmsh.finalize()
        except Exception:
            pass
        return None
    basis = Basis(m, ElementTetP1())

    # uniform dielectric: conductor interiors have grad(phi)=0 (all nodes fixed to
    # one potential), so they add no energy and a constant eps is exact here.
    @BilinearForm
    def laplace(u, v, _):
        return dot(grad(u), grad(v))
    K = laplace.assemble(basis)

    # Dirichlet: nodes touched by pri elements -> 1V, sec elements -> 0V
    pri_nodes = np.unique(m.t[:, elem_region == 1].ravel()) if (elem_region == 1).any() else np.array([], int)
    sec_nodes = np.unique(m.t[:, elem_region == 2].ravel()) if (elem_region == 2).any() else np.array([], int)
    sec_nodes = np.setdiff1d(sec_nodes, pri_nodes)
    if len(pri_nodes) == 0 or len(sec_nodes) == 0:
        return None
    u = basis.zeros(); u[pri_nodes] = 1.0; u[sec_nodes] = 0.0
    D = np.concatenate([pri_nodes, sec_nodes])
    u = skfem.solve(*skfem.condense(K, basis.zeros(), x=u, D=D))
    W = 0.5 * EPS0 * eps_r * float(u @ (K @ u))   # Joules (V=1, uniform eps)
    return {
        "cps_pf": 2.0 * W * 1e12,                 # C = 2W/V^2 (V=1) -> pF
        "mesh_nodes": int(m.p.shape[1]),
        "mesh_tetrahedra": int(m.t.shape[1]),
        "refine": int(refine),
        "pad_mm": float(pad_mm),
        "eps_r": float(eps_r),
    }


def fem_cps_3d(layout, eps_r=4.2, refine=0, pad_mm=8.0):
    """3-D electrostatic C_ps (pF) between the primary and secondary windings."""
    diagnostics = fem_cps_3d_diagnostics(
        layout, eps_r=eps_r, refine=refine, pad_mm=pad_mm
    )
    return diagnostics["cps_pf"] if diagnostics is not None else None


def parallel_plate_pf(area_mm2, gap_mm, eps_r=4.2):
    return eps_r * EPS0 * (area_mm2 * 1e-6) / (gap_mm * 1e-3) * 1e12


if __name__ == "__main__":
    # parallel-plate validation: 40x5 mm plates, 0.11 mm gap, eps_r=4.2
    lay = {
        "geometry_schema": "pcb-planar-active-legs.v3",
        "n_layers": 2, "board_w_mm": 45.0, "board_h_mm": 10.0,
        "stackup": {"layer_pitch_mm": 0.18, "layer_z0_mm": 0.10},
        "design_rules": {"same_layer_clearance_mm": 0.20, "board_edge_margin_mm": 0.0},
        "traces": [
            {"trace_id": "pri-0", "x0": 2, "y0": 2, "length_mm": 40,
             "width_mm": 5, "thick_mm": 0.07, "layer": 0, "net": "pri",
             "current_sign": 1},
            {"trace_id": "sec-0", "x0": 2, "y0": 2, "length_mm": 40,
             "width_mm": 5, "thick_mm": 0.07, "layer": 1, "net": "sec",
             "current_sign": 1},
        ],
    }
    truth = parallel_plate_pf(40*5, 0.28-0.17, 4.2)
    for r in (0, 1):
        c = fem_cps_3d(lay, eps_r=4.2, refine=r)
        print("refine=%d -> Cps=%.2f pF (parallel-plate truth ~%.1f pF)" % (r, c if c else -1, truth))
