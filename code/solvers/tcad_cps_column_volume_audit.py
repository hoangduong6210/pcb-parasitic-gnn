"""Complete streamed tetrahedron facet audit; actual meshes are compute-only.

No native imports, file writes, field solves or runnable mesh entry point.
The input CAD and planar contracts must be independently replayed by the caller.
"""
import math
from fractions import Fraction

from tcad_cps_column_volume_geometry import boundary_surfaces
from tcad_cps_column_contract import exact_volume, rational

CLOSED = ("field_solver_executed", "numerical_accuracy_qualified", "reference_qualified",
          "training_may_start", "claim_eligible")
OUTWARD = ((1,2,3), (0,3,2), (0,1,3), (0,2,1))


def row_order(a):
    import numpy as np
    return np.lexsort(tuple(a[:,i] for i in reversed(range(a.shape[1]))))


def parity(a):
    import numpy as np
    return sum((a[:,i] > a[:,j]).astype(np.int8) for i,j in ((0,1),(0,2),(1,2))) % 2


def slab_facets(t):
    """Every face, including both induced orientations on shared faces."""
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    if (t.ndim != 2 or t.shape[1] != 4 or t.dtype.kind not in "iu" or not len(t)
            or np.any(t <= 0) or np.any(np.diff(np.sort(t,axis=1),axis=1) == 0)):
        raise ValueError("finite positive distinct slab vertex identities required")
    faces = np.concatenate([t[:,side] for side in OUTWARD])
    keys = np.sort(faces, axis=1)
    order = row_order(keys)
    keys, signs = keys[order], parity(faces)[order]
    owners = order % len(t)
    starts = np.r_[0, np.flatnonzero(np.any(keys[1:] != keys[:-1], axis=1))+1]
    counts = np.diff(np.r_[starts, len(keys)])
    if np.any(counts > 2):
        raise ValueError("nonmanifold slab facet")
    paired = starts[counts == 2]
    if np.any(signs[paired] == signs[paired+1]):
        raise ValueError("slab internal orientations do not cancel")
    graph = coo_matrix((np.ones(len(paired), dtype=np.int8),
        (owners[paired], owners[paired+1])), shape=(len(t),len(t))).tocsr()
    n, components = connected_components(graph, directed=False)
    boundary = starts[counts == 1]
    return faces[order[boundary]], owners[boundary], int(len(paired)), int(n), components


class Components:
    """Join slab components without retaining a whole-volume adjacency graph."""

    def __init__(self):
        self.parent, self.rank, self.anchored, self.volume = [], [], [], []

    def add(self, count):
        offset = len(self.parent)
        self.parent.extend(range(offset, offset+count))
        self.rank.extend([0]*count)
        self.anchored.extend([False]*count)
        self.volume.extend([None]*count)
        return offset

    def root(self, i):
        i = int(i)
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a, b):
        a,b = self.root(a),self.root(b)
        if a == b: return
        if self.volume[a] is not None and self.volume[b] is not None and self.volume[a] != self.volume[b]:
            raise ValueError("joined components disagree on retained CAD owner")
        if self.rank[a] < self.rank[b]: a,b = b,a
        self.parent[b] = a
        self.rank[a] += self.rank[a] == self.rank[b]
        self.anchored[a] |= self.anchored[b]
        if self.volume[a] is None: self.volume[a] = self.volume[b]

    def mark(self, component, volume, terminal):
        root = self.root(component)
        if self.volume[root] not in (None, volume):
            raise ValueError("component boundary has conflicting CAD owners")
        self.volume[root] = volume
        self.anchored[root] |= terminal

    def finish(self, volumes):
        roots = [i for i in range(len(self.parent)) if self.root(i) == i]
        if any(not self.anchored[i] for i in roots):
            raise ValueError("volume component has no terminal boundary")
        if len(roots) != len(volumes) or {self.volume[i] for i in roots} != set(volumes):
            raise ValueError("mesh/CAD connected component coverage differs")
        return len(roots)


def join_seam(previous, current, components):
    """Exact row join; unmatched horizontal faces remain physical boundaries."""
    import numpy as np
    faces = np.concatenate((previous[0],current[0]))
    labels = np.concatenate((previous[1],current[1]))
    owners = np.concatenate((previous[2],current[2]))
    if not len(faces): return (faces,labels,owners),0
    origin = np.r_[np.zeros(len(previous[0]),dtype=np.int8), np.ones(len(current[0]),dtype=np.int8)]
    keys = np.sort(faces,axis=1)
    order = row_order(keys)
    keys, signs = keys[order], parity(faces)[order]
    origin, labels, owners, faces = origin[order],labels[order],owners[order],faces[order]
    starts = np.r_[0,np.flatnonzero(np.any(keys[1:] != keys[:-1],axis=1))+1]
    counts = np.diff(np.r_[starts,len(keys)])
    if np.any(counts > 2): raise ValueError("nonmanifold horizontal seam")
    pairs = starts[counts == 2]
    if np.any(origin[pairs] == origin[pairs+1]) or np.any(signs[pairs] == signs[pairs+1]):
        raise ValueError("horizontal seam ownership/orientation differs")
    for left,right in np.unique(np.column_stack((labels[pairs],labels[pairs+1])),axis=0):
        components.join(left,right)
    boundary = starts[counts == 1]
    return (faces[boundary],labels[boundary],owners[boundary]),int(len(pairs))


