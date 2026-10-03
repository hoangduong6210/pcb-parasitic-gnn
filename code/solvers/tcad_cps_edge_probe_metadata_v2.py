"""Byte/scalar closure of recorded probes; never reconstruct layout probes."""
from tcad_cps_model_field_probe import EVENTS, TEMP_MODEL, validate_data
from tcad_cps_edge_sizing import validate_probe

PROBE_NAMES = {"probe_state_before", "probe_state_after"} | {
    stem+"."+event for stem in ("distance", "size") for event in EVENTS}
NAMES = PROBE_NAMES | {"inputs", "cad", "sizing", "field_probe", "post_mesh_cad", "report"}


def validate_main_state(before, cad, sizing, p):
    """Compare recorded native state with already captured CAD/sizing metadata."""
    session = before["session"]
    models = session["models"]
    if (set(session) != {"current_model", "models", "views"}
            or session["current_model"] != "tcad_column_footprints" or session["views"] != []
            or not isinstance(models, list) or any(not isinstance(v, str) for v in models)
            or len(set(models)) != len(models) or models.count(session["current_model"]) != 1
            or TEMP_MODEL in models):
        raise ValueError("original planar model/session differs")
    mesh = {"entities": [[dim, r["tag"]] for dim in range(4) for r in cad[str(dim)]],
        "node_tags": [], "coordinates_mm": [], "parametric": [], "element_types": [],
        "element_tags": [], "element_nodes": []}
    fields = {"tags": [r["tag"] for r in sizing["distance_fields"]]+[sizing["minimum_tag"], sizing["background_tag"]],
        "expressions": [{"tag": r["tag"], "type": "MathEval", "F": r["expression"]} for r in sizing["distance_fields"]],
        "minimum": {"tag": sizing["minimum_tag"], "type": "Min", "FieldsList": [r["tag"] for r in sizing["distance_fields"]]},
        "threshold": {"tag": sizing["background_tag"], "type": "Threshold", "settings": sizing["threshold_settings"]}}
    if before != {"session": session, "cad": cad, "mesh": mesh, "fields": fields,
            "options": {**p["dielectric_cad"]["cad_options"], **sizing["requested"]["options"]}}:
        raise ValueError("original planar CAD/fields/options/empty-mesh differs")


def validate_probe_records(data, p, cfg):
    """Validate recorded points/raw values, not their real-geometry oracle."""
    sizing, observed = data["sizing"], data["field_probe"]
    before, after = data["probe_state_before"], data["probe_state_after"]
    validate_main_state(before, data["cad"]["after"], sizing, p)
    if before != after:
        raise ValueError("original planar probe state was not restored")
    validate_probe(observed, sizing, cfg)
    points = [row["point_mm"] for row in observed["points"]]
    tags = list(range(1, len(points)+1))
    session = before["session"]
    scaffold = {"entities": [[0,1]], "node_tags": tags,
        "coordinates_mm": [v for point in points for v in point], "parametric": [],
        "element_types": [15], "element_tags": [tags], "element_nodes": [tags]}
    for stem, field in (("distance", sizing["minimum_tag"]), ("size", sizing["background_tag"])):
        request = {"field_tag": field, "points_mm": points, "before": session,
            "temporary_model": TEMP_MODEL, "temporary_entity": [0,1], "point_element_type": 15}
        out = data[stem+".view_after"]
        view = out["view_tag"]
        if (data[stem+".request"] != request or data[stem+".scaffold"] != scaffold
                or data[stem+".cleanup"] != session or out["scaffold_after"] != scaffold
                or type(view) is not int or view < 0 or out["returned_view"] != view
                or out["active"] != {"current_model": session["current_model"], "models": [*session["models"], TEMP_MODEL], "views": [view]}
                or validate_data(data[stem+".view_before"], tags) != [-12345.]*len(tags)
                or validate_data(out["data"], tags) != [row["native_"+stem+"_mm"] for row in observed["points"]]):
            raise ValueError("native model-backed layout probe raw/state closure differs")
    return True
