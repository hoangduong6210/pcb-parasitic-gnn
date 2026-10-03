"""Planar native array capture and independent audit; no meshing/CLI entry.

Real packets must be captured/replayed only inside the guarded SLURM worker.
Raw connectivity is retained; CCW orientation is a separate audit view only.
"""
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
import math

import tcad_cps_column_cad as cad
from tcad_cps_column_contract import fraction, rational, CLOSED
from tcad_cps_dielectric_mesh_audit import integers, reals, unique_tags, row_order, _indices

SCHEMA = "pcb-gnn.column-planar-mesh.v1"
ARRAY_DTYPES = {"node_tags":"<i8","coordinates_mm":"<f8","node_dimension":"<i8","node_entity":"<i8",
    "triangle_tags":"<i8","triangle_nodes":"<i8","triangle_surfaces":"<i8",
    "line_tags":"<i8","line_nodes":"<i8","line_curves":"<i8"}
LEAKAGE_BITS = 80


def leakage_upper_bound(value):
    """Conservative dyadic accumulation avoids products of clipping denominators."""
    if value < 0: raise ValueError("nonnegative leakage required")
    scale = 1 << LEAKAGE_BITS
    return Fraction(-(-(value.numerator*scale)//value.denominator),scale)


def canonical_packet(packet,limits):
    import numpy as np
    if set(packet) != set(ARRAY_DTYPES):
        raise ValueError("planar packet schema mismatch")
    output = {}
    for prefix,width,owner,cap in (("node",None,None,"planar_nodes_max"),
            ("triangle",3,"surfaces","planar_triangles_max"),("line",2,"curves","planar_lines_max")):
        tags = integers(packet[prefix+"_tags"])
        if type(limits[cap]) is not int or not 0 < len(tags) <= limits[cap]:
            raise ValueError("planar array count exceeds cap")
        unique_tags(tags)
        order = np.argsort(tags,kind="stable")
        output[prefix+"_tags"] = tags[order]
        if width is None:
            output["coordinates_mm"] = reals(packet["coordinates_mm"],(len(tags),3))[order]
            dimension = np.asarray(packet["node_dimension"])
            entity = integers(packet["node_entity"])
            if (dimension.shape != (len(tags),) or dimension.dtype.kind not in "iu" or np.any(dimension > 2)
                    or np.any(dimension < 0) or len(entity) != len(tags)):
                raise ValueError("invalid native node classification")
            output["node_dimension"] = dimension.astype(np.int64)[order]
            output["node_entity"] = entity[order]
        else:
            connectivity = integers(packet[prefix+"_nodes"],width)
            owners = integers(packet[prefix+"_"+owner])
            if len(connectivity) != len(tags) or len(owners) != len(tags):
                raise ValueError("planar related-array length mismatch")
            sorted_nodes = np.sort(connectivity,axis=1)
            if np.any(sorted_nodes[:,1:] == sorted_nodes[:,:-1]):
                raise ValueError("planar element repeats a vertex")
            sorted_nodes = sorted_nodes[row_order(sorted_nodes)]
            if np.any(np.all(sorted_nodes[1:] == sorted_nodes[:-1],axis=1)):
                raise ValueError("duplicate planar element connectivity")
            output[prefix+"_nodes"] = connectivity[order]
            output[prefix+"_"+owner] = owners[order]
    if np.intersect1d(output["triangle_tags"],output["line_tags"]).size:
        raise ValueError("native element tag reused across dimensions")
    return output


def packet_sha256(packet):
    import numpy as np
    digest = hashlib.sha256((SCHEMA+"\0").encode())
    for name,dtype in ARRAY_DTYPES.items():
        value = np.ascontiguousarray(packet[name],dtype=dtype)
        header = json.dumps({"name":name,"dtype":value.dtype.str,"shape":list(value.shape)},sort_keys=True,separators=(",",":"))
        digest.update(header.encode()+b"\0")
        digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def read_native(native,snapshot,limits):
    """Capture global arrays plus entity-local classifications/connectivity."""
    import numpy as np
    if native.model.getEntities(3):
        raise ValueError("volume entities forbidden in planar reader")
    for dim in range(3):
        if cad.dimensions(native.model.getEntities(dim),dim) != [r["tag"] for r in snapshot[str(dim)]]:
            raise ValueError("native CAD entities changed before planar extraction")
    node_tags,coordinates,_ = native.model.mesh.getNodes(-1,-1,includeBoundary=False,returnParametricCoord=False)
    node_tags = integers(node_tags)
    if len(node_tags) > limits["planar_nodes_max"]:
        raise ValueError("native planar node cap exceeded")
    coordinates = np.asarray(coordinates).reshape((-1,3))
    classified = {}
    for dim in range(3):
        for r in snapshot[str(dim)]:
            local,xyz,_ = native.model.mesh.getNodes(dim,r["tag"],includeBoundary=False,returnParametricCoord=False)
            local,xyz = np.asarray(local),np.asarray(xyz).reshape((-1,3))
            if local.dtype.kind not in "iu" or len(local) != len(xyz):
                raise ValueError("invalid entity-local node arrays")
            for tag,point in zip(local,xyz):
                if int(tag) in classified:
                    raise ValueError("node classified on multiple native entities")
                classified[int(tag)] = (dim,r["tag"],point)
    if set(classified) != set(node_tags.tolist()) or coordinates.shape != (len(node_tags),3):
        raise ValueError("global/local native node coverage differs")
    if any(not np.array_equal(xyz,classified[int(tag)][2]) for tag,xyz in zip(node_tags,coordinates)):
        raise ValueError("global/local native node coordinates disagree")
    packet = {"node_tags":node_tags,"coordinates_mm":coordinates,
        "node_dimension":np.array([classified[int(t)][0] for t in node_tags],dtype=np.int64),
        "node_entity":np.array([classified[int(t)][1] for t in node_tags],dtype=np.int64)}
    for dim,prefix,width,kind,owner,cap in ((1,"line",2,1,"curves","planar_lines_max"),(2,"triangle",3,2,"surfaces","planar_triangles_max")):
        def elements(tag):
            kinds,tags,nodes = native.model.mesh.getElements(dim,tag)
            if (np.asarray(kinds).dtype.kind not in "iu" or len(kinds) != len(tags)
                    or len(tags) != len(nodes) or any(int(k) != kind for k in kinds)):
                raise ValueError("unexpected native planar element type")
            result = {}
            for ids,flat in zip(tags,nodes):
                ids,flat = np.asarray(ids),np.asarray(flat)
                if ids.dtype.kind not in "iu" or flat.dtype.kind not in "iu" or len(flat) != width*len(ids):
                    raise ValueError("invalid native connectivity block")
                for element,row in zip(ids,flat.reshape((-1,width))):
                    if int(element) in result:
                        raise ValueError("duplicate native element tag")
                    result[int(element)] = tuple(int(x) for x in row)
            if len(result) > limits[cap]:
                raise ValueError("native planar element cap exceeded")
            return result
        global_rows = elements(-1)
        observed,owned = {},{}
        for r in snapshot[str(dim)]:
            local = elements(r["tag"])
            if set(local) & set(observed):
                raise ValueError("element on multiple native entities")
            observed.update(local)
            owned.update({tag:r["tag"] for tag in local})
        if observed != global_rows:
            raise ValueError("global/local native elements disagree")
        tags = sorted(observed)
        packet[prefix+"_tags"] = np.array(tags,dtype=np.int64)
        packet[prefix+"_nodes"] = np.array([observed[t] for t in tags],dtype=np.int64)
        packet[prefix+"_"+owner] = np.array([owned[t] for t in tags],dtype=np.int64)
    return canonical_packet(packet,limits)


def clipped_area(triangle,box):
    """Exact convex clipping against a canonical x/y rectangle."""
    polygon = triangle
    for axis,lower,value in ((0,True,box[0]),(0,False,box[1]),(1,True,box[2]),(1,False,box[3])):
        value = fraction(value)
        result = []
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            inside_a = a[axis] >= value if lower else a[axis] <= value
            inside_b = b[axis] >= value if lower else b[axis] <= value
            if inside_a != inside_b:
                t = (value-a[axis])/(b[axis]-a[axis])
                result.append([a[j]+t*(b[j]-a[j]) for j in range(2)])
            if inside_b: result.append(b)
        polygon = result
        if not polygon: return Fraction(0)
    return abs(sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2


class Components:
    def __init__(self,count): self.parents = list(range(count))
    def root(self,i):
        while self.parents[i] != i:
            self.parents[i] = self.parents[self.parents[i]]
            i = self.parents[i]
        return i
    def join(self,a,b): self.parents[self.root(a)] = self.root(b)


def connected(graph):
    if not graph: return False
    seen,stack = set(),[next(iter(graph))]
    while stack:
        value = stack.pop()
        if value not in seen:
            seen.add(value)
            stack.extend(graph[value]-seen)
    return seen == set(graph)


def check_vertex_links(links,boundary_nodes):
    if not links: raise ValueError("empty planar vertex links")
    for vertex,pairs in links.items():
        if len({tuple(sorted(p)) for p in pairs}) != len(pairs):
            raise ValueError("duplicate planar vertex-link edge")
        graph = defaultdict(set)
        degree = Counter()
        for u,v in pairs:
            if u == v: raise ValueError("collapsed planar vertex-link edge")
            graph[u].add(v); graph[v].add(u); degree[u] += 1; degree[v] += 1
        ends = sum(n == 1 for n in degree.values())
        if (not connected(graph) or any(n not in (1,2) for n in degree.values())
                or ends != (2 if vertex in boundary_nodes else 0)):
            raise ValueError("nonmanifold/disconnected planar vertex link")


def audit_packet(packet,report,boxes,domain,cfg,options,limits):
    import numpy as np
    summary = cad.review_report(report,boxes,domain,cfg,options)
    index = cad.index_snapshot(report["after"],cfg)
    a = canonical_packet(packet,limits)
    tags,xyz = a["node_tags"],a["coordinates_mm"]
    t = _indices(tags,a["triangle_nodes"])
    lines = _indices(tags,a["line_nodes"])
    faces,curves = a["triangle_surfaces"],a["line_curves"]
    if set(faces.tolist()) != set(index[2]) or set(curves.tolist()) != set(index[1]):
        raise ValueError("mesh does not cover every native face/curve")
    if len(np.unique(t)) != len(tags) or len(np.unique(xyz,axis=0)) != len(tags) or np.any(xyz[:,2] != 0.):
        raise ValueError("orphan/duplicate/nonplanar native node")
    tolerance = cfg["coordinate_atol_mm"]
    if any(np.any(xyz[:,k] < domain[2*k]-tolerance) or np.any(xyz[:,k] > domain[2*k+1]+tolerance) for k in (0,1)):
        raise ValueError("planar mesh node outside canonical domain")
    node_faces,point_nodes = [],{}
    for i,(dim,entity) in enumerate(zip(a["node_dimension"].tolist(),a["node_entity"].tolist())):
        if entity not in index[dim]: raise ValueError("node classified on unknown CAD entity")
        if dim == 0:
            if entity in point_nodes or np.max(np.abs(xyz[i]-index[0][entity]["point_mm"])) > tolerance:
                raise ValueError("native CAD point has multiple/misplaced nodes")
            point_nodes[entity] = i
            owners = {f for edge in index[0][entity]["upward"] for f in index[1][edge]["upward"]}
        elif dim == 1:
            owners = set(index[1][entity]["upward"])
        else: owners = {entity}
        node_faces.append(owners)
    if set(point_nodes) != set(index[0]): raise ValueError("native CAD point node coverage missing")
    xy = [[fraction(float(x)),fraction(float(y))] for x,y in xyz[:,:2]]
    edges,links = defaultdict(list),defaultdict(list)
    area_by_face,area_by_mask = defaultdict(Fraction),defaultdict(Fraction)
    leakage = [Fraction(0) for _ in boxes]
    exact_boxes = [[fraction(v) for v in box[:4]] for box in boxes]
    mask_counts,negative,minimum_area = Counter(),0,None
    for ordinal,(row,face) in enumerate(zip(t.tolist(),faces.tolist())):
        if any(face not in node_faces[v] for v in row): raise ValueError("triangle node classification disagrees with face")
        points = [xy[v] for v in row]
        area2 = (points[1][0]-points[0][0])*(points[2][1]-points[0][1])-(points[1][1]-points[0][1])*(points[2][0]-points[0][0])
        if area2 == 0: raise ValueError("exactly degenerate native planar triangle")
        area = abs(area2)/2
        minimum_area = area if minimum_area is None else min(minimum_area,area)
        owners = tuple(summary["ownership"][str(face)])
        center = [sum(p[k] for p in points)/3 for k in (0,1)]
        geometric = tuple(i for i,b in enumerate(exact_boxes) if b[0] < center[0] < b[1] and b[2] < center[1] < b[3])
        if geometric != owners: raise ValueError("triangle centroid disagrees with complete footprint ownership")
        low = [min(p[k] for p in points) for k in (0,1)]
        high = [max(p[k] for p in points) for k in (0,1)]
        for i,(box,bounds) in enumerate(zip(boxes,exact_boxes)):
            if any(high[k] <= bounds[2*k] or low[k] >= bounds[2*k+1] for k in (0,1)):
                overlap = Fraction(0)
            elif all(low[k] >= bounds[2*k] and high[k] <= bounds[2*k+1] for k in (0,1)):
                overlap = area
            else: overlap = clipped_area(points,box)
            leakage[i] += leakage_upper_bound(abs(overlap-(area if i in owners else 0)))
        area_by_face[face] += area
        area_by_mask[owners] += area
        mask_counts[owners] += 1
        if area2 < 0:
            negative += 1
            row = [row[0],row[2],row[1]]  # Derived view; raw packet is never changed.
        for i in range(3):
            u,v,w = row[i],row[(i+1)%3],row[(i+2)%3]
            edges[tuple(sorted((u,v)))].append((ordinal,face,1 if u < v else -1))
            links[u].append((v,w))
    for i,box in enumerate(boxes):
        scale = (fraction(box[1])-fraction(box[0]))*(fraction(box[3])-fraction(box[2]))
        limit = max(fraction(cfg["measure_atol_native"]),fraction(cfg["measure_rtol"])*scale)
        if leakage[i] > limit: raise ValueError("aggregate exact triangle/conductor ownership leakage")
    for face,area in area_by_face.items():
        if not cad.close(index[2][face]["measure_native"],area,cfg): raise ValueError("native/triangle surface area differs")
    expected = {tuple(g["owners"]):g for g in summary["exact_partition"]["groups"]}
    if set(area_by_mask) != set(expected) or any(not cad.close(float(area),cad.unpack(expected[mask]["area_mm2"]),cfg) for mask,area in area_by_mask.items()):
        raise ValueError("triangle ownership areas differ from canonical partition")
    curve_by_edge = {tuple(sorted(row)):curve for row,curve in zip(lines.tolist(),curves.tolist())}
    if not set(curve_by_edge) <= set(edges): raise ValueError("native line is not a triangle edge")
    global_components,face_components = Components(len(t)),Components(len(t))
    outer_graph = defaultdict(set)
    for edge,owners in edges.items():
        if len(owners) not in (1,2) or (len(owners) == 2 and owners[0][2] == owners[1][2]):
            raise ValueError("nonmanifold/folded planar edge")
        if edge in curve_by_edge:
            if sorted(o[1] for o in owners) != index[1][curve_by_edge[edge]]["upward"]:
                raise ValueError("native line/triangle/CAD incidence disagreement")
        elif len(owners) != 2 or owners[0][1] != owners[1][1]:
            raise ValueError("unmatched planar region/outer boundary")
        if len(owners) == 2:
            global_components.join(owners[0][0],owners[1][0])
            if owners[0][1] == owners[1][1]: face_components.join(owners[0][0],owners[1][0])
        else:
            u,v = edge
            outer_graph[u].add(v); outer_graph[v].add(u)
    if (len({global_components.root(i) for i in range(len(t))}) != 1
            or len(tags)-len(edges)+len(t) != 1 or not connected(outer_graph)
            or any(len(v) != 2 for v in outer_graph.values())):
        raise ValueError("planar mesh is not one connected disk with one outer cycle")
    roots_by_face = defaultdict(set)
    for i,face in enumerate(faces.tolist()):
        roots_by_face[face].add(face_components.root(i))
    for face in index[2]:
        if len(roots_by_face[face]) != 1:
            raise ValueError("native planar face has disconnected triangle patches")
    check_vertex_links(links,set(outer_graph))
    lines_by_curve = defaultdict(list)
    for row,curve in zip(lines.tolist(),curves.tolist()):
        lines_by_curve[curve].append(tuple(row))
    for curve,entity in index[1].items():
        selected = lines_by_curve[curve]
        graph = defaultdict(set)
        degree = Counter()
        a0,b0 = [index[0][p]["point_mm"] for p in entity["boundary"]]
        axis = int(abs(b0[1]-a0[1]) > abs(b0[0]-a0[0]))
        lo,hi = sorted((a0[axis],b0[axis]))
        for u,v in selected:
            graph[u].add(v); graph[v].add(u); degree[u] += 1; degree[v] += 1
            for node in (u,v):
                dim,e = int(a["node_dimension"][node]),int(a["node_entity"][node])
                if not ((dim == 0 and e in entity["boundary"]) or (dim == 1 and e == curve)):
                    raise ValueError("line node classification differs from CAD curve")
                if not lo-tolerance <= xyz[node,axis] <= hi+tolerance or abs(xyz[node,1-axis]-a0[1-axis]) > tolerance:
                    raise ValueError("line node is outside native axis-aligned segment")
        ends = {node for node,n in degree.items() if n == 1}
        length = math.fsum(math.dist(xyz[u],xyz[v]) for u,v in selected)
        if (ends != {point_nodes[p] for p in entity["boundary"]} or any(n not in (1,2) for n in degree.values())
                or not connected(graph) or not cad.close(length,entity["measure_native"],cfg)):
            raise ValueError("native curve mesh is not a complete nonoverlapping endpoint chain")
    return {"schema":"pcb-gnn.column-planar-audit.v1","packet_sha256":packet_sha256(a),
        "planar_nodes":len(tags),"planar_triangles":len(t),"planar_lines":len(lines),
        "raw_clockwise_triangles":negative,"minimum_exact_triangle_area_mm2":rational(minimum_area),
        "groups":[{"owners":list(k),"triangles":v} for k,v in sorted(mask_counts.items())],
        "ownership_leakage_upper_bound_mm2":[rational(v) for v in leakage],
        "leakage_bound_quantum_mm2":rational(Fraction(1,1 << LEAKAGE_BITS)),"planar_mesh_validated":True,
        "coordinates_snapped":False,"raw_connectivity_changed":False,"native_quality_claimed":False,
        **{k:False for k in CLOSED}}


if __name__ == "__main__":
    raise SystemExit("Library only; real mesh capture/replay requires guarded SLURM integration")
