"""Column construction helpers; real inputs require a guarded SLURM caller.

No native session, field assembly, file writes or executable mesh entry point.
Original planar arrays are never modified. All indices below are new volume
identities, not replacements for the source packet's native node tags.
"""
from fractions import Fraction
from collections import Counter
import math

from tcad_cps_column_contract import PRISM_PATTERN, coordinate, triangle_coordinates


class Columns:
    """Deterministic slab iterator using complete source ownership masks."""

    def __init__(self, packet, cad_report, plan, limits):
        import numpy as np
        from tcad_cps_column_mesh import canonical_packet, packet_sha256
        if any(type(limits[k]) is not int or limits[k] <= 0 for k in ("mesh_nodes_max","mesh_tetrahedra_max")):
            raise ValueError("positive integer volume caps required")
        self.packet = canonical_packet(packet, limits)
        if (plan["packet_sha256"] != packet_sha256(self.packet)
                or plan["planning_feasible"] is not True or plan["planar_mesh_validated"] is not True
                or set(plan["planning_checks"]) != {"node_upper_bound","tetrahedron_count","jacobian_condition_bound","prospective_mesh_volume"}
                or not all(v is True for v in plan["planning_checks"].values())):
            raise ValueError("column input lacks the matching complete prospective plan")
        self.xy = self.packet["coordinates_mm"][:, :2].copy()
        self.z = list(plan["vertical_axis"]["points_mm"])
        if (not all(coordinate(v) for v in self.z) or not 2 <= len(self.z) <= 4096
                or self.z != sorted(set(self.z)) or len(self.z) != plan["vertical_axis"]["point_count"]
                or len(self.z) != plan["capacity"]["vertical_points"]):
            raise ValueError("finite strictly ordered volume planes required")
        self.n = len(self.xy)
        self.full_nodes = self.n*len(self.z)
        if self.full_nodes != plan["capacity"]["column_node_upper_bound"] or self.full_nodes > limits["mesh_nodes_max"]:
            raise ValueError("full column node bound differs or exceeds cap")
        tags = self.packet["node_tags"]
        nodes = np.searchsorted(tags, self.packet["triangle_nodes"])
        if np.any(nodes == len(tags)) or np.any(tags[nodes] != self.packet["triangle_nodes"]):
            raise ValueError("unknown source planar node")
        self.triangles = np.sort(nodes, axis=1)
        self.area2 = [triangle_coordinates(self.xy[row].tolist())[1] for row in self.triangles]
        mapping = cad_report["fragment_map"]
        owners = {face: tuple(i for i, children in enumerate(mapping[1:]) if face in children)
                  for face in cad_report["fragment_output_surfaces"]}
        groups = {tuple(row["owners"]): row for row in plan["capacity"]["groups"]}
        self.masks = [owners[int(face)] for face in self.packet["triangle_surfaces"]]
        if set(self.masks) != set(groups) or len(groups) != len(plan["capacity"]["groups"]):
            raise ValueError("volume source ownership group coverage differs")
        boxes = cad_report["canonical_boxes_mm"]
        domain = cad_report["domain_box_mm"]
        if (self.z[0] != domain[4] or self.z[-1] != domain[5]
                or not {b[k] for b in boxes for k in (4,5)}.issubset(self.z)):
            raise ValueError("volume planes lose canonical conductor/domain faces")
        self.retained = {}
        for mask, group in groups.items():
            kept = [j for j, (lo, hi) in enumerate(zip(self.z, self.z[1:]))
                    if not any(boxes[i][4] <= lo and hi <= boxes[i][5] for i in mask)]
            if (not kept or kept != group["retained_z_intervals"]
                    or self.masks.count(mask) != group["planar_triangles"]):
                raise ValueError("canonical dielectric interval/triangle ownership differs")
            self.retained[mask] = set(kept)
        self.counts = [3*sum(j in self.retained[mask] for mask in self.masks) for j in range(len(self.z)-1)]
        self.tetrahedra = sum(self.counts)
        if (self.tetrahedra != plan["capacity"]["tetrahedra"] or not 0 < self.tetrahedra <= limits["mesh_tetrahedra_max"]
                or any(v <= 0 for v in self.counts)):
            raise ValueError("complete volume count/cap differs")

    def coordinates(self, ids):
        import numpy as np
        a = np.asarray(ids)
        if a.dtype.kind not in "iu" or np.any(a < 1) or np.any(a > self.full_nodes):
            raise ValueError("unknown generated column node identity")
        zero = a.astype(np.int64, copy=False)-1
        return np.concatenate((self.xy[zero % self.n], np.asarray(self.z)[zero // self.n][..., None]), axis=-1)

    def slab(self, index):
        """Generate positive local order by the frozen exact planar sign rule."""
        import numpy as np
        if type(index) is not int or not 0 <= index < len(self.counts):
            raise ValueError("invalid volume slab index")
        selected = np.asarray([i for i, mask in enumerate(self.masks) if index in self.retained[mask]], dtype=np.int64)
        row = self.triangles[selected]
        vertices = np.concatenate((row+index*self.n+1, row+(index+1)*self.n+1), axis=1)
        t = vertices[:, np.asarray(PRISM_PATTERN)].copy()
        negative = np.asarray([self.area2[i] < 0 for i in selected])
        t[negative] = t[negative][:, :, [0,2,1,3]]
        height = Fraction(self.z[index+1])-Fraction(self.z[index])
        expected = np.repeat([float(abs(self.area2[i])*height) for i in selected], 3)
        return t.reshape(-1, 4), expected


def boundary_surfaces(after, groups, boxes, domain, nets, cfg):
    """Bind retained rectangular native faces to original physical sides.

    Caller must replay the full 3D CAD report first. CAD internal subdivisions
    are not silently discarded: they need an explicit owner contract and are
    rejected by this adapter. The existing toy/sentinel CAD has no such faces.
    """
    if set(groups) != {"primary", "secondary", "outer", "internal_dielectric"} or groups["internal_dielectric"]:
        raise ValueError("internal CAD partitions require an explicit volume-owner contract")
    if len(nets) != len(boxes) or any(n not in ("pri", "sec") for n in nets):
        raise ValueError("original conductor terminal labels required")
    labels = [f for names in groups.values() for f in names]
    rows = after["2"]
    if (len(labels) != len(set(labels)) or set(labels) != {r["tag"] for r in rows}
            or any(not groups[name] for name in ("primary", "secondary", "outer"))):
        raise ValueError("complete disjoint nonempty CAD boundary groups required")
    tolerance = cfg["coordinate_atol_mm"]
    result = []
    edges = {r["tag"]:r for r in after["1"]}
    points = {r["tag"]:r for r in after["0"]}
    for r in rows:
        group = next(name for name, tags in groups.items() if r["tag"] in tags)
        if len(r["upward"]) != 1 or r["upward"][0] not in {v["tag"] for v in after["3"]}:
            raise ValueError("exterior CAD face needs one retained dielectric owner")
        candidates = [(-1, domain)] if group == "outer" else [(i,b) for i,b in enumerate(boxes)
            if nets[i] == ("pri" if group == "primary" else "sec")]
        b = r["bbox_mm"]
        matches = [(owner, side) for owner, box in candidates for side in range(6)
            if abs(b[2*(side//2)]-box[side]) <= tolerance and abs(b[2*(side//2)+1]-box[side]) <= tolerance
            and all(b[k] >= box[k]-tolerance and b[k+1] <= box[k+1]+tolerance for k in (0,2,4))]
        if len(matches) != 1:
            raise ValueError("CAD surface has missing/ambiguous canonical side")
        owner, side = matches[0]
        axis = side//2
        if len(r["boundary"]) != 4 or len(set(r["boundary"])) != 4 or not set(r["boundary"]) <= set(edges):
            raise ValueError("retained CAD face is not a four-edge rectangle")
        degree, directions, graph = Counter(),Counter(),{}
        for tag in r["boundary"]:
            edge = edges[tag]
            if len(edge["boundary"]) != 2 or len(set(edge["boundary"])) != 2 or not set(edge["boundary"]) <= set(points):
                raise ValueError("CAD rectangle edge endpoints differ")
            degree.update(edge["boundary"])
            left,right = edge["boundary"]
            graph.setdefault(left,set()).add(right)
            graph.setdefault(right,set()).add(left)
            active = [k//2 for k in (0,2,4) if edge["bbox_mm"][k+1]-edge["bbox_mm"][k] > 2*tolerance]
            if len(active) != 1 or active[0] == axis:
                raise ValueError("CAD rectangle edge direction differs")
            directions.update(active)
            for point in edge["boundary"]:
                pb,eb = points[point]["bbox_mm"],edge["bbox_mm"]
                if any(pb[k] < eb[k]-tolerance or pb[k+1] > eb[k+1]+tolerance for k in (0,2,4)):
                    raise ValueError("CAD rectangle endpoint outside edge")
        if len(degree) != 4 or any(v != 2 for v in degree.values()) or directions != Counter({k:2 for k in range(3) if k != axis}):
            raise ValueError("CAD rectangle corner/edge cycle differs")
        reached, pending = set(),[next(iter(degree))]
        while pending:
            point = pending.pop()
            if point not in reached:
                reached.add(point); pending.extend(graph[point]-reached)
        if reached != set(degree): raise ValueError("CAD rectangle boundary is disconnected")
        # Native bounding boxes may include kernel padding. This bounds the
        # rectangle's possible area; final mesh/native area comparison keeps
        # the stricter original measure tolerance and is never replaced here.
        widths = [b[k+1]-b[k] for k in (0,2,4) if k//2 != axis]
        lo,hi = math.prod(max(0.,w-2*tolerance) for w in widths),math.prod(w+2*tolerance for w in widths)
        if not coordinate(r["measure_native"]) or r["measure_native"] <= 0:
            raise ValueError("finite positive CAD rectangle area required")
        error = max(cfg["measure_atol_native"],cfg["measure_rtol"]*r["measure_native"])
        if not lo-error <= r["measure_native"] <= hi+error:
            raise ValueError("CAD rectangle bounding area differs")
        result.append({"tag":r["tag"], "group":group, "box":b, "area":r["measure_native"],
            "volume":r["upward"][0], "axis":axis,
            "normal_sign":(-1 if side % 2 == 0 else 1)*(1 if owner == -1 else -1)})
    return result


if __name__ == "__main__":
    raise SystemExit("Library only; actual volume construction requires allocation/source/runtime-guarded SLURM callers")
