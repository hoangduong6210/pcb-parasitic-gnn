"""Model-backed field sampling; native callers must be allocation-guarded.

No native initialization/import on module load. This inserts disposable 0D
probe elements, never calls mesh.generate and never edits the original model.
"""
import math

from tcad_cps_column_contract import coordinate
from tcad_cps_edge_sizing import distance_squared, rational, size_at_distance
from scientific_artifact import sha256_json

TEMP_MODEL = "__tcad_isolated_field_probe__"
EVENTS = ("request", "scaffold", "view_before", "view_after", "cleanup")


def scalar(value):
    value = float(value)
    return value if math.isfinite(value) else {"nonfinite": str(value)}


def state(native):
    return {"current_model": native.model.getCurrent(), "models": list(native.model.list()),
        "views": [int(t) for t in native.view.getTags()]}


def scaffold(native):
    tags, xyz, param = native.model.mesh.getNodes()
    kinds, elements, nodes = native.model.mesh.getElements()
    return {"entities": [[int(d),int(t)] for d,t in native.model.getEntities()],
        "node_tags": [int(t) for t in tags], "coordinates_mm": [scalar(v) for v in xyz],
        "parametric": [scalar(v) for v in param], "element_types": [int(t) for t in kinds],
        "element_tags": [[int(t) for t in row] for row in elements],
        "element_nodes": [[int(t) for t in row] for row in nodes]}


def view_data(native, view):
    kind, tags, values, time, components = native.view.getModelData(view,0)
    return {"data_type": kind, "node_tags": [int(t) for t in tags],
        "values": [[scalar(v) for v in row] for row in values], "time": scalar(time),
        "components": int(components)}


def validate_data(data, tags):
    if (data["data_type"] != "NodeData" or data["node_tags"] != tags or data["time"] != 0.
            or data["components"] != 1 or len(data["values"]) != len(tags)
            or any(len(row) != 1 or not coordinate(row[0]) for row in data["values"])):
        raise ValueError("native model-backed probe data identity/shape/nonfinite mismatch")
    return [row[0] for row in data["values"]]


def evaluate(native, field_tag, points, preserve):
    """Preserve each raw stage before its gate; restore/remove only owned state."""
    if (type(field_tag) is not int or field_tag <= 0 or not isinstance(points,list)
            or not 0 < len(points) <= 8192 or any(len(p) != 3 or not all(coordinate(v) for v in p) for p in points)
            or len({tuple(p) for p in points}) != len(points)):
        raise ValueError("bounded unique finite model probe points/field required")
    before = state(native)
    original = before["current_model"]
    if (before["views"] or not original or before["models"].count(original) != 1
            or len(set(before["models"])) != len(before["models"]) or TEMP_MODEL in before["models"]
            or field_tag not in [int(t) for t in native.model.mesh.field.list()]):
        raise ValueError("native probe requires unique original model, fresh view and existing field")
    tags = list(range(1,len(points)+1))
    request = {"field_tag":field_tag,"points_mm":points,"before":before,
        "temporary_model":TEMP_MODEL,"temporary_entity":[0,1],"point_element_type":15}
    preserve("request",request)
    view, created = None, False
    try:
        native.model.add(TEMP_MODEL)
        created = True
        native.model.addDiscreteEntity(0,1)
        native.model.mesh.addNodes(0,1,tags,[v for p in points for v in p])
        native.model.mesh.addElementsByType(1,15,tags,tags)
        raw = scaffold(native)
        preserve("scaffold",raw)
        expected = {"entities":[[0,1]],"node_tags":tags,"coordinates_mm":[v for p in points for v in p],
            "parametric":[],"element_types":[15],"element_tags":[tags],"element_nodes":[tags]}
        if raw != expected:
            raise ValueError("native probe point-element scaffold differs")
        view = native.view.add("tcad_model_field_probe")
        native.view.addModelData(view,0,TEMP_MODEL,"NodeData",tags,[[-12345.] for _ in tags],time=0.,numComponents=1)
        initial = view_data(native,view)
        preserve("view_before",initial)
        if validate_data(initial,tags) != [-12345.]*len(tags):
            raise ValueError("native probe initialization differs")
        native.model.setCurrent(original)
        native.plugin.setNumber("MeshSizeFieldView","MeshSizeField",field_tag)
        native.plugin.setNumber("MeshSizeFieldView","View",native.view.getIndex(view))
        native.plugin.setNumber("MeshSizeFieldView","Component",0)
        returned = native.plugin.run("MeshSizeFieldView")
        data = view_data(native,view)
        active = state(native)
        native.model.setCurrent(TEMP_MODEL)
        post = scaffold(native)
        native.model.setCurrent(original)
        output = {"returned_view":returned,"view_tag":view,"data":data,"active":active,"scaffold_after":post}
        preserve("view_after",output)
        if (returned != view or active != {"current_model":original,"models":[*before["models"],TEMP_MODEL],"views":[view]}
                or post != raw):
            raise ValueError("native probe model/view/scaffold changed")
        values = validate_data(data,tags)
    finally:
        try:
            if view is not None and view in native.view.getTags(): native.view.remove(view)
        finally:
            try:
                if created and TEMP_MODEL in native.model.list():
                    native.model.setCurrent(TEMP_MODEL)
                    native.model.remove()
            finally:
                if original in native.model.list(): native.model.setCurrent(original)
                after = state(native)
                preserve("cleanup",after)
                if after != before:
                    raise ValueError("native probe cleanup/current-model restoration differs")
    return values


def comparison(points, sizing, cfg, native_distance, native_size):
    if len(native_distance) != len(points) or len(native_size) != len(points):
        raise ValueError("native comparison point count differs")
    rows = []
    for point,distance,size in zip(points,native_distance,native_size):
        square = min(distance_squared(point[:2],s) for s in sizing["requested"]["segments"])
        expected = math.sqrt(float(square))
        rows.append({"point_mm":point,"exact_minimum_distance_squared_mm2":rational(square),
            "expected_distance_mm":expected,"native_distance_mm":distance,
            "expected_size_mm":size_at_distance(expected,sizing["requested"]["threshold"]),"native_size_mm":size})
    return {"schema":"pcb-gnn.edge-sizing-probe.v1","sizing_sha256":sha256_json(sizing),
        "point_set_sha256":sha256_json(points),"points":rows,"point_count":len(rows),
        "rtol":cfg["probe_rtol"],"atol_mm":cfg["probe_atol_mm"],
        "probe_is_mesh_accuracy_test":False,"mesh_generated":False,"field_solver_executed":False}


if __name__ == "__main__":
    raise SystemExit("Library only; native field probes require allocation/source/runtime-guarded SLURM callers")
