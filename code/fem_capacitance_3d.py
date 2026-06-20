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

EPS0 = 8.854187817e-12   # F/m


def _build_mesh(layout, eps_r=4.2, pad_mm=8.0, refine=0):
    """gmsh OCC: air box + pri/sec conductor boxes (fragmented, tagged).
    Returns (skfem MeshTet, element_region array: 0=air,1=pri,2=sec)."""
    import gmsh
    from skfem import MeshTet
    import tempfile, os
    trs = layout["traces"]
    xs = [t.get("x0", 0.0) for t in trs] + [t.get("x0", 0.0) + t["length_mm"] for t in trs]
    ys = [t.get("y0", 0.0) for t in trs] + [t.get("y0", 0.0) + t["width_mm"] for t in trs]
    zs = [t.get("z_mm", (t["layer"] + 0.5) * 0.2) for t in trs] + \
         [t.get("z_mm", (t["layer"] + 0.5) * 0.2) + t.get("thick_mm", 0.07) for t in trs]
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
    for t in trs:
        net = t.get("net")
        if net not in ("pri", "sec"):
            continue
        bx = occ.addBox(t.get("x0", 0.0), t.get("y0", 0.0),
                        t.get("z_mm", (t["layer"] + 0.5) * 0.2),
                        t["length_mm"], t["width_mm"], t.get("thick_mm", 0.07))
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
        for t in trs:
            if t.get("net") not in ("pri", "sec"):
                continue
            cx = t.get("x0", 0.0); cy = t.get("y0", 0.0)
            cz = t.get("z_mm", (t["layer"] + 0.5) * 0.2)
            if (cx - 1e-3 <= c[0] <= cx + t["length_mm"] + 1e-3 and
                cy - 1e-3 <= c[1] <= cy + t["width_mm"] + 1e-3 and
                cz - 1e-3 <= c[2] <= cz + t.get("thick_mm", 0.07) + 1e-3):
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


def fem_cps_3d(layout, eps_r=4.2, refine=0):
    """3-D electrostatic C_ps (pF) between the primary and secondary windings."""
    import skfem
    from skfem import Basis, ElementTetP1, BilinearForm
    from skfem.helpers import dot, grad
    if not any(t.get("net") == "pri" for t in layout["traces"]) or \
       not any(t.get("net") == "sec" for t in layout["traces"]):
        return None
    try:                          # gmsh fails to mesh intersecting (invalid) boxes
        m, elem_region = _build_mesh(layout, eps_r=eps_r, refine=refine)
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
    return 2.0 * W * 1e12                          # C = 2W/V^2 (V=1) -> pF


def parallel_plate_pf(area_mm2, gap_mm, eps_r=4.2):
    return eps_r * EPS0 * (area_mm2 * 1e-6) / (gap_mm * 1e-3) * 1e12


if __name__ == "__main__":
    # parallel-plate validation: 40x5 mm plates, 0.11 mm gap, eps_r=4.2
    lay = {"traces": [
        {"x0": 0, "y0": 0, "z_mm": 0.10, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 0, "net": "pri"},
        {"x0": 0, "y0": 0, "z_mm": 0.28, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 1, "net": "sec"},
    ]}
    truth = parallel_plate_pf(40*5, 0.28-0.17, 4.2)
    for r in (0, 1):
        c = fem_cps_3d(lay, eps_r=4.2, refine=r)
        print("refine=%d -> Cps=%.2f pF (parallel-plate truth ~%.1f pF)" % (r, c if c else -1, truth))
