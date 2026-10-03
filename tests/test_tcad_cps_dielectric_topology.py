"""Tiny abstract topology fixtures only; no native CAD or numerical execution."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dielectric_topology", ROOT / "code/solvers/tcad_cps_dielectric_topology.py")
topology = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(topology)


def example():
    # Abstract incidence, not a geometrically closed collection of solids.
    return dict(all_volumes=[1, 2, 3, 4, 5], all_faces=[11, 12, 13, 14, 15, 16],
                outer_descendants=[1, 2, 3, 4, 5], primary_descendants=[3, 5],
                secondary_descendants=[4], outer_faces=[11, 14],
                volume_faces={1: [11, 12, 13], 2: [13, 14, 15], 3: [12, 16],
                              4: [15], 5: [16]},
                face_volumes={11: [1], 12: [1, 3], 13: [1, 2],
                              14: [2], 15: [2, 4], 16: [3, 5]})


def add_face(data, tag, owners):
    data["all_faces"].append(tag)
    data["face_volumes"][tag] = list(owners)
    for owner in owners:
        data["volume_faces"][owner].append(tag)


def test_classification_and_retained_incidence():
    data = example()
    before = copy.deepcopy(data)
    plan = topology.classify_interfaces(**data)
    assert data == before
    assert plan["faces"] == dict(primary=[12], secondary=[15], outer=[11, 14],
                                 internal_dielectric=[13], internal_metal=[16])
    assert plan["volumes"] == dict(dielectric=[1, 2], primary=[3, 5], secondary=[4])
    assert plan["expected_retained_face_volumes"] == {
        11: [1], 12: [1], 13: [1, 2], 14: [2], 15: [2]}
    assert plan["expected_retained_volume_faces"] == {1: [11, 12, 13], 2: [13, 14, 15]}
    for key in ("geometry_verified", "removal_verified", "mesh_feasible",
                "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible"):
        assert plan[key] is False


def test_permutations_do_not_change_plan():
    data = example()
    original = topology.classify_interfaces(**data)
    for key, value in data.items():
        data[key] = {k: list(reversed(v)) for k, v in reversed(list(value.items()))} if isinstance(value, dict) else list(reversed(value))
    assert topology.classify_interfaces(**data) == original


@pytest.mark.parametrize("field", ["all_volumes", "all_faces", "outer_descendants",
    "primary_descendants", "secondary_descendants", "outer_faces"])
@pytest.mark.parametrize("value", [[], [1, 1], [True], [0], [-1], [1.0], ["1"], "1"])
def test_invalid_tag_lists(field, value):
    data = example()
    data[field] = value
    with pytest.raises(ValueError):
        topology.classify_interfaces(**data)


@pytest.mark.parametrize("field,value", [
    ("outer_descendants", [1, 2, 3, 4]), ("outer_descendants", [1, 2, 3, 4, 5, 6]),
    ("primary_descendants", [3, 5, 6]), ("secondary_descendants", [3, 4]),
    ("primary_descendants", [1, 2, 3, 5]), ("outer_faces", [99]),
    ("outer_faces", [11]), ("outer_faces", [11, 12, 14])])
def test_provenance_and_outer_scope(field, value):
    data = example()
    data[field] = value
    with pytest.raises(ValueError):
        topology.classify_interfaces(**data)


@pytest.mark.parametrize("field", ["volume_faces", "face_volumes"])
@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "empty", "unknown", "boolean_key"])
def test_incidence_input_contract(field, defect):
    data = example()
    mapping = data[field]
    key = next(iter(mapping))
    if defect == "missing":
        del mapping[key]
    elif defect == "extra":
        mapping[99] = mapping[key][:]
    elif defect == "duplicate":
        mapping[key] += mapping[key][:1]
    elif defect == "empty":
        mapping[key] = []
    elif defect == "unknown":
        mapping[key] = [99]
    else:
        mapping[True] = mapping.pop(key)
    with pytest.raises(ValueError):
        topology.classify_interfaces(**data)


def test_independent_incidence_must_agree():
    data = example()
    data["face_volumes"][12] = [2, 3]
    with pytest.raises(ValueError, match="incidence disagree"):
        topology.classify_interfaces(**data)


@pytest.mark.parametrize("owners,message", [([1, 2, 3], "nonmanifold"),
    ([3, 4], "shared face"), ([1], "unclassified exterior"), ([3], "exposed conductor")])
def test_invalid_interfaces(owners, message):
    data = example()
    add_face(data, 17, owners)
    with pytest.raises(ValueError, match=message):
        topology.classify_interfaces(**data)


def test_orphan_face_rejected():
    data = example()
    data["all_faces"].append(17)
    data["face_volumes"][17] = []
    with pytest.raises(ValueError):
        topology.classify_interfaces(**data)


def test_neumann_only_dielectric_component_rejected():
    data = example()
    data["all_volumes"].append(6)
    data["outer_descendants"].append(6)
    data["volume_faces"][6] = []
    add_face(data, 17, [6])
    data["outer_faces"].append(17)
    with pytest.raises(ValueError, match="no terminal boundary"):
        topology.classify_interfaces(**data)


def test_disconnected_but_anchored_component_allowed():
    data = example()
    data["all_volumes"].append(6)
    data["outer_descendants"].append(6)
    data["volume_faces"][6] = []
    add_face(data, 17, [3, 6])
    plan = topology.classify_interfaces(**data)
    assert plan["volumes"]["dielectric"] == [1, 2, 6]
    assert plan["faces"]["primary"] == [12, 17]


def test_metadata_module_has_no_imports_or_native_entrypoint():
    import ast
    tree = ast.parse(Path(SPEC.origin).read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert len(imports) == 1 and imports[0].module == "__future__"
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in ("eval", "exec", "__import__") for node in ast.walk(tree))