class VolumeAudit:
    """Visit slabs in order; require complete facet accounting and CAD coverage."""

    def __init__(self, columns, after, groups, boxes, domain, nets, cfg, limits, preserve_boundary=None):
        import numpy as np
        self.columns, self.cfg, self.limits = columns,dict(cfg),dict(limits)
        if type(limits["mesh_triangles_max"]) is not int or limits["mesh_triangles_max"] <= 0:
            raise ValueError("positive integer boundary cap required")
        self.surfaces = boundary_surfaces(after,groups,boxes,domain,nets,cfg)
        self.volumes = {r["tag"]:r for r in after["3"]}
        self.canonical_volume = exact_volume(domain)-sum((exact_volume(b) for b in boxes),Fraction(0))
        if self.canonical_volume <= 0: raise ValueError("positive canonical dielectric volume required")
        self.components = Components()
        self.empty = (np.empty((0,3),dtype=np.int64),np.empty(0,dtype=np.int64),np.empty(0,dtype=np.int64))
        self.top = self.empty
        self.next_slab = self.tetrahedra = self.interior = self.boundary = 0
        self.volume_parts, self.relative_errors, self.minima, self.component_volumes = [], [], [], []
        self.area_parts = {r["tag"]:[] for r in self.surfaces}
        self.surface_counts = {r["tag"]:0 for r in self.surfaces}
        self.used = np.zeros(columns.full_nodes,dtype=bool)
        self.group_nodes = {name:np.zeros(columns.full_nodes,dtype=bool) for name in ("primary","secondary","outer")}
        self.preserve_boundary = preserve_boundary
        self.finished = False
        self.failed = False

    def _boundary(self, block):
        import numpy as np
        faces,labels,owners = block
        if not len(faces): return
        if self.boundary+len(faces) > self.limits["mesh_triangles_max"]:
            raise ValueError("volume boundary triangle cap exceeded")
        xyz = self.columns.coordinates(faces)
        low, high = xyz.min(axis=1), xyz.max(axis=1)
        normals = np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])
        area = np.linalg.norm(normals,axis=1)/2
        if not np.isfinite(area).all() or np.any(area <= 0):
            raise ValueError("nonpositive/nonfinite boundary triangle area")
        counts, tags = np.zeros(len(faces),dtype=np.int16),np.zeros(len(faces),dtype=np.int64)
        tolerance = self.cfg["coordinate_atol_mm"]
        for surface in self.surfaces:
            b = np.asarray(surface["box"])
            selected = np.all(low >= b[::2]-tolerance,axis=1) & np.all(high <= b[1::2]+tolerance,axis=1)
            if not np.any(selected): continue
            if np.any(normals[selected,surface["axis"]]*surface["normal_sign"] <= 0):
                raise ValueError("boundary normal is not outward from dielectric")
            counts[selected] += 1; tags[selected] = surface["tag"]
            self.area_parts[surface["tag"]].append(float(np.sum(area[selected],dtype=np.float64)))
            self.surface_counts[surface["tag"]] += int(np.count_nonzero(selected))
            self.group_nodes[surface["group"]][faces[selected].ravel()-1] = True
            for label in np.unique(labels[selected]):
                self.components.mark(label,surface["volume"],surface["group"] != "outer")
        if np.any(counts != 1):
            raise ValueError("exterior triangle has missing/ambiguous CAD surface")
        if self.preserve_boundary is not None:
            self.preserve_boundary(faces,tags,owners)
        self.boundary += len(faces)

    def visit(self, index, connectivity):
        if self.failed or self.finished: raise ValueError("volume audit is closed or failed")
        self.failed = True
        self._visit(index, connectivity)
        self.failed = False

    def _visit(self, index, connectivity):
        import numpy as np
        if self.finished or type(index) is not int or index != self.next_slab:
            raise ValueError("volume slabs must be visited exactly once in order")
        t = np.asarray(connectivity)
        expected, determinant_oracle = self.columns.slab(index)
        if t.dtype.kind not in "iu" or t.shape != expected.shape or not np.array_equal(t,expected):
            raise ValueError("actual volume connectivity differs from complete canonical construction")
        xyz = self.columns.coordinates(t)
        edges = [xyz[:,j]-xyz[:,0] for j in (1,2,3)]
        determinant = np.einsum("ij,ij->i",edges[0],np.cross(edges[1],edges[2]))
        if (not np.isfinite(determinant).all() or np.any(determinant <= 0)
                or not np.isfinite(determinant_oracle).all() or np.any(determinant_oracle <= 0)
                or not np.allclose(determinant,determinant_oracle,rtol=self.cfg["jacobian_rtol"],atol=0)):
            raise ValueError("actual signed volume determinant disagrees with exact column oracle")
        self.used[t.ravel()-1] = True
        self.volume_parts.append(float(np.sum(determinant,dtype=np.float64)/6))
        self.relative_errors.append(float(np.max(np.abs(determinant-determinant_oracle)/determinant_oracle)))
        self.minima.append(float(np.min(determinant)))
        del xyz,edges,expected
        faces,owners,inside,count,local = slab_facets(t)
        offset = self.components.add(count)
        local_volumes = np.bincount(local,weights=determinant/6,minlength=count)
        self.component_volumes.extend((offset+component,float(value)) for component,value in enumerate(local_volumes))
        labels = local[owners]+offset
        owners = owners+self.tetrahedra+1  # Generated positive element identities.
        plane = (faces-1)//self.columns.n
        bottom = np.all(plane == index,axis=1)
        top = np.all(plane == index+1,axis=1)
        side = ~(bottom | top)
        self._boundary((faces[side],labels[side],owners[side]))
        exposed,joined = join_seam(self.top,(faces[bottom],labels[bottom],owners[bottom]),self.components)
        self._boundary(exposed)
        self.top = (faces[top],labels[top],owners[top])
        self.interior += inside+joined
        self.tetrahedra += len(t)
        self.next_slab += 1

    def finish(self):
        if self.failed or self.finished: raise ValueError("volume audit is closed or failed")
        self.failed = True
        result = self._finish()
        self.failed = False
        return result

    def _finish(self):
        import numpy as np
        if self.finished or self.next_slab != len(self.columns.counts) or self.tetrahedra != self.columns.tetrahedra:
            raise ValueError("incomplete or repeated volume finish")
        self._boundary(self.top)
        if 4*self.tetrahedra != 2*self.interior+self.boundary:
            raise ValueError("whole-volume facet accounting differs")
        for left,right in (("primary","secondary"),("primary","outer"),("secondary","outer")):
            if np.any(self.group_nodes[left] & self.group_nodes[right]):
                raise ValueError("terminal/outer node sets overlap")
        def close(a,b): return math.isclose(a,b,rel_tol=self.cfg["measure_rtol"],abs_tol=self.cfg["measure_atol_native"])
        area = {k:math.fsum(v) for k,v in self.area_parts.items()}
        if any(not self.surface_counts[r["tag"]] or not close(area[r["tag"]],r["area"]) for r in self.surfaces):
            raise ValueError("complete boundary CAD area coverage differs")
        volume = math.fsum(self.volume_parts)
        error = abs(Fraction(volume)-self.canonical_volume)
        limit = max(Fraction(self.cfg["measure_atol_native"]),Fraction(self.cfg["measure_rtol"])*self.canonical_volume)
        if error > limit or not close(volume,math.fsum(r["measure_native"] for r in self.volumes.values())):
            raise ValueError("actual volume differs from canonical/CAD dielectric volume")
        components = self.components.finish(self.volumes)
        parts = {tag:[] for tag in self.volumes}
        for component,value in self.component_volumes:
            parts[self.components.volume[self.components.root(component)]].append(value)
        by_volume = {tag:math.fsum(values) for tag,values in parts.items()}
        if any(not close(by_volume[tag],row["measure_native"]) for tag,row in self.volumes.items()):
            raise ValueError("individual CAD volume coverage differs")
        self.finished = True
        return {"schema":"pcb-gnn.column-volume-audit.v1","mesh_tetrahedra":self.tetrahedra,
            "mesh_nodes":int(np.count_nonzero(self.used)),"full_column_node_upper_bound":self.columns.full_nodes,
            "interior_facets":self.interior,"boundary_triangles":self.boundary,"tetrahedral_components":components,
            "independent_volume_mm3":volume,"canonical_volume_mm3":rational(self.canonical_volume),
            "canonical_volume_error_mm3":rational(error),"canonical_volume_limit_mm3":rational(limit),
            "cad_volume_mm3":{str(k):v for k,v in by_volume.items()},
            "minimum_independent_det_jac_mm3":min(self.minima),"maximum_determinant_relative_difference":max(self.relative_errors),
            "cad_surface_mm2":{str(k):v for k,v in area.items()},
            "boundary_groups":{g:{"nodes":int(np.count_nonzero(mask)),
                "triangles":sum(self.surface_counts[r["tag"]] for r in self.surfaces if r["group"] == g)} for g,mask in self.group_nodes.items()},
            "boundary_contract_passed":True,"volume_mesh_generated":True,"coordinates_snapped":False,
            "native_quality_claimed":False,**{k:False for k in CLOSED}}

    def node_arrays(self):
        import numpy as np
        if not self.finished or self.failed: raise ValueError("complete audited construction required before node projection")
        tags = np.flatnonzero(self.used)+1
        return tags,self.columns.coordinates(tags)


if __name__ == "__main__":
    raise SystemExit("Library only; real volume audit requires allocation/source/runtime-guarded SLURM callers")
